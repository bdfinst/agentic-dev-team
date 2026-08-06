#!/usr/bin/env python3
"""pre_tool_guard.py — Claude Code PreToolUse hook (Python port of pre-tool-guard.sh).

Runs before Write and Edit tool calls. Blocks writes to sensitive paths
(credentials, secrets, keys). Warns on writes to protected config files.
Enforces freeze-mode's scope lock when a freeze-state file is active.

Input : JSON on stdin with `tool_input.file_path` or `tool_input.path`.
Output: message on stdout; exit 2 to block, exit 0 to allow.
Config: `hooks/guards.json` (same directory as the hook itself — shared
across sessions deliberately; sensitive-path patterns are global, not
per-repo).

Freeze state (issue #1890) is resolved per invoking repo, NOT relative to
this hook's own `script_dir`. In a real installed session `script_dir` is
the shared plugin cache (`~/.claude/plugins/cache/bfinster/dev-team/<ver>/
hooks/`) — one location shared by every concurrently-running session,
worktree, and project on the machine. Resolving freeze state there let one
session's `/freeze` scope-lock every other, unrelated session's Write/Edit
calls. `main()` instead resolves it via `hooks/lib/artifact_paths.py`'s
`resolve_file()`, keyed off the tool call's own `cwd` — landing at
`<repo-root>/.claude/hooks/freeze-state.json`, the same per-repo `.claude/`
convention `.review-passed` and other runtime state already use.

Two follow-up fixes (issue #1904 items 7, 11, 14):

- (#1904 item 11) `main()` no longer calls the `git rev-parse`-based
  `project_root()` unconditionally on every Write/Edit. `_cheap_freeze_inactive()`
  proves freeze is inactive with a plain filesystem stat when `cwd` is
  unambiguously the repo root itself (a `.git` entry exists directly under
  it); only when that check is inconclusive does `main()` fall through to
  the git-based resolution — mirroring the cheap-stat fast path #1861 added
  for the higher-frequency PostToolUse `*` matcher.
- (#1904 items 7, 14) `evaluate()`'s freeze-mode allowlist match now
  relativizes `tool_input.file_path` against the freeze-scoped repo root
  before matching — a real session reports an ABSOLUTE `file_path`, which
  can never match a repo-relative glob like `.claude/plans/*.md` (item 14).
  Doing so safely requires knowing whether `file_path` even resolves inside
  the SAME repo `cwd` resolved to: `evaluate()` treats a `file_path` that
  resolves to a different repo root entirely as outside freeze's scope —
  neither blocked nor exempted by that repo's allowlist — rather than
  matching a relativized path fragment against an unrelated repo (item 7).

A third follow-up (post-#1904 review): a candidate whose resolved form
lands outside `repo_root` even though its UNRESOLVED, cwd-joined form was
inside it is a symlink escape (e.g. a `tests/` directory symlinked
elsewhere) — `_freeze_verdict()` blocks that case rather than falling
through to the ordinary sensitive-path/warn checks, since a scope lock
crossing a symlink must never be silently permitted.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from boundary_events import emit_boundary_event as _emit_boundary_event


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


_DEFAULT_BLOCKED = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*credential*",
    "*secret*",
    "*.token",
]
_DEFAULT_WARN = [
    ".claude/settings.json",
    ".claude/claude.md",
]


# ---------------------------------------------------------------------------
# stdin → file path
# ---------------------------------------------------------------------------


def _extract_file_path(raw: str) -> str:
    """Return `tool_input.file_path`, `tool_input.path`, or empty string.

    Mirrors the bash `jq -r '.tool_input.file_path // .tool_input.path // empty'`.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path
    other = tool_input.get("path")
    if isinstance(other, str) and other:
        return other
    return ""


# ---------------------------------------------------------------------------
# Glob matching — the bash uses `case ... esac`, we use fnmatch.fnmatchcase
# with matching semantics (no case folding — we lowercase subjects ourselves).
# ---------------------------------------------------------------------------


def _matches_any(subject: str, patterns: list[str]) -> bool:
    return any(
        pattern and fnmatch.fnmatchcase(subject, pattern) for pattern in patterns
    )


def _relative_to_repo_root(
    file_path: str, cwd: str, repo_root: Path | None
) -> tuple[str | None, bool]:
    """Resolve `file_path` relative to `repo_root`, and whether it lies
    within `repo_root` at all (#1904 items 7 and 14).

    A relative `file_path` is joined against `cwd` first — a tool reports
    `file_path` relative to its own invocation `cwd`, never to some other
    root. Returns `(None, False)` when `repo_root` is unknown (the caller
    didn't resolve one, e.g. freeze is provably inactive), when `file_path`
    cannot be resolved, or when it resolves OUTSIDE `repo_root` entirely —
    freeze's `allowed_patterns` are defined relative to that one repo, so
    they never govern a write that lands in a different repo (item 7),
    even one with the identical relative shape.
    """
    if repo_root is None:
        return None, False
    base = Path(cwd) if cwd else Path.cwd()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
        resolved_root = repo_root.resolve()
    except (OSError, RuntimeError):
        return None, False
    if not resolved.is_relative_to(resolved_root):
        return None, False
    return str(resolved.relative_to(resolved_root)), True


