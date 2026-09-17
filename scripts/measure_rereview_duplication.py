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

CLI (Step 1.2): `theoretical --checkpoint <baseline_sha>:<head_sha>[:<label>]
[--checkpoint ...] [--agents-dir] [--registry] [--repo-root]` (repeatable,
each argument becomes one `Checkpoint` in that same caller-given order;
prints `find_theoretical_duplicates`'s own result, plus `roster_warnings`,
to stdout as JSON — the process exits non-zero with a stderr message,
naming the failing sha and checkpoint, on `CheckpointResolutionError` rather
than a raw traceback) and `empirical --transcript <path> [--since]
[--gap-seconds]` (reuses `mfd.collect_agent_dispatches` and
`mfd.filter_since` directly; refuses — rather than silently reporting zero
spend for — a `--transcript` path that does not exist; prints real
per-dispatch input-token spend grouped by agent type to stdout as JSON).
Privacy boundary mirrors `measure_full_file_duplication.py`'s own exactly:
only `timestamp`, numeric `usage.*` fields, `isSidechain`, `agentId`,
`attributionAgent`, and `meta.agentType` are ever read from a transcript;
nothing is persisted to disk by this script itself.

Deliberately out of scope for Step 1.2: the `report`/`rollup` argparse
subcommands — a later step in this slice. This module already imports
`session_log.records` (below) so that later step shares the same sys.path
setup rather than re-deriving it.

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
`applicable_lenses` and `test_file_subset`; no private-surface reach.

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

import argparse
import hashlib
import json
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
    # not a bug to raise on -- every caller that can silently misinterpret
    # a failure as "no output" (currently `_diff_name_status`) must check
    # `returncode` itself.
    #
    # `-c core.quotePath=false`: without it, git C-quotes a non-ASCII path
    # in `--name-status` output (e.g. `"caf\303\251.py"`, literal quotes
    # included), which breaks `select_lenses` glob matching (the suffix
    # check fails against the quoted string) and `git show <head>:<path>`
    # (the quoted string is not a real path, so the lookup silently returns
    # nothing). Same fix, same reasoning as `changed_file_list.py`'s
    # documented `-c core.quotePath=false` mandate for this pipeline.
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo_root), *args],
        capture_output=True,
        check=False,
    )


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


