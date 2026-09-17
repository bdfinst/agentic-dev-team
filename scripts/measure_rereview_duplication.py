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

`report`/`rollup` (Step 1.3): `report --checkpoint <base:head[:label]>
[--checkpoint ...] [--transcript <path>] [--since] [--agents-dir]
[--registry] [--repo-root]` runs the theoretical leg
(`find_theoretical_duplicates`/`checkpoint_lens_file_hashes`, never
re-deriving the git plumbing) and, when `--transcript` is given, computes
each lens's real AVERAGE per-dispatch input spend from that transcript
(`aggregate_spend_by_agent_type`, called as a function, never shelled out)
and substitutes it for the byte estimate on any lens the transcript
actually covers -- a lens the transcript never dispatched keeps the byte
estimate. **This substitution assumes a lens's real dispatch cost is
roughly SIZE-INVARIANT within that lens** -- the SAME flat per-lens average
is applied to a duplicate on a large file and one on a small file,
discarding the file-size sensitivity the byte-based estimate otherwise
has. Every duplicate row in `report`'s output carries a `spend_source`
field (`"measured"` or `"estimated"`) right next to its
`avoidable_tokens_estimate`, and the same assumption is restated verbatim
in the output's own `spend_source_assumption` field so a reader never has
to infer it. `avoidable_pct_of_total` mirrors
`measure_full_file_duplication.py`'s own `avoidable_pct_of_round_total_
estimate` shape: `avoidable / total * 100`, where `total` here is every
`(lens, file)` occurrence this run resolved (first-seen AND duplicate),
the theoretical-leg analogue of a round's own real total input spend --
`0.0`, never a division error, when that total is zero. `report` prints
its JSON to **stdout only** — it never writes a file itself; a caller
wanting `rollup` to consume it redirects (`report ... > run1.json`).
`rollup --reports <path1.json> <path2.json> ...` reads several `report`
JSON files from disk -- the ONLY subcommand inputs this script reads from
a caller-supplied file path, as distinct from every subcommand's own
stdout-only output -- refuses (exits non-zero, never silently drops) any
path that is not valid JSON, and prints the public `percentile_
distribution` (imported from `measure_full_file_duplication`, not the
underscored alias) over each run's `avoidable_pct_of_total`, plus a
`THRESHOLD_PCT = 5.0`-gated `"recommendation"` field (`"proceed"` when the
median is `>=` the threshold, `"do-not-proceed"` otherwise) computed in
code so it is never mis-eyeballed.

Monorepo-only by design (ADR 0032 category 2, docs/adr/0032-shipped-script-
path-resolution-taxonomy.md), same as `measure_full_file_duplication.py`:
this is a one-off measurement tool for this marketplace repo's own
`/code-review`/`/build` cost question, not `/code-review`-invoked skill
machinery.

Import boundary: adds `plugins/dev-team/scripts/` to `sys.path` to import
`select_lenses`, the SAME pattern `measure_full_file_duplication.py` uses
and for the same reason — the estimate is only meaningful against the SAME
gate `/code-review`/`/build` themselves apply. `select_lenses` touches only
its public `applicable_lenses`, `test_file_subset`, and
`build_review_roster` (the CLI's own roster resolution, `theoretical` and
`report`); no private-surface reach.

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


def _checkpoint_row(resolved: dict) -> dict:
    """The public `checkpoints` row shape (`label`/`file_set`/`lenses`/
    `warnings`) built from one `checkpoint_lens_file_hashes` resolution --
    shared by `find_theoretical_duplicates` and `build_report` so both
    derive it from the SAME resolution rather than each re-deriving it (and,
    for `build_report`, re-resolving the checkpoint's git plumbing a second
    time to get there)."""
    return {
        "label": resolved["label"],
        "file_set": sorted(resolved["files"]),
        "lenses": resolved["lenses"],
        "warnings": resolved["warnings"],
    }


def _process_checkpoint_pairs(
    resolved: dict, first_seen: dict[tuple[str, str], str]
) -> tuple[list[dict], dict[tuple[str, str], str], int]:
    """One checkpoint's `lens x file` cross product against `first_seen`
    (pairs recorded at EARLIER checkpoints only) -- extracted out of
    `_resolve_checkpoints_with_duplicates`'s own loop to keep that function
    at a readable nesting depth, the same extraction `_checkpoint_total_
    tokens` already applies to its own lens x file double-loop elsewhere in
    this file.

    Returns `(duplicates, newly_seen, avoidable_tokens)` for THIS checkpoint
    only. `newly_seen` is NOT merged into `first_seen` here -- the caller
    merges it into `first_seen` only after this checkpoint's entire loop has
    finished, per `_resolve_checkpoints_with_duplicates`'s own "never live,
    mid-loop" rule (see that function's docstring).
    """
    duplicates: list[dict] = []
    newly_seen: dict[tuple[str, str], str] = {}
    avoidable_tokens = 0
    for lens in resolved["lenses"]:
        for file_path, info in resolved["files"].items():
            dup = _check_lens_file_pair(lens, file_path, info, first_seen, resolved["label"])
            if dup is not None:
                avoidable_tokens += dup["avoidable_tokens_estimate"]
                duplicates.append(dup)
            else:
                key = (lens, info["hash"])
                newly_seen.setdefault(key, resolved["label"])
    return duplicates, newly_seen, avoidable_tokens


def _resolve_checkpoints_with_duplicates(checkpoints: list[Checkpoint], repo_root: Path, roster) -> dict:
    """Resolve every checkpoint EXACTLY ONCE (`checkpoint_lens_file_hashes`)
    and run the cross-checkpoint dedup algorithm over the result in the same
    pass -- the single git-resolution source both `find_theoretical_
    duplicates` (theoretical leg's public shape) and `build_report` (which
    additionally needs each file's byte count for `total_tokens_estimate`)
    build from, so a checkpoint's git plumbing (`rev-parse` x2, `diff
    --name-status`, one `git show` per changed file) is paid for once per
    call, not once per consumer.

    Processes `checkpoints` strictly in the given list order (the caller's
    responsibility -- chronological order is never inferred here). Every
    `(lens, file_hash)` pair is tracked by the first checkpoint it is seen
    at; a later occurrence of the SAME pair, at a DIFFERENT checkpoint, is a
    duplicate. A lens simply not being in a later checkpoint's
    applicable-lens set means no entry is ever recorded for it there -- no
    special-case branch, a structural consequence of the recording rule
    above.

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

    Returns `{"resolved_checkpoints": [...], "duplicates": [...],
    "avoidable_tokens_estimate": int}` -- `resolved_checkpoints` is the list
    of raw `checkpoint_lens_file_hashes` dicts (label/lenses/warnings/files,
    the LATTER carrying each file's hash+byte info that `_checkpoint_row`
    above discards for the public shape but `build_report` still needs).
    """
    first_seen: dict[tuple[str, str], str] = {}
    resolved_checkpoints: list[dict] = []
    duplicates: list[dict] = []
    total_avoidable_tokens = 0

    for checkpoint in checkpoints:
        resolved = checkpoint_lens_file_hashes(checkpoint, repo_root, roster)
        resolved_checkpoints.append(resolved)

        checkpoint_duplicates, newly_seen, checkpoint_avoidable_tokens = _process_checkpoint_pairs(
            resolved, first_seen
        )
        duplicates.extend(checkpoint_duplicates)
        total_avoidable_tokens += checkpoint_avoidable_tokens
        first_seen.update(newly_seen)

    return {
        "resolved_checkpoints": resolved_checkpoints,
        "duplicates": duplicates,
        "avoidable_tokens_estimate": total_avoidable_tokens,
    }


def find_theoretical_duplicates(checkpoints: list[Checkpoint], repo_root: Path, roster) -> dict:
    """The theoretical leg's core cross-checkpoint dedup algorithm --
    `theoretical`/`report`'s public shape over `_resolve_checkpoints_with_
    duplicates`' single-resolution-per-checkpoint result (see that
    function's docstring for the dedup algorithm itself).

    Returns `{"checkpoints": [...], "duplicates": [...],
    "avoidable_tokens_estimate": int}`.
    """
    core = _resolve_checkpoints_with_duplicates(checkpoints, repo_root, roster)
    return {
        "checkpoints": [_checkpoint_row(r) for r in core["resolved_checkpoints"]],
        "duplicates": core["duplicates"],
        "avoidable_tokens_estimate": core["avoidable_tokens_estimate"],
    }


# ---------------------------------------------------------------------------
# CLI (Step 1.2): `theoretical` and `empirical` subcommands.
# ---------------------------------------------------------------------------


def aggregate_spend_by_agent_type(dispatches: list[dict]) -> dict[str, dict]:
    """`agent_type -> {"total_input_tokens": int, "n_dispatches": int}` --
    the real per-dispatch input-token spend the `empirical` subcommand
    reports, grouped by the transcript's raw `agent_type` spelling
    (plugin-qualified or bare, whichever `collect_agent_dispatches` saw).
    `report`'s `measured_avg_by_lens` (step 1.3) does NOT reuse this raw
    grouping directly -- it re-merges by short name first, since a single
    transcript can carry both spellings of the same lens and raw grouping
    alone would silently drop one spelling's dispatches from the average
    (see `measured_avg_by_lens`'s own docstring)."""
    aggregated: dict[str, dict] = {}
    for dispatch in dispatches:
        bucket = aggregated.setdefault(
            dispatch["agent_type"], {"total_input_tokens": 0, "n_dispatches": 0}
        )
        bucket["total_input_tokens"] += dispatch["input_spend"]
        bucket["n_dispatches"] += 1
    return aggregated


def _parse_checkpoint_specs(specs: list[str]) -> list[Checkpoint] | None:
    """Parse every `--checkpoint` spec via `parse_checkpoint_spec`, the
    try/except `cmd_theoretical` and `cmd_report` otherwise each repeat
    identically. Prints a clean `error: ...` message to stderr and returns
    `None` on the first malformed spec; both callers check for `None` and
    return 1 the same way they did before this was extracted."""
    try:
        return [parse_checkpoint_spec(spec) for spec in specs]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _load_spend_by_agent_type(transcript: Path, since: str | None) -> dict[str, dict] | None:
    """Validate `transcript` exists and `since` parses, then return real
    per-dispatch input-token spend grouped by agent type
    (`aggregate_spend_by_agent_type`) -- the transcript-loading steps
    `cmd_empirical` and `cmd_report` otherwise both repeat identically.
    Prints a clean `error: ...` message to stderr and returns `None` on
    either failure; both callers check for `None` and return 1 the same way
    they did before this was extracted."""
    if not transcript.is_file():
        print(
            f"error: --transcript is not a readable file: {transcript}",
            file=sys.stderr,
        )
        return None
    try:
        dispatches = mfd.filter_since(mfd.collect_agent_dispatches(transcript), since)
    except ValueError:
        print(f"error: invalid --since value: {since!r}", file=sys.stderr)
        return None
    return aggregate_spend_by_agent_type(dispatches)


def cmd_theoretical(args: argparse.Namespace) -> int:
    checkpoints = _parse_checkpoint_specs(args.checkpoint)
    if checkpoints is None:
        return 1
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
    spend_by_agent_type = _load_spend_by_agent_type(args.transcript, args.since)
    if spend_by_agent_type is None:
        return 1
    print(json.dumps({"spend_by_agent_type": spend_by_agent_type}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI (Step 1.3): `report` and `rollup` subcommands.
# ---------------------------------------------------------------------------

#: Go/no-go anchor for `rollup`'s code-computed `recommendation` (plan's own
#: Goal section): median `avoidable_pct_of_total` >= this is "proceed".
#: Exactly 5.0% counts as `>=`. A provisional anchor borrowed from #1618's
#: orthogonal same-round question, not independently derived for this
#: cross-round one -- advisory input to the epic owner's own call, not a
#: binding trigger (see the plan's Go/no-go threshold section).
THRESHOLD_PCT = 5.0

#: Restated verbatim in every `report` output (next to `spend_source`) so a
#: reader of the #2164 comment sees the assumption, not just infers it from
#: this module's docstring.
_SPEND_SOURCE_ASSUMPTION = (
    "spend_source: 'measured' applies a flat per-lens average real dispatch "
    "cost from the transcript, assumed roughly size-invariant within that "
    "lens -- the same average is used for a duplicate on a large file and "
    "one on a small file. 'estimated' uses the byte-based per-file estimate "
    "instead, for any lens the transcript never dispatched."
)


def _short_agent_type(agent_type: str) -> str:
    """`dev-team:correctness-review` -> `correctness-review` -- mirrors
    `measure_full_file_duplication._short_name`'s own logic locally rather
    than importing it: that helper is private to `mfd` and step 1.1's alias
    fix deliberately scoped the new public surface to `parse_iso`/
    `filter_since`/`percentile_distribution` only, not this one. Needed so a
    transcript's plugin-qualified `agent_type` (e.g. from `.meta.json`'s
    `agentType`) can be matched against this roster's unqualified lens
    names."""
    return agent_type.rsplit(":", 1)[-1]


def measured_avg_by_lens(spend_by_agent_type: dict[str, dict]) -> dict[str, float]:
    """`{lens_name: average_input_tokens_per_dispatch}`, from `aggregate_
    spend_by_agent_type`'s own per-agent-type totals, keyed by the
    UNQUALIFIED lens name (`_short_agent_type`) so a lens the transcript
    covers can be looked up directly against `select_lenses`'s own
    lens-name convention.

    Normalizes with `_short_agent_type` BEFORE grouping, not after: a
    single transcript can carry both a plugin-qualified spelling (e.g.
    `dev-team:correctness-review`) and a bare spelling
    (`correctness-review`) for the SAME lens -- `measure_full_file_
    duplication.py`'s own dispatch collector produces one or the other
    depending on whether a `.meta.json` sidecar exists for a given agent
    instance. Shortening after `aggregate_spend_by_agent_type` has already
    grouped by the raw type would collapse both spellings onto one dict key
    (last-wins), silently discarding one spelling's dispatches from the
    average -- so same-short-name buckets are merged (summed) here, before
    any division happens.

    A lens is only "measured" when it both had at least one dispatch AND
    accumulated real spend (`total_input_tokens > 0`). A bucket with zero
    recorded spend exists only when this script could not fully parse that
    lens's dispatch records -- treating it as "measured" would silently
    report a confident-looking `0.0` `avoidable_tokens_estimate` for every
    duplicate on that lens instead of falling back to the byte estimate,
    UNDER-reporting `avoidable_pct_of_total`."""
    merged: dict[str, dict] = {}
    for agent_type, bucket in spend_by_agent_type.items():
        short = _short_agent_type(agent_type)
        merged_bucket = merged.setdefault(short, {"total_input_tokens": 0, "n_dispatches": 0})
        merged_bucket["total_input_tokens"] += bucket["total_input_tokens"]
        merged_bucket["n_dispatches"] += bucket["n_dispatches"]
    return {
        lens: bucket["total_input_tokens"] / bucket["n_dispatches"]
        for lens, bucket in merged.items()
        if bucket["n_dispatches"] > 0 and bucket["total_input_tokens"] > 0
    }


def _occurrence_tokens(lens: str, byte_count: int, avg_by_lens: dict[str, float]) -> tuple[float, str]:
    """The occurrence-cost rule shared by `build_report`'s per-duplicate
    loop and `_checkpoint_total_tokens`'s own per-(lens, file) total: use
    the measured per-lens average real dispatch cost when the transcript
    covers `lens` (a key in `avg_by_lens`), else fall back to the
    byte-based estimate (`mfd.estimate_tokens`). Named once here so the
    numerator (`build_report`'s duplicates) and the denominator
    (`_checkpoint_total_tokens`'s totals) are provably applying the
    IDENTICAL rule rather than two independently-drifting copies of it.

    Pure DRY/structure fix -- does not change the arithmetic either call
    site already produced. Not a fix for #2183 (the separate, deeper
    per-dispatch-vs-per-file cost-attribution question), which is
    intentionally left alone here.

    Returns `(tokens, spend_source)`, `spend_source` being `"measured"` or
    `"estimated"` -- the same two values `build_report`'s own
    `spend_source` field already carries.
    """
    if lens in avg_by_lens:
        return avg_by_lens[lens], "measured"
    return mfd.estimate_tokens(byte_count), "estimated"


def build_report(
    checkpoints: list[Checkpoint],
    repo_root: Path,
    roster,
    spend_by_agent_type: dict[str, dict] | None,
) -> dict:
    """The `report` subcommand's own combining logic (Step 1.3): the
    theoretical leg's cross-checkpoint duplicate set
    (`find_theoretical_duplicates`), plus -- when `spend_by_agent_type` is
    given (the `empirical` leg's own `aggregate_spend_by_agent_type` output,
    called as a function, never shelled out) -- a real average per-dispatch
    input-token substitution for any lens the transcript actually covers.

    ASSUMPTION (see `_SPEND_SOURCE_ASSUMPTION`, restated in the returned
    dict): this substitution treats a covered lens's real dispatch cost as
    roughly SIZE-INVARIANT within that lens -- the SAME flat per-lens
    average is applied to a duplicate on a large file and one on a small
    file. A lens the transcript never dispatched keeps the byte-based
    estimate, tagged accordingly.

    `avoidable_pct_of_total` mirrors `measure_full_file_duplication.py`'s
    own `avoidable_pct_of_round_total_estimate` shape (`_round_report_row`):
    `avoidable / total * 100`, where `total` here is the summed
    per-occurrence cost across EVERY `(lens, file)` occurrence this run
    resolved (first-seen AND duplicate) -- the theoretical leg's analogue of
    a round's own real total input spend, since no ledger exists yet
    (#2164 slices 1-2) to read a real per-checkpoint total from directly.
    Resolves each checkpoint's git plumbing exactly ONCE, via
    `_resolve_checkpoints_with_duplicates` (shared with `find_theoretical_
    duplicates`), and derives both the duplicate list and this total from
    that single resolution -- rather than calling `find_theoretical_
    duplicates` as an opaque black box and then re-resolving every
    checkpoint a second time just to get each file's byte count. `0.0`,
    never a division error, when that total is zero.

    Raises `CheckpointResolutionError` -- propagated from
    `_resolve_checkpoints_with_duplicates`/`checkpoint_lens_file_hashes` --
    the moment any checkpoint's baseline or head fails to resolve.
    """
    avg_by_lens = measured_avg_by_lens(spend_by_agent_type) if spend_by_agent_type else {}
    core = _resolve_checkpoints_with_duplicates(checkpoints, repo_root, roster)

    # `(checkpoint_label, file_path) -> byte_count`, so each duplicate row
    # (which only carries `duplicate_at`/`file`, not the raw byte count) can
    # look up the byte count `_occurrence_tokens` needs without re-deriving
    # any git plumbing or changing the theoretical leg's own row shape.
    bytes_by_checkpoint_file = {
        (resolved["label"], file_path): info["bytes"]
        for resolved in core["resolved_checkpoints"]
        for file_path, info in resolved["files"].items()
    }

    duplicates: list[dict] = []
    avoidable_tokens_estimate = 0.0
    for dup in core["duplicates"]:
        byte_count = bytes_by_checkpoint_file[(dup["duplicate_at"], dup["file"])]
        tokens, spend_source = _occurrence_tokens(dup["lens"], byte_count, avg_by_lens)
        avoidable_tokens_estimate += tokens
        duplicates.append({**dup, "avoidable_tokens_estimate": tokens, "spend_source": spend_source})

    total_tokens_estimate = sum(
        _checkpoint_total_tokens(resolved, avg_by_lens) for resolved in core["resolved_checkpoints"]
    )

    avoidable_pct_of_total = (
        round(100 * avoidable_tokens_estimate / total_tokens_estimate, 2)
        if total_tokens_estimate
        else 0.0
    )

    return {
        "checkpoints": [_checkpoint_row(r) for r in core["resolved_checkpoints"]],
        "duplicates": duplicates,
        "avoidable_tokens_estimate": avoidable_tokens_estimate,
        "total_tokens_estimate": total_tokens_estimate,
        "avoidable_pct_of_total": avoidable_pct_of_total,
        "spend_source_assumption": _SPEND_SOURCE_ASSUMPTION,
    }


def _checkpoint_total_tokens(resolved: dict, avg_by_lens: dict[str, float]) -> float:
    """One checkpoint's contribution to `build_report`'s `total_tokens_
    estimate`: the summed per-(lens, file) occurrence cost across that
    checkpoint's whole applicable-lens x file-set cross product -- the
    measured average when the lens is covered by the transcript, else the
    byte-based estimate (`_occurrence_tokens`, shared with `build_report`'s
    own per-duplicate loop so the two never independently drift). Extracted
    out of `build_report`'s own loop to keep it at a readable nesting depth
    (the same 4-level-nesting fix step 1.1 already applied elsewhere in this
    file)."""
    total = 0.0
    for lens in resolved["lenses"]:
        for info in resolved["files"].values():
            tokens, _spend_source = _occurrence_tokens(lens, info["bytes"], avg_by_lens)
            total += tokens
    return total


def cmd_report(args: argparse.Namespace) -> int:
    checkpoints = _parse_checkpoint_specs(args.checkpoint)
    if checkpoints is None:
        return 1
    roster, roster_warnings = select_lenses.build_review_roster(args.agents_dir, args.registry)

    spend_by_agent_type = None
    if args.transcript is not None:
        spend_by_agent_type = _load_spend_by_agent_type(args.transcript, args.since)
        if spend_by_agent_type is None:
            return 1

    try:
        result = build_report(checkpoints, args.repo_root, roster, spend_by_agent_type)
    except CheckpointResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result["roster_warnings"] = roster_warnings
    print(json.dumps(result, indent=2))
    return 0


def cmd_rollup(args: argparse.Namespace) -> int:
    percentages: list[float] = []
    for path in args.reports:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"error: --reports path is not valid JSON: {path}: {exc}",
                file=sys.stderr,
            )
            return 1
        if not isinstance(data, dict) or "avoidable_pct_of_total" not in data:
            print(
                f"error: --reports path is missing 'avoidable_pct_of_total': {path}",
                file=sys.stderr,
            )
            return 1
        value = data["avoidable_pct_of_total"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            print(
                f"error: --reports path has a non-numeric 'avoidable_pct_of_total': {path}",
                file=sys.stderr,
            )
            return 1
        percentages.append(value)

    distribution = mfd.percentile_distribution(percentages)
    median_pct = distribution["median_pct"]
    recommendation = "proceed" if median_pct >= THRESHOLD_PCT else "do-not-proceed"
    print(
        json.dumps(
            {
                "distribution": distribution,
                "threshold_pct": THRESHOLD_PCT,
                "recommendation": recommendation,
            },
            indent=2,
        )
    )
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

    p_report = sub.add_parser(
        "report",
        help=(
            "Combine the theoretical leg with real transcript spend where available; "
            "prints JSON to stdout ONLY -- redirect to a file for `rollup` to consume "
            "it (report ... > run1.json)"
        ),
    )
    p_report.add_argument(
        "--checkpoint",
        action="append",
        required=True,
        dest="checkpoint",
        metavar="<baseline_sha>:<head_sha>[:<label>]",
        help="Repeatable; processed strictly in the order given",
    )
    p_report.add_argument(
        "--transcript",
        type=Path,
        default=None,
        help="Optional; omitting it falls back to the byte estimate for every lens",
    )
    p_report.add_argument(
        "--since", default=None, help="ISO8601 timestamp; drop earlier dispatches"
    )
    p_report.add_argument(
        "--agents-dir", type=Path, default=_PLUGIN_ROOT / "agents"
    )
    p_report.add_argument(
        "--registry", type=Path, default=_PLUGIN_ROOT / "knowledge" / "agent-registry.md"
    )
    p_report.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    p_report.set_defaults(func=cmd_report)

    p_rollup = sub.add_parser(
        "rollup",
        help=(
            "min/median/max avoidable_pct_of_total across several `report` JSON files "
            "(read from disk -- the only subcommand inputs this script reads from a "
            "caller-supplied file path), plus a code-computed recommendation"
        ),
    )
    p_rollup.add_argument(
        "--reports",
        type=Path,
        nargs="+",
        required=True,
        help="One or more `report` JSON files (e.g. produced via `report ... > run1.json`)",
    )
    p_rollup.set_defaults(func=cmd_rollup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
