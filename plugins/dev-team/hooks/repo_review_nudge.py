#!/usr/bin/env python3
"""repo_review_nudge — Claude Code SessionStart hook (#1739/#1743/#1746).

`/repo-review` (#1733/#1735) tracks drift in
`.claude/memory/repo-review-state.json` (`{"last_commit", "last_run_at"}`)
but is invoked manually — nothing proactively tells the operator drift has
crossed a threshold worth acting on. This hook is that proactive nudge,
mirroring `pending_review_notify.py`'s shape: read a small state signal,
print a one-line stdout notice, fail-open, stdlib-only.

Drift signal: **percentage of the codebase changed since `last_commit`**,
not an absolute line count, commit count, or elapsed time (#1743). An
absolute line count doesn't scale with repo size — a fixed threshold is
noise for a small repo and meaningless for a huge one; a percentage of the
current codebase is the size-independent version of the same "how much
actually changed" signal #1739 established.

    percentage = added_lines_since_baseline / total_current_loc * 100

Both quantities come from `git diff --numstat <revspec>`, summing only the
added-lines column — matching `change_size.py`'s own established rationale
in this codebase: added lines are unverified, newly introduced content;
deleted lines are comparatively low-risk.

- `total_current_loc`: diffed from git's empty-tree object to HEAD. Every
  line in HEAD is necessarily an "addition" relative to nothing, so this
  doubles as a cheap, accurate current-LOC count with no need to `wc -l`
  every tracked file.
- `added_lines_since_baseline`: baseline is `last_commit` if on record and
  it both passes validation and is still reachable (see below); otherwise
  the empty tree again — which makes "never run" resolve to exactly 100%
  (the whole current codebase is unreviewed) with no special-cased branch.

**Pure percentage fails at both size extremes (#1746)**, so the trigger is
three-part, percentage in the middle with absolute floor/ceiling guards on
either side:

    trigger = added >= MAX_ADDED_LINES
              OR (added >= MIN_ADDED_LINES AND percent >= PERCENT_THRESHOLD)

- **Floor** (`MIN_ADDED_LINES`): below it, never nudge regardless of
  percentage — otherwise a trivial change in a small repo (a few dozen
  lines can already be 10%+ of a tiny codebase) reads as "the codebase
  changed," which is naggy, not useful.
- **Ceiling** (`MAX_ADDED_LINES`): above it, always nudge regardless of
  percentage — otherwise a huge repo's percent threshold could take dozens
  of sessions to reach, and the nudge goes silently dormant exactly where
  drift review matters most.
- Between the two, the percentage rule applies as before.

**`last_commit` is untrusted input, validated before touching any git
command (#1743).** `.claude/memory/repo-review-state.json` is written by
`/repo-review`, but nothing stops a hostile PR from committing its own copy
with an arbitrary string (see `skills/repo-review/SKILL.md`'s own matching
guard) — this hook reads the same file. `last_commit` is never
shell-interpolated (subprocess args, not a shell string), so classic shell
injection doesn't apply, but an unvalidated value starting with `-` could
still be misparsed as a git flag rather than a revspec (argument
injection). Any value not matching `^[0-9a-fA-F]{7,40}$` is treated exactly
like "no prior state".

Env seams (all starting guesses, not empirically measured — no real
cadence data exists yet; override if live usage shows any of them too
tight or too loose):
    DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD  percentage threshold, default 10
    DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES    anti-nagging floor, default 200
    DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES    anti-silence ceiling, default 5000

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
import re
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]

_DEFAULT_THRESHOLD_PERCENT = 10.0
_DEFAULT_MIN_ADDED_LINES = 200
_DEFAULT_MAX_ADDED_LINES = 5000

# Same trust-boundary guard `skills/repo-review/SKILL.md` applies to this
# exact field before it touches any git command (#1743).
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

# The hash of an empty git tree object — identical in every git repository,
# always resolvable, and needs no repo-specific root-commit lookup (which
# can return more than one commit in a history with multiple roots).
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _threshold_percent() -> float:
    """Percentage threshold from DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD,
    falling back to _DEFAULT_THRESHOLD_PERCENT on anything that isn't a
    positive number."""
    raw = os.environ.get("DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD_PERCENT
    return value if value > 0 else _DEFAULT_THRESHOLD_PERCENT


def _min_added_lines() -> int:
    """Anti-nagging floor from DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES,
    falling back to _DEFAULT_MIN_ADDED_LINES on anything that isn't a
    non-negative int."""
    raw = os.environ.get("DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MIN_ADDED_LINES
    return value if value >= 0 else _DEFAULT_MIN_ADDED_LINES


def _max_added_lines() -> int:
    """Anti-silence ceiling from DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES,
    falling back to _DEFAULT_MAX_ADDED_LINES on anything that isn't a
    positive int."""
    raw = os.environ.get("DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ADDED_LINES
    return value if value > 0 else _DEFAULT_MAX_ADDED_LINES


def _should_nudge(percent: float, added: int) -> bool:
    """Three-part trigger (#1746): the ceiling overrides everything (a
    huge absolute change always warrants a nudge, however small a
    percentage it is of a huge repo); short of that, the floor suppresses
    the percentage rule for a trivial absolute change (however large a
    percentage it is of a tiny repo)."""
    if added >= _max_added_lines():
        return True
    if added < _min_added_lines():
        return False
    return percent >= _threshold_percent()


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
    """The recorded `last_commit`, or None for "no prior state" — including
    when the field fails the commit-sha shape check (#1743): the state file
    is untrusted input, not just possibly absent."""
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
    if not isinstance(last_commit, str) or not _COMMIT_SHA_RE.match(last_commit):
        return None
    return last_commit


def _drift_percentage(cwd: str) -> tuple[float, int, int] | None:
    """(percentage, added, total) since the last /repo-review run, or since
    the repository's first commit when there is no prior run, `last_commit`
    fails validation, or it no longer resolves (rewritten history) — all
    read as "never run", which correctly yields exactly 100%. None on git
    failure (unreachable HEAD, corrupt index, git not installed, timeout)."""
    total = _added_lines(cwd, f"{_EMPTY_TREE}..HEAD")
    if total is None or total <= 0:
        return None

    last_commit = _load_last_commit(cwd)
    added = None
    if last_commit is not None:
        added = _added_lines(cwd, f"{last_commit}..HEAD")
    if added is None:
        added = total  # no prior state / unreachable last_commit => "never run"

    return (added / total) * 100, added, total


def _nudge_message(percent: float, added: int, total: int) -> str:
    return (
        f"\U0001f300 ~{percent:.1f}% of the codebase ({added:,} of {total:,} "
        "lines) has changed since the last /repo-review — consider running "
        "it to catch drift no per-diff review sees (file/CLAUDE.md size, "
        "verification debt, component duplication)\n"
    )


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0
    cwd = resolve_cwd(payload)

    if not _is_git_repo(cwd):
        return 0

    result = _drift_percentage(cwd)
    if result is None:
        return 0
    percent, added, total = result
    if not _should_nudge(percent, added):
        return 0

    sys.stdout.write(_nudge_message(percent, added, total))
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a session
        sys.exit(0)
