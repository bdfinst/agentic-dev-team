#!/usr/bin/env python3
"""build_rollback_point.py — resolve + record slice rollback points (#865).

A plan's optional slice-level `**Rollback point:**` field is symbolic — a
concrete SHA cannot be known when the plan is written. Values are one of
`slice-start` (default meaning: HEAD at slice dispatch), `wave-start`,
`plan-start`, or an explicit git ref. `/build` resolves the symbolic value
to a concrete SHA at slice dispatch and records it in the slice's build
bookkeeping so a dead-end escalation (issue #864) can name the exact revert
boundary: "revert to <sha> (<symbolic>)".

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SYMBOLIC_VALUES = ("slice-start", "wave-start", "plan-start")


def resolve_rollback_point(
    symbolic: str,
    *,
    repo_root: str,
    slice_start: str | None = None,
    wave_start: str | None = None,
    plan_start: str | None = None,
) -> str:
    """Resolve a symbolic rollback value (or an explicit ref) to a concrete
    commit SHA. Raises `ValueError` if the ref cannot be resolved, and
    `ValueError` if a symbolic value is requested but its anchor ref wasn't
    supplied (the caller — `/build` — always has these three at dispatch
    time)."""
    mapping = {
        "slice-start": slice_start,
        "wave-start": wave_start,
        "plan-start": plan_start,
    }
    if symbolic in mapping:
        ref = mapping[symbolic]
        if not ref:
            raise ValueError(
                f"rollback point '{symbolic}' requires its anchor ref to be supplied"
            )
    else:
        ref = symbolic  # explicit ref, e.g. a SHA or tag

    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"could not resolve ref {ref!r}: {result.stderr.strip()}")
    return result.stdout.strip()


def _load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_rollback_point(path: Path, slice_id: str, symbolic: str, sha: str) -> None:
    """Persist `{slice_id: {"symbolic", "sha", "recorded_at"}}` to `path`,
    merging with any existing entries for other slices."""
    data = _load(path)
    data[slice_id] = {
        "symbolic": symbolic,
        "sha": sha,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def get_rollback_point(path: Path, slice_id: str) -> dict | None:
    """Retrieve the recorded rollback point for `slice_id`, or `None`."""
    return _load(path).get(slice_id)


def _is_ancestor(candidate_sha: str, of_ref: str, repo_root: str) -> bool:
    """True when `candidate_sha` is an ancestor of `of_ref` (or equal to
    it) in `repo_root`'s history — `git merge-base --is-ancestor` exits 0
    for a real ancestor/self, non-zero otherwise (including when either
    ref can't be resolved in this repo at all)."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, of_ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def find_rollback_point_by_symbolic(
    path: Path,
    symbolic: str,
    *,
    repo_root: str | None = None,
    ancestor_of: str | None = None,
) -> dict | None:
    """Find a recorded entry (any slice) whose `symbolic` value matches, or
    `None` if none qualifies.

    Used by `/build` Step 7's degenerate branch-base fallback (issue #916):
    when `git merge-base` resolution collapses to `HEAD` (or fails outright
    — e.g. a single-branch/no-remote repo), the plan-start commit already
    resolved for a `Rollback point: plan-start` slice (issue #865) is a
    trustworthy alternative base, distinct from a ref that merely happens
    to equal `HEAD`.

    `memory/build-rollback.json` is a flat, unscoped store that is never
    cleared between plans or builds sharing a worktree — the first
    `symbolic` match by insertion order could be a stale SHA left behind by
    an unrelated earlier build. When both `repo_root` and `ancestor_of` are
    supplied, a candidate is only accepted when its `sha` is actually an
    ancestor of `ancestor_of` (typically the current `HEAD`) via
    `git merge-base --is-ancestor` — a stale entry from a different branch
    history will not satisfy this and is skipped in favor of the next
    match, or `None` if no entry qualifies. Callers that omit both
    (`repo_root`/`ancestor_of`) get the unfiltered first match, matching
    the CLI default when `--repo`/`--ancestor-of` aren't passed."""
    for entry in _load(path).values():
        if entry.get("symbolic") != symbolic:
            continue
        if repo_root is not None and ancestor_of is not None:
            sha = entry.get("sha")
            if not sha or not _is_ancestor(sha, ancestor_of, repo_root):
                continue
        return entry
    return None


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_rollback_point.py",
        description="Resolve and record a slice's rollback point (issue #865).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    resolve_p = sub.add_parser("resolve", help="Resolve a symbolic value to a SHA.")
    resolve_p.add_argument("--symbolic", required=True)
    resolve_p.add_argument("--repo", default=".")
    resolve_p.add_argument("--slice-start")
    resolve_p.add_argument("--wave-start")
    resolve_p.add_argument("--plan-start")

    record_p = sub.add_parser("record", help="Record a resolved rollback point.")
    record_p.add_argument("--path", type=Path, required=True)
    record_p.add_argument("--slice", required=True)
    record_p.add_argument("--symbolic", required=True)
    record_p.add_argument("--sha", required=True)

    get_p = sub.add_parser("get", help="Retrieve a recorded rollback point.")
    get_p.add_argument("--path", type=Path, required=True)
    get_p.add_argument("--slice", required=True)

    get_by_symbolic_p = sub.add_parser(
        "get-by-symbolic",
        help="Find any recorded rollback point by its symbolic value (issue #916).",
    )
    get_by_symbolic_p.add_argument("--path", type=Path, required=True)
    get_by_symbolic_p.add_argument("--symbolic", required=True)
    get_by_symbolic_p.add_argument(
        "--repo",
        help="Repo root to validate the candidate SHA's ancestry in. "
        "Pair with --ancestor-of to reject stale entries from an unrelated "
        "build sharing this worktree's memory/ store.",
    )
    get_by_symbolic_p.add_argument(
        "--ancestor-of",
        help="Only accept a candidate whose SHA is an ancestor of this ref "
        "(typically HEAD). Requires --repo.",
    )

    args = parser.parse_args(argv)

    if args.command == "resolve":
        try:
            sha = resolve_rollback_point(
                args.symbolic,
                repo_root=args.repo,
                slice_start=args.slice_start,
                wave_start=args.wave_start,
                plan_start=args.plan_start,
            )
        except ValueError as exc:
            sys.stderr.write(f"build-rollback-point: {exc}\n")
            return 2
        print(sha)
        return 0

    if args.command == "record":
        record_rollback_point(args.path, args.slice, args.symbolic, args.sha)
        print(f"Recorded rollback point for slice {args.slice}: {args.sha}")
        return 0

    if args.command == "get":
        entry = get_rollback_point(args.path, args.slice)
        if entry is None:
            sys.stderr.write(
                f"build-rollback-point: no rollback point recorded for slice {args.slice}\n"
            )
            return 1
        print(json.dumps(entry))
        return 0

    if args.command == "get-by-symbolic":
        entry = find_rollback_point_by_symbolic(
            args.path,
            args.symbolic,
            repo_root=args.repo,
            ancestor_of=args.ancestor_of,
        )
        if entry is None:
            sys.stderr.write(
                f"build-rollback-point: no rollback point recorded with symbolic {args.symbolic!r}\n"
            )
            return 1
        print(json.dumps(entry))
        return 0

    return 2  # pragma: no cover — argparse enforces a valid subcommand


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
