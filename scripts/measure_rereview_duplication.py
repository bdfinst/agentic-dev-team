#!/usr/bin/env python3
"""measure_rereview_duplication.py — quantify duplicate review-agent
dispatches ACROSS build checkpoints and repeat runs (#2165, slice 0 of epic
#2164).

This is the orthogonal, **cross-round** counterpart to #1618's own
`measure_full_file_duplication.py`, which measures the same-round case
(several agents in ONE dispatch round independently reading one unchanged
file). This script instead asks: across TIME — `/build` sub-step 4 clearing
a file, then sub-step 6 or the Step 6 backstop reviewing it again unchanged,
or a second `/code-review` invocation re-running every lens over an
unchanged target set — how much of that is the same `(lens,
file_content_hash)` pair being paid for more than once?

Checkpoint model (Step 1.1): a caller supplies an ordered list of explicit
`(baseline, head)` pairs — never a single commit's own self-diff, which
cannot see a file that a later checkpoint's own commits never re-touch but
that still sits inside that checkpoint's BROADER review scope (a slice-
boundary batch review, or the Step 6 backstop's "all files modified during
the build", `build/SKILL.md` line 298). Each checkpoint's file set is
`git diff --name-only <baseline>..<head>` — cumulative since that
checkpoint's own stated baseline, not scoped to any one commit inside the
range. `select_lenses.applicable_lenses` resolves which lenses apply to that
whole file set (using the checkpoint-local `git diff --name-status` to also
derive `added_files`, so a `Scope: added-only` lens narrows correctly per
checkpoint rather than being evaluated once globally); each file's content
at that checkpoint's `head` is hashed via `git show <head>:<file> |
sha256`. The first checkpoint a `(lens, file_hash)` pair is seen at is free;
every later occurrence is a duplicate.

A baseline or head sha that fails to resolve is a hard failure for the
WHOLE invocation: `find_theoretical_duplicates` raises
`CheckpointResolutionError` naming the specific sha and which checkpoint it
belongs to, before returning anything — there is no partial result for a
caller to mistake for a clean run over fewer checkpoints. Checkpoints are
processed strictly in the order the caller supplies them (documented here,
not inferred from timestamps or topology).

Future `--checkpoint <baseline_sha>:<head_sha>[:<label>]` CLI shape (wired
in a later step over `parse_checkpoint_spec` below): repeatable, each
argument becomes one `Checkpoint` in that same caller-given order.

Deliberately out of scope for THIS step (Step 1.1): the `theoretical`/
`empirical`/`report`/`rollup` argparse subcommands, and the empirical
(real-transcript) leg's own aggregation — later steps in this slice. This
module already imports `session_log.records` (below) so those later steps
share the same sys.path setup rather than re-deriving it.

Monorepo-only by design (ADR 0032 category 2, docs/adr/0032-shipped-script-
path-resolution-taxonomy.md), same as `measure_full_file_duplication.py`:
this is a one-off measurement tool for this marketplace repo's own
`/code-review`/`/build` cost question, not `/code-review`-invoked skill
machinery.

Import boundary: adds `plugins/dev-team/scripts/` (and its `lib/` sibling)
to `sys.path` to import `select_lenses` and `session_log.records`, the SAME
pattern `measure_full_file_duplication.py` uses and for the same reason —
the estimate is only meaningful against the SAME gate `/code-review`/
`/build` themselves apply. `select_lenses` touches only its public
`applicable_lenses`; no private-surface reach.

Additionally inserts this script's OWN directory
(`sys.path.insert(0, str(Path(__file__).resolve().parent))`) before
`import measure_full_file_duplication` — the same same-directory
sibling-script pattern `scripts/eval_variance.py` already uses to import
`scripts/eval_grade.py`. This is needed because
`tests/scripts/test_measure_rereview_duplication.py` loads THIS module via
`importlib.util.spec_from_file_location`, which does not inherit the
CLI-execution `sys.path[0]` convenience a normal `python3 scripts/
measure_rereview_duplication.py` invocation gets for free, and `pytest.ini`'s
`pythonpath` list does not include repo-root `scripts/` — without this
insert, the plain `import measure_full_file_duplication` statement below
would fail only under the test's loading mechanism, not when this script is
run directly.

Stdlib-only.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_PLUGIN_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
if str(_PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SCRIPTS_DIR))

import select_lenses

_PLUGIN_SCRIPTS_LIB_DIR = _PLUGIN_SCRIPTS_DIR / "lib"
if str(_PLUGIN_SCRIPTS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SCRIPTS_LIB_DIR))
# Not used by this step's own algorithm (the theoretical leg needs no
# transcript) -- imported now, per this sys.path setup being shared, for the
# `empirical` subcommand a later step in this slice adds.
from session_log import records as session_log_records  # noqa: F401

# Same-directory sibling-script import -- see module docstring's "Import
# boundary" section for why this insert is required (not merely
# convenient) for the paired test's loading mechanism.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_full_file_duplication as mfd


class CheckpointResolutionError(RuntimeError):
    """A checkpoint's baseline or head sha could not be resolved in this
    repository (`git rev-parse`/`git show` non-zero). Raised for the WHOLE
    invocation, before `find_theoretical_duplicates` returns anything -- see
    that function's docstring for why no partial result is ever produced."""


