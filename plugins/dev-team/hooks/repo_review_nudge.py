#!/usr/bin/env python3
"""repo_review_nudge — Claude Code SessionStart hook (#1739).

`/repo-review` (#1733/#1735) tracks drift in
`.claude/memory/repo-review-state.json` (`{"last_commit", "last_run_at"}`)
but is invoked manually — nothing proactively tells the operator drift has
crossed a threshold worth acting on. This hook is that proactive nudge,
mirroring `pending_review_notify.py`'s shape: read a small state signal,
print a one-line stdout notice, fail-open, stdlib-only.

Drift signal: **added lines since `last_commit`**, not commit count and not
elapsed time — a single commit can carry thousands of added lines, and a
week can pass with none; the drift this skill's roster cares about (file/
CLAUDE.md size, verification debt, component duplication) tracks how much
code actually changed, not how many commits or how much wall-clock it took
to change it. Computed via `git diff --numstat <last_commit>..HEAD`, summing
only the added-lines column — matching `change_size.py`'s own established
rationale in this codebase: added lines are unverified, newly introduced
content; deleted lines are comparatively low-risk. No prior state, or
`last_commit` no longer resolving (rewritten history), both read as "never
run": the signal falls back to added lines from the repository's very first
commit (diffed against git's empty-tree object) to HEAD.

Env seams:
    DEV_TEAM_REPO_REVIEW_LINE_THRESHOLD  added-lines threshold (default
        2000) — a starting guess, not an empirically measured number (no
        real cadence data exists yet); override if live usage shows it's
        too tight or too loose.

Contract (docs/python-hook-contract.md):
    Input : SessionStart JSON on stdin (hook_event_name, cwd, model, ...).
    Output: notification text on stdout. Exit 0 always.
    Posture: fail-open — a buggy notifier must never block a session; this
        hook only ever suggests, it never gates.

Stdlib-only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths

_DEFAULT_THRESHOLD = 2000

# The hash of an empty git tree object — identical in every git repository,
# always resolvable, and needs no repo-specific root-commit lookup (which
# can return more than one commit in a history with multiple roots). Diffing
# against it gives "every added line since the repository began", the
# correct "never run" fallback signal.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _threshold() -> int:
    """Added-lines threshold from DEV_TEAM_REPO_REVIEW_LINE_THRESHOLD,
    falling back to _DEFAULT_THRESHOLD on anything that isn't a positive
    int."""
    raw = os.environ.get("DEV_TEAM_REPO_REVIEW_LINE_THRESHOLD", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD
    return value if value > 0 else _DEFAULT_THRESHOLD


def _is_git_repo(cwd: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _added_lines(cwd: str, revspec: str) -> int | None:
    """Sum of `git diff --numstat <revspec>`'s added-lines column.

    None on any git failure (unreachable ref, corrupt index, git not
    installed, timeout) or on any unparseable line — a binary-file marker
    (`-\t-\tpath`) or a malformed row disqualifies the whole count rather
    than silently under-counting, matching `change_size.py`'s own
    fail-safe-by-construction posture.
    """
    try:
        completed = subprocess.run(
            ["git", "diff", "--numstat", revspec],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None

    total = 0
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            return None
        added_field = parts[0]
        if added_field == "-":  # binary file — no line-count signal
            return None
        try:
            total += int(added_field)
        except ValueError:
            return None
    return total


def _load_last_commit(cwd: str) -> str | None:
    state_file = artifact_paths.resolve_file(
        "memory", "repo-review-state.json", cwd, migrate=False
    )
    if not state_file.is_file():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    last_commit = data.get("last_commit")
    return last_commit if isinstance(last_commit, str) and last_commit else None


def _drift_lines(cwd: str) -> int | None:
    """Added lines since the last /repo-review run, or since the
    repository's first commit when there is no prior run or `last_commit`
    no longer resolves (rewritten history) — both read as "never run".
    None on git failure."""
    last_commit = _load_last_commit(cwd)
    if last_commit is not None:
        count = _added_lines(cwd, f"{last_commit}..HEAD")
        if count is not None:
            return count
    # No prior state, or last_commit didn't resolve — fall back to added
    # lines since the repository began.
    return _added_lines(cwd, f"{_EMPTY_TREE}..HEAD")


def _nudge_message(added: int) -> str:
    return (
        f"\U0001f300 ~{added} added line(s) since the last /repo-review — "
        "consider running it to catch drift no per-diff review sees "
        "(file/CLAUDE.md size, verification debt, component duplication)\n"
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        cwd = os.getcwd()

    if not _is_git_repo(cwd):
        return 0

    added = _drift_lines(cwd)
    if added is None or added < _threshold():
        return 0

    sys.stdout.write(_nudge_message(added))
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a session
        sys.exit(0)