def _unresolved_within_repo_root(file_path: str, cwd: str, repo_root: Path) -> bool:
    """True when `file_path`'s cwd-joined form is LEXICALLY inside
    `repo_root` — normalized via `os.path.abspath` (`..`/`.` collapsing
    only, no filesystem access, no symlink following).

    Used to detect a symlink escape: `file_path` is nominally in scope AS
    WRITTEN, but `_relative_to_repo_root`'s symlink-following `.resolve()`
    lands it outside `repo_root`. Without this check, `evaluate()` would
    fall through to the ordinary sensitive-path/warn checks and silently
    allow a write that crosses a symlink out of a frozen repo.
    """
    base = Path(cwd) if cwd else Path.cwd()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    lexical = os.path.abspath(str(candidate))
    root_lexical = os.path.abspath(str(repo_root))
    return lexical == root_lexical or lexical.startswith(root_lexical + os.sep)


# ---------------------------------------------------------------------------
# Config loading — guards.json + freeze-state.json
# ---------------------------------------------------------------------------


def _load_guards(guards_path: Path) -> tuple:
    """Return (blocked_patterns, warn_patterns) from guards.json or defaults."""
    if not guards_path.is_file():
        return list(_DEFAULT_BLOCKED), list(_DEFAULT_WARN)
    try:
        data = json.loads(guards_path.read_text())
    except (OSError, ValueError):
        return list(_DEFAULT_BLOCKED), list(_DEFAULT_WARN)
    if not isinstance(data, dict):
        return list(_DEFAULT_BLOCKED), list(_DEFAULT_WARN)
    raw_blocked = data.get("blocked_paths")
    raw_warn = data.get("warn_paths")
    blocked = [p for p in (raw_blocked if isinstance(raw_blocked, list) else []) if isinstance(p, str) and p]
    warn = [p for p in (raw_warn if isinstance(raw_warn, list) else []) if isinstance(p, str) and p]
    if not blocked:
        blocked = list(_DEFAULT_BLOCKED)
    if not warn:
        warn = list(_DEFAULT_WARN)
    return blocked, warn