class Checkpoint(NamedTuple):
    """One resolved `--checkpoint <baseline>:<head>[:<label>]` argument.

    `baseline`/`head` are git commit-ish strings (usually full or
    abbreviated shas); `label` is a caller-facing name for error messages
    and duplicate provenance, defaulting to `"<baseline>..<head>"` when the
    caller's spec omits it.
    """

    baseline: str
    head: str
    label: str


def parse_checkpoint_spec(spec: str) -> Checkpoint:
    """Parse one `<baseline_sha>:<head_sha>[:<label>]` CLI argument.

    `label` is optional; a caller-supplied third segment (even if it
    happens to be empty) falls back to the same `"<baseline>..<head>"`
    default an omitted segment gets, so a trailing bare `:` never produces
    a blank label.
    """
    parts = spec.split(":", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"invalid --checkpoint {spec!r}: expected "
            "<baseline_sha>:<head_sha>[:<label>]"
        )
    baseline, head = parts[0], parts[1]
    label = parts[2] if len(parts) == 3 and parts[2] else f"{baseline}..{head}"
    return Checkpoint(baseline=baseline, head=head, label=label)


def _run_git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess:
    # check=False: a non-zero exit is a normal, checked-by-the-caller
    # outcome here (an unresolvable sha, a file missing at a given head),
    # not a bug to raise on.
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, check=False)


