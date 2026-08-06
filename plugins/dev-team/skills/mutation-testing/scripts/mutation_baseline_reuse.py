#!/usr/bin/env python3
"""Baseline mutation-report reuse for the mutant-kill loop's Round 1 (#1545).

The mutant-kill loop's per-file Round 1 always triggers a fresh scoped
mutation run, even when a fresh baseline report (captured once, before the
per-file loop starts) already covers that file. This module owns the
eligibility decision and the consumption bookkeeping so a file's Round 1 can
be safely seeded from the baseline via ``--report`` instead of paying for a
redundant run — as real, unit-tested code, not agent-followed prose.

Eligibility is a two-part test:
  1. an **ancestor check** — is the file's last commit an ancestor of the
     baseline's capture commit? (git itself treats a commit as its own
     ancestor, so a file last committed exactly at the capture commit is
     eligible too — the "self-ancestor boundary".) A file with no
     discoverable last-commit SHA (untracked/never committed), or a
     non-ancestor relationship, is never eligible.
  2. a **consumption check** — has this file already consumed *this exact*
     baseline capture commit? If so it is not eligible again until a
     different (not-yet-consumed) baseline capture commit comes along.

Concurrency (#1920): ``mark_consumed`` is the sole writer of the tracking
file, and its read-modify-write span is serialized by
``atomic_state.locked_state(strict=True)`` so two concurrent callers can
never lose one another's update to the tracking FILE. ``resolve``/
``read_tracking`` are deliberately lock-free — a stale read there can only
under-count eligibility (miss a consumption recorded moments ago and report
a file eligible when it is about to be marked consumed elsewhere).

That serialization, on its own, does NOT guarantee a file is never
double-consumed: two concurrent ``resolve`` calls for the SAME file would
both observe pre-consumption state and both seed Round 1, regardless of how
serialized ``mark_consumed``'s writes are — serialization protects the
tracking file's integrity across *different* files' writes, not the
ordering between one file's ``resolve`` calls and its own eventual
``mark_consumed``. The "never double-consume" property this module relies
on instead comes from an explicit assumption held by its callers: each file
is resolved and consumed by at most one worker per run (the ``--all``
fan-out assigns files disjointly across workers, so two workers never race
on the same file to begin with).

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import mutation_report

# skills/mutation-testing/scripts -> skills/mutation-testing -> skills
# -> plugin root -> hooks/lib
_HOOKS_LIB_DIR = Path(__file__).resolve().parents[3] / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import atomic_state  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    atomic_state = None


class _AtomicStateUnavailableError(RuntimeError):
    """Raised by ``mark_consumed`` when ``hooks/lib``'s ``atomic_state``
    module could not be imported — refusing to run the read-modify-write
    cycle unlocked rather than silently proceeding without it."""


# The exception type ``mark_consumed``'s ``except`` clause narrows to
# (#1920 correctness review): ``atomic_state.LockAcquisitionError`` when the
# module imported successfully, or the local fallback above when it didn't.
# Computed once here, at import time, so the ``except`` clause itself never
# has to attribute-access a possibly-``None`` ``atomic_state`` — evaluating
# ``atomic_state.LockAcquisitionError`` directly inside the ``except`` tuple
# would raise ``AttributeError`` instead of matching the real error whenever
# ``atomic_state is None``.
_LOCK_FAILURE_ERROR: type[Exception] = (
    atomic_state.LockAcquisitionError
    if atomic_state is not None
    else _AtomicStateUnavailableError
)


# =============================================================================
# Tracking file — read / decide / write
# =============================================================================
def read_tracking(tracking_path) -> dict:
    """Return the parsed consumption-tracking JSON, or ``{}`` for an
    absent, malformed, or non-dict-shaped file.

    Delegates to ``mutation_report.load_report`` — this module used to
    reimplement that function's absent/empty/malformed-JSON handling itself;
    it now genuinely calls it, so the two stay behaviorally identical by
    construction rather than by convention.
    """
    return mutation_report.load_report(tracking_path)


def is_eligible_for_reuse(
    tracking: dict, file_path: str, capture_commit: str, is_ancestor: bool
) -> bool:
    """Pure eligibility decision.

    ``False`` when the file's last commit is not an ancestor of the
    baseline's capture commit (``is_ancestor`` is the caller's already-
    resolved git ancestor check — this function does no git work itself).
    Otherwise ``False`` only when ``tracking`` already records ``file_path``
    as consumed at this exact ``capture_commit``; ``True`` in every other
    case, including a file consumed at some *other*, older baseline capture
    commit it hasn't yet consumed.
    """
    if not is_ancestor:
        return False
    entry = tracking.get(file_path)
    return entry is None or entry.get("capture_commit") != capture_commit


def mark_consumed(tracking_path, file_path: str, capture_commit: str) -> dict:
    """Atomically record ``file_path``'s consumption of ``capture_commit``.

    The full read-tracking -> mutate-dict -> atomic-write sequence runs
    inside ``atomic_state.locked_state(tracking_path, strict=True)`` (#1920),
    so a second concurrent caller's read can never observe a state older than
    the first caller's completed write — closing the lost-update race two
    processes racing on the same tracking file could otherwise hit. Within
    that lock, writes to a temp file obtained via ``tempfile.mkstemp``
    (mirroring ``atomic_state.atomic_write``'s own idiom in this module
    family) then ``os.replace``s it onto ``tracking_path`` — every other
    file's existing entry in the tracking dict is preserved.

    The temp file is unique-per-call (#1920 correctness review), not a
    fixed, predictable ``<tracking_path>.tmp`` path: a fixed path shared
    across concurrent callers meant a failed call's cleanup could delete a
    *different*, still-in-flight caller's temp file, or fire when this call
    never wrote a temp file at all (e.g. a lock-acquisition failure).
    ``mkstemp``'s ``O_CREAT | O_EXCL`` semantics also mean it refuses to
    open an already-existing path at the generated name — including a
    symlink planted there — so this switch incidentally closes the same
    symlink-follow concern ``atomic_state.append_line_locked`` hardens
    against explicitly (#1889 precedent), with no separate ``O_NOFOLLOW``
    open needed here.

    Never raises: a write failure (permission denied, unwritable directory,
    a monkeypatched ``os.replace`` failure, ...) *or* a failed lock
    acquisition (``strict=True`` raises ``atomic_state.LockAcquisitionError``
    instead of running unlocked — or the local ``_AtomicStateUnavailableError``
    when ``atomic_state`` itself could not be imported) is caught and
    reported as ``{"success": False, "error": str(exc)}``, leaving the
    on-disk file (if any) untouched — the file stays recorded as
    not-yet-consumed. A stray temp file left behind by a failed write is
    best-effort cleaned up — but ONLY the temp file this call itself
    created: ``tmp_name`` is set the moment ``mkstemp`` returns it and stays
    ``None`` before that, so a lock-acquisition failure (which never reaches
    ``mkstemp``) or any other failure before that point triggers no cleanup
    at all, and can never touch a different concurrent caller's in-flight
    temp file. A failure during that cleanup is swallowed so it never masks
    the original error being reported.

    ``resolve``/``read_tracking`` stay lock-free by design — see the module
    docstring's ``Concurrency`` note for why a stale read there is safe, and
    for the explicit assumption behind "never double-consume" (single
    worker per file per run, not serialization alone).
    """
    tracking_path = Path(tracking_path)
    tmp_name: str | None = None
    try:
        if atomic_state is None:
            raise _AtomicStateUnavailableError(
                "atomic_state unavailable (hooks/lib unreachable); refusing "
                "to run mark_consumed's read-modify-write unlocked"
            )
        with atomic_state.locked_state(tracking_path, strict=True):
            tracking = read_tracking(tracking_path)
            tracking[file_path] = {
                "capture_commit": capture_commit,
                "recorded_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{tracking_path.name}-",
                suffix=".tmp",
                dir=str(tracking_path.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(tracking, indent=2))
            os.replace(tmp_name, tracking_path)
    except (OSError, _LOCK_FAILURE_ERROR) as exc:
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink(missing_ok=True)
        return {"success": False, "error": str(exc)}
    return {"success": True}


# =============================================================================
# Git-backed ancestor check
# =============================================================================
def _run_git(args: list[str], *, cwd=None) -> subprocess.CompletedProcess | None:
    """Run a git subcommand, returning ``None`` on a missing git binary, a
    non-repo ``cwd``, or a 30s timeout — never raises."""
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _git_last_commit_sha(file_path, *, cwd=None) -> str | None:
    """Return ``file_path``'s last-commit SHA, or ``None`` when git is
    unavailable (missing binary, not a repo, timeout) or the file has no
    commit history at all (empty ``git log`` result — untracked/never
    committed). Never raises."""
    result = _run_git(
        ["git", "log", "-1", "--format=%H", "--", str(file_path)], cwd=cwd
    )
    if result is None:
        return None
    sha = result.stdout.strip()
    return sha or None


def _git_is_ancestor(commit_a: str, commit_b: str, *, cwd=None) -> bool:
    """True when ``commit_a`` is an ancestor of (or equal to) ``commit_b``
    (``git merge-base --is-ancestor``). ``False`` when git is unavailable
    (missing binary, not a repo, timeout) rather than letting the exception
    propagate. Never raises."""
    result = _run_git(
        ["git", "merge-base", "--is-ancestor", "--", commit_a, commit_b], cwd=cwd
    )
    if result is None:
        return False
    return result.returncode == 0


# =============================================================================
# CLI — resolve / mark-consumed
# =============================================================================
def _resolve(args) -> dict:
    tracking = read_tracking(args.tracking)
    last_commit = _git_last_commit_sha(args.file, cwd=args.cwd)
    is_ancestor = (
        _git_is_ancestor(last_commit, args.capture_commit, cwd=args.cwd)
        if last_commit is not None
        else False
    )
    eligible = is_eligible_for_reuse(
        tracking, args.file, args.capture_commit, is_ancestor
    )
    return {
        "eligible": eligible,
        "file": args.file,
        "capture_commit": args.capture_commit,
    }


def _mark_consumed(args) -> dict:
    return mark_consumed(args.tracking, args.file, args.capture_commit)


def _cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve baseline-reuse eligibility, or mark a file's "
        "consumption of a baseline capture commit."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--file", required=True)
    parent_parser.add_argument("--capture-commit", required=True)
    parent_parser.add_argument("--tracking", required=True)

    resolve_parser = sub.add_parser(
        "resolve",
        help="resolve whether a file may reuse the baseline report",
        parents=[parent_parser],
    )
    resolve_parser.add_argument("--cwd", default=None)

    sub.add_parser(
        "mark-consumed",
        help="record a file's consumption of a baseline",
        parents=[parent_parser],
    )

    args = parser.parse_args(list(argv))

    if args.command == "resolve":
        payload = _resolve(args)
    else:
        payload = _mark_consumed(args)

    print(json.dumps(payload))
    # Exit 0 either way — advisory/informational, matching
    # mutation_feasibility_gate.py's "advisory arbiter, not a gate" convention.
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