def _diff_name_status(baseline: str, head: str, checkpoint_label: str, repo_root: Path) -> dict[str, str]:
    """`{file_path: status_code}` for every file that differs between
    `baseline` and `head` (cumulative, never a single commit's own
    self-diff). A rename/copy row's NEW path is used as the key -- that is
    the path that exists at `head` and what a reviewer actually sees.

    Both shas are already resolved by `_resolve_commit` before this runs, so
    a non-zero exit here means something else went wrong (a corrupt object,
    a permissions error, an interrupted process) -- checked explicitly and
    raised on, rather than read as an empty (and therefore falsely
    "clean") diff, per this module's own "no partial result mistaken for a
    clean run" rule (see module docstring)."""
    result = _run_git(["diff", "--name-status", f"{baseline}..{head}"], repo_root)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise CheckpointResolutionError(
            f"checkpoint {checkpoint_label!r}: `git diff --name-status "
            f"{baseline}..{head}` failed: {stderr}"
        )
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
    checkpoint rather than once globally, and `test_files` (via
    `select_lenses.test_file_subset`, the same call `select_lenses.py`'s own
    CLI makes) so a `Scope: test-files` lens is narrowed to checkpoints that
    actually changed a test file rather than counted as applicable at every
    checkpoint (`test_files=None` means "no classification offered, include
    unconditionally" to `applicable_lenses` -- not "no test files") -- and
    hashes each file's content at `head`.

    Raises `CheckpointResolutionError` if `checkpoint.baseline` or
    `checkpoint.head` does not resolve in `repo_root`, or if the
    `git diff --name-status` call itself fails.

    Returns `{"label": str, "lenses": [...], "warnings": [...],
    "files": {file_path: {"hash": str, "bytes": int}}}` -- `files` holds
    only the checkpoint's changed paths whose content actually resolved at
    `head` (a path deleted within the checkpoint's range is in the diff's
    file set but has nothing to hash, so it is simply absent here).
    """
    _resolve_commit(checkpoint.baseline, checkpoint.label, repo_root)
    _resolve_commit(checkpoint.head, checkpoint.label, repo_root)

    status = _diff_name_status(checkpoint.baseline, checkpoint.head, checkpoint.label, repo_root)
    file_set = sorted(status)
    added_files = {f for f, code in status.items() if code.startswith("A")}
    test_files = select_lenses.test_file_subset(file_set, root=repo_root)

    lenses, warnings = select_lenses.applicable_lenses(
        file_set, roster, added_files=added_files, test_files=test_files
    )

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


def _check_lens_file_pair(
    lens: str, file_path: str, info: dict, first_seen: dict[tuple[str, str], str], checkpoint_label: str
) -> dict | None:
    """Check one `(lens, file_path, info)` triple against `first_seen` (the
    pairs recorded at EARLIER checkpoints only -- never this checkpoint's
    own, see `find_theoretical_duplicates`). Returns a duplicate row dict if
    `(lens, info["hash"])` was already seen, else `None`. Never mutates
    `first_seen` -- recording a newly-seen pair is the caller's job, and
    only after this checkpoint's own loop over every `(lens, file)` pair has
    finished, so two different files with identical content within the SAME
    checkpoint are never scored as a duplicate of each other."""
    key = (lens, info["hash"])
    if key not in first_seen:
        return None
    return {
        "lens": lens,
        "file": file_path,
        "file_hash": info["hash"],
        "first_seen_at": first_seen[key],
        "duplicate_at": checkpoint_label,
        "avoidable_tokens_estimate": mfd.estimate_tokens(info["bytes"]),
    }


def find_theoretical_duplicates(checkpoints: list[Checkpoint], repo_root: Path, roster) -> dict:
    """The theoretical leg's core cross-checkpoint dedup algorithm.

    Processes `checkpoints` strictly in the given list order (the caller's
    responsibility -- chronological order is never inferred here), resolving
    each via `checkpoint_lens_file_hashes` above. Every `(lens, file_hash)`
    pair is tracked by the first checkpoint it is seen at; a later
    occurrence of the SAME pair, at a DIFFERENT checkpoint, is a duplicate.
    A lens simply not being in a later checkpoint's applicable-lens set
    means no entry is ever recorded for it there -- no special-case branch,
    a structural consequence of the recording rule above.

    A checkpoint's own newly-seen `(lens, file_hash)` pairs are recorded
    into `first_seen` only AFTER that checkpoint's entire loop finishes
    (`newly_seen`, merged below) -- never live, mid-loop. Two different
    files with byte-identical content added within the SAME checkpoint
    therefore never produce a duplicate row against each other: this tool
    measures cross-checkpoint re-review, not same-checkpoint coincidental
    content collisions.

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

        newly_seen: dict[tuple[str, str], str] = {}
        for lens in resolved["lenses"]:
            for file_path, info in resolved["files"].items():
                dup = _check_lens_file_pair(lens, file_path, info, first_seen, resolved["label"])
                if dup is not None:
                    total_avoidable_tokens += dup["avoidable_tokens_estimate"]
                    duplicates.append(dup)
                else:
                    key = (lens, info["hash"])
                    newly_seen.setdefault(key, resolved["label"])
        first_seen.update(newly_seen)

    return {
        "checkpoints": checkpoint_rows,
        "duplicates": duplicates,
        "avoidable_tokens_estimate": total_avoidable_tokens,
    }


# ---------------------------------------------------------------------------
# CLI (Step 1.2): `theoretical` and `empirical` subcommands.
# ---------------------------------------------------------------------------


def aggregate_spend_by_agent_type(dispatches: list[dict]) -> dict[str, dict]:
    """`agent_type -> {"total_input_tokens": int, "n_dispatches": int}` --
    the real per-dispatch input-token spend the `empirical` subcommand
    reports, grouped the same way a later `report` subcommand (step 1.3)
    will need it to compute a real average per-dispatch spend per agent
    type (`total_input_tokens / n_dispatches`)."""
    aggregated: dict[str, dict] = {}
    for dispatch in dispatches:
        bucket = aggregated.setdefault(
            dispatch["agent_type"], {"total_input_tokens": 0, "n_dispatches": 0}
        )
        bucket["total_input_tokens"] += dispatch["input_spend"]
        bucket["n_dispatches"] += 1
    return aggregated


def cmd_theoretical(args: argparse.Namespace) -> int:
    checkpoints = [parse_checkpoint_spec(spec) for spec in args.checkpoint]
    roster, roster_warnings = select_lenses.build_review_roster(args.agents_dir, args.registry)
    try:
        result = find_theoretical_duplicates(checkpoints, args.repo_root, roster)
    except CheckpointResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result["roster_warnings"] = roster_warnings
    print(json.dumps(result, indent=2))
    return 0


def cmd_empirical(args: argparse.Namespace) -> int:
    if not args.transcript.is_file():
        print(
            f"error: --transcript path does not exist: {args.transcript}",
            file=sys.stderr,
        )
        return 1
    dispatches = mfd.filter_since(mfd.collect_agent_dispatches(args.transcript), args.since)
    spend_by_agent_type = aggregate_spend_by_agent_type(dispatches)
    print(json.dumps({"spend_by_agent_type": spend_by_agent_type}, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_theoretical = sub.add_parser(
        "theoretical",
        help="Cross-checkpoint (lens, file_hash) duplicate report, no transcript needed",
    )
    p_theoretical.add_argument(
        "--checkpoint",
        action="append",
        required=True,
        dest="checkpoint",
        metavar="<baseline_sha>:<head_sha>[:<label>]",
        help="Repeatable; processed strictly in the order given",
    )
    p_theoretical.add_argument(
        "--agents-dir", type=Path, default=_PLUGIN_ROOT / "agents"
    )
    p_theoretical.add_argument(
        "--registry", type=Path, default=_PLUGIN_ROOT / "knowledge" / "agent-registry.md"
    )
    p_theoretical.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    p_theoretical.set_defaults(func=cmd_theoretical)

    p_empirical = sub.add_parser(
        "empirical",
        help="Real per-dispatch input-token spend by agent type, from a session transcript",
    )
    p_empirical.add_argument("--transcript", type=Path, required=True)
    p_empirical.add_argument(
        "--since", default=None, help="ISO8601 timestamp; drop earlier dispatches"
    )
    p_empirical.add_argument(
        "--gap-seconds",
        type=float,
        default=mfd.DEFAULT_ROUND_GAP_SECONDS,
        help="Accepted for CLI-shape parity with measure_full_file_duplication.py; "
        "unused by this subcommand's own per-agent-type totals (no round "
        "clustering is performed here).",
    )
    p_empirical.set_defaults(func=cmd_empirical)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