def _resolve_commit(sha: str, checkpoint_label: str, repo_root: Path) -> None:
    """Raise `CheckpointResolutionError`, naming `sha` and
    `checkpoint_label`, if `sha` does not resolve to a commit in
    `repo_root`. `--verify --quiet` covers both possible causes (not found,
    or found but not a valid commit-ish object) without distinguishing
    them further -- git itself does not reliably tell them apart either."""
    result = _run_git(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"], repo_root)
    if result.returncode != 0:
        raise CheckpointResolutionError(
            f"checkpoint {checkpoint_label!r}: sha {sha!r} could not be "
            "resolved in this repository (not found, or not a valid git "
            "commit object)"
        )


def _diff_name_status(baseline: str, head: str, repo_root: Path) -> dict[str, str]:
    """`{file_path: status_code}` for every file that differs between
    `baseline` and `head` (cumulative, never a single commit's own
    self-diff). A rename/copy row's NEW path is used as the key -- that is
    the path that exists at `head` and what a reviewer actually sees."""
    result = _run_git(["diff", "--name-status", f"{baseline}..{head}"], repo_root)
    status: dict[str, str] = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status[fields[-1]] = fields[0]
    return status


def _file_content_hash(head: str, file_path: str, repo_root: Path) -> tuple[str, int] | None:
    """sha256 hex digest and byte count of `file_path` as it exists at
    `head`, or `None` if `head` has no content for it there (e.g. the file
    was deleted within this checkpoint's range). A missing-at-head file is
    not a hard failure -- there is simply nothing left to hash or record a
    `(lens, file_hash)` pair for."""
    result = _run_git(["show", f"{head}:{file_path}"], repo_root)
    if result.returncode != 0:
        return None
    content = result.stdout
    return hashlib.sha256(content).hexdigest(), len(content)


def checkpoint_lens_file_hashes(checkpoint: Checkpoint, repo_root: Path, roster) -> dict:
    """One checkpoint's `(lenses, file_hashes)` resolution -- factored out
    of `find_theoretical_duplicates` below (Step 1.1 REFACTOR) so it and the
    `report` subcommand a later step in this slice adds can both call this
    without re-deriving the git plumbing twice.

    Resolves the checkpoint's cumulative file set (`git diff --name-status
    baseline..head`, never a single commit's own self-diff) and its
    `added_files` subset (status `A`) in the same pass, then runs
    `select_lenses.applicable_lenses` against that whole file set -- giving
    it `added_files` so a `Scope: added-only` lens is evaluated freshly per
    checkpoint rather than once globally -- and hashes each file's content
    at `head`.

    Raises `CheckpointResolutionError` if `checkpoint.baseline` or
    `checkpoint.head` does not resolve in `repo_root`.

    Returns `{"label": str, "lenses": [...], "warnings": [...],
    "files": {file_path: {"hash": str, "bytes": int}}}` -- `files` holds
    only the checkpoint's changed paths whose content actually resolved at
    `head` (a path deleted within the checkpoint's range is in the diff's
    file set but has nothing to hash, so it is simply absent here).
    """
    _resolve_commit(checkpoint.baseline, checkpoint.label, repo_root)
    _resolve_commit(checkpoint.head, checkpoint.label, repo_root)

    status = _diff_name_status(checkpoint.baseline, checkpoint.head, repo_root)
    file_set = sorted(status)
    added_files = {f for f, code in status.items() if code.startswith("A")}

    lenses, warnings = select_lenses.applicable_lenses(file_set, roster, added_files=added_files)

    files: dict[str, dict] = {}
    for f in file_set:
        hashed = _file_content_hash(checkpoint.head, f, repo_root)
        if hashed is not None:
            file_hash, byte_count = hashed
            files[f] = {"hash": file_hash, "bytes": byte_count}

    return {
        "label": checkpoint.label,
        "lenses": lenses,
        "warnings": warnings,
        "files": files,
    }


def find_theoretical_duplicates(checkpoints: list[Checkpoint], repo_root: Path, roster) -> dict:
    """The theoretical leg's core cross-checkpoint dedup algorithm.

    Processes `checkpoints` strictly in the given list order (the caller's
    responsibility -- chronological order is never inferred here), resolving
    each via `checkpoint_lens_file_hashes` above. Every `(lens, file_hash)`
    pair is tracked by the first checkpoint it is seen at; a later
    occurrence of the SAME pair is a duplicate. A lens simply not being in a
    later checkpoint's applicable-lens set means no entry is ever recorded
    for it there -- no special-case branch, a structural consequence of the
    recording rule above.

    Raises `CheckpointResolutionError` -- and returns nothing -- the moment
    any checkpoint's baseline or head fails to resolve, so a caller can
    never mistake a partial run for a clean one over fewer checkpoints.

    Returns `{"checkpoints": [...], "duplicates": [...],
    "avoidable_tokens_estimate": int}`.
    """
    first_seen: dict[tuple[str, str], str] = {}
    checkpoint_rows: list[dict] = []
    duplicates: list[dict] = []
    total_avoidable_tokens = 0

    for checkpoint in checkpoints:
        resolved = checkpoint_lens_file_hashes(checkpoint, repo_root, roster)
        checkpoint_rows.append(
            {
                "label": resolved["label"],
                "file_set": sorted(resolved["files"]),
                "lenses": resolved["lenses"],
                "warnings": resolved["warnings"],
            }
        )

        for lens in resolved["lenses"]:
            for file_path, info in resolved["files"].items():
                key = (lens, info["hash"])
                if key in first_seen:
                    avoidable = mfd.estimate_tokens(info["bytes"])
                    total_avoidable_tokens += avoidable
                    duplicates.append(
                        {
                            "lens": lens,
                            "file": file_path,
                            "file_hash": info["hash"],
                            "first_seen_at": first_seen[key],
                            "duplicate_at": resolved["label"],
                            "avoidable_tokens_estimate": avoidable,
                        }
                    )
                else:
                    first_seen[key] = resolved["label"]

    return {
        "checkpoints": checkpoint_rows,
        "duplicates": duplicates,
        "avoidable_tokens_estimate": total_avoidable_tokens,
    }