def _load_freeze(freeze_path: Path) -> list[str] | None:
    """Return the freeze `allowed_patterns` when freeze is active, else None."""
    if not freeze_path.is_file():
        return None
    try:
        data = json.loads(freeze_path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("active") is not True and data.get("active") != "true":
        return None
    raw_allowed = data.get("allowed_patterns")
    allowed = [
        p for p in (raw_allowed if isinstance(raw_allowed, list) else []) if isinstance(p, str) and p
    ]
    return allowed


# ---------------------------------------------------------------------------
# Guard evaluation
# ---------------------------------------------------------------------------


class GuardPaths(NamedTuple):
    """The "where do we look" state `main()` resolves once per invocation
    — bundled so `evaluate()` takes one param instead of three."""

    guards_path: Path
    freeze_path: Path
    repo_root: Path | None = None


def _freeze_block(file_path: str, allowed: list[str], cwd: str, session_id: str | None) -> tuple:
    allowed_display = "\n".join(allowed)
    emit_boundary_event(cwd, "pre_tool_guard", "Write", "block", "freeze-scope-lock", session_id)
    return 2, [
        "BLOCKED: Freeze mode is active. Only files matching the allowed patterns can be edited.",
        f"File: {file_path}",
        f"Allowed: {allowed_display}",
        "Use /unfreeze to lift the scope lock.",
    ]


def _freeze_verdict(
    file_path: str,
    lower_path: str,
    freeze_path: Path,
    cwd: str,
    repo_root: Path | None,
    session_id: str | None,
) -> tuple | None:
    """Freeze-mode lens, mirroring `pre_pr_review.py`'s named-verdict-lens
    pipeline shape: a decisive BLOCK `(exit_code, lines)` tuple when freeze
    is active and `file_path` is in scope but not allow-listed (or is a
    symlink escape out of scope — see below); `None` otherwise, meaning
    "continue to the sensitive-path/warn checks".

    A candidate whose UNRESOLVED, cwd-joined form is inside `repo_root`
    but whose `.resolve()`d form (following symlinks) lands outside it is
    a symlink escape and is BLOCKED, not treated as merely out of scope —
    a scope lock crossing a symlink must never be silently permitted.
    """
    allowed = _load_freeze(freeze_path)
    if allowed is None:
        return None

    rel_path, in_scope = _relative_to_repo_root(file_path, cwd, repo_root)
    if repo_root is not None and not in_scope:
        if _unresolved_within_repo_root(file_path, cwd, repo_root):
            return _freeze_block(file_path, allowed, cwd, session_id)
        return None

    subjects = [file_path, lower_path]
    if rel_path is not None:
        subjects.extend((rel_path, rel_path.lower()))
    matched = any(
        fnmatch.fnmatchcase(subject, pat) for subject in subjects for pat in allowed
    )
    if matched:
        return None
    return _freeze_block(file_path, allowed, cwd, session_id)


def evaluate(
    file_path: str,
    cwd: str = ".",
    session_id: str | None = None,
    *,
    paths: GuardPaths,
) -> tuple:
    """Return (exit_code, [stdout_lines]) for a single file_path decision.

    - exit_code 0 with `[warning]` lines means "allow with warning".
    - exit_code 0 with `[]` means "silent pass".
    - exit_code 2 with `[block message]` means "block".

    `paths.repo_root` is the repo `cwd` resolved to (see `main()`) — used
    only to relativize `file_path` against it for the freeze-mode allowlist
    match (#1904 items 7, 14). Leave it `None` to match `file_path` as-is,
    e.g. when the caller already knows it's repo-relative.

    Emits a boundary event (#859) for every warn/block decision.
    """
    if not file_path:
        return 0, []

    filename = os.path.basename(file_path)
    lower_filename = filename.lower()
    lower_path = file_path.lower()

    # Freeze mode first — scope lock trumps allow list.
    verdict = _freeze_verdict(
        file_path, lower_path, paths.freeze_path, cwd, paths.repo_root, session_id
    )
    if verdict is not None:
        return verdict

    blocked_patterns, warn_patterns = _load_guards(paths.guards_path)

    if _matches_any(lower_filename, blocked_patterns) or _matches_any(
        lower_path, blocked_patterns
    ):
        emit_boundary_event(cwd, "pre_tool_guard", "Write", "block", "sensitive-path", session_id)
        return 2, [
            f"BLOCKED: Write to '{file_path}' is not allowed.",
            "This path matches a sensitive-file pattern in .claude/hooks/guards.json.",
            "If this write is intentional, confirm with the user before proceeding.",
        ]

    if _matches_any(lower_path, warn_patterns):
        emit_boundary_event(cwd, "pre_tool_guard", "Write", "warn", "protected-config", session_id)
        return 0, [
            f"WARNING: '{file_path}' is a protected configuration file.",
            "Verify this change is intentional before writing.",
        ]

    return 0, []


def _cheap_freeze_inactive(cwd: str) -> bool:
    """Cheap, non-git proof that freeze mode is inactive for `cwd` (#1904
    item 11) — mirrors #1861's `looks_like_monorepo_checkout` cheap-stat
    pattern, added there for the higher-frequency PostToolUse `*` matcher.

    Only returns True when `cwd` is unambiguously the repo root itself (a
    `.git` entry exists directly under it — a plain stat, no `git`
    subprocess needed to confirm this) AND no `.claude/hooks/
    freeze-state.json` exists there. Any other shape — `cwd` is a
    subdirectory of the repo (the file could exist at an ancestor this
    check never looks at), or the file exists right here — is ambiguous;
    the caller must fall through to the git-rev-parse-based resolution.
    """
    try:
        base = Path(cwd)
        if not (base / ".git").exists():
            return False
        return not (base / ".claude" / "hooks" / "freeze-state.json").exists()
    except OSError:
        return False


def main() -> int:
    raw = sys.stdin.read()
    file_path = _extract_file_path(raw)
    if not file_path:
        return 0
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {}
    raw_cwd = payload.get("cwd") if isinstance(payload, dict) else None
    cwd = raw_cwd if isinstance(raw_cwd, str) and raw_cwd and "\0" not in raw_cwd else "."
    raw_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    session_id = raw_session_id if isinstance(raw_session_id, str) else None
    script_dir = Path(__file__).resolve().parent

    repo_root: Path | None
    if _cheap_freeze_inactive(cwd):
        freeze_path = Path(cwd) / ".claude" / "hooks" / "freeze-state.json"
        repo_root = None
    else:
        repo_root = artifact_paths.project_root(start=cwd)
        freeze_path = repo_root / ".claude" / "hooks" / "freeze-state.json"

    paths = GuardPaths(script_dir / "guards.json", freeze_path, repo_root)
    exit_code, lines = evaluate(file_path, cwd, session_id, paths=paths)
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
