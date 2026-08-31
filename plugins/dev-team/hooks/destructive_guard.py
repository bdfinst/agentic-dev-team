#!/usr/bin/env python3
"""Python port of hooks/destructive-guard.sh (#598 / #572 Phase 3).

Claude Code PreToolUse hook. Runs before Bash tool calls, detects
destructive commands, and either warns (default, exit 0) or blocks (when
careful mode is active, exit 2). Patterns are loaded from
`hooks/destructive-commands.json`; careful state from
`<repo-root>/.claude/hooks/careful-state.json` (see below). Falls back to
inline defaults when the commands config is absent.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with tool_input.command
    Output: exit 0 = allow (optionally with CAUTION warning on stdout)
            exit 2 = block; stdout contains the block message

Stdlib-only (json/pathlib/sys). See ADR 0014.

Careful state (issue #1900, same bug class as #1890's freeze-state.json
fix) is resolved per invoking repo, NOT relative to this hook's own
`script_dir`. In a real installed session `script_dir` is the shared
plugin cache (`~/.claude/plugins/cache/bfinster/dev-team/<ver>/hooks/`) —
one location shared by every concurrently-running session, worktree, and
project on the machine. Resolving careful state there let one session's
`/careful` activation scope-lock every other, unrelated session's Bash
calls. `main()` instead resolves it via `hooks/lib/artifact_paths.py`'s
`resolve_file()`, keyed off the tool call's own `cwd` — landing at
`<repo-root>/.claude/hooks/careful-state.json`, the same per-repo
`.claude/` convention `freeze-state.json` and `.review-passed` already use.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from boundary_events import emit_boundary_event as _emit_boundary_event
from stdin_json import read_stdin_json  # type: ignore[import-not-found]


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass
_COMMANDS_FILE = _SCRIPT_DIR / "destructive-commands.json"

_PROBE_TIMEOUT_SECONDS = 1.0
_OVERRIDE_ENV_VAR = "DEV_TEAM_GUARD_OVERRIDE"


# Inline fallbacks — kept in the exact order the .sh's here-docs use so
# the "first match wins" ordering is preserved byte-for-byte across
# implementations.
_DEFAULT_FILE_PATTERNS = ["rm -rf", "rm -r", "rm -fr"]
_DEFAULT_DB_PATTERNS = ["drop table", "drop database", "truncate"]
_DEFAULT_GIT_PATTERNS = [
    "git push --force",
    "git push -f",
    "git reset --hard",
    "git clean -f",
    "git clean -fd",
    "git checkout -- .",
    "git branch -D",
]
_DEFAULT_PROCESS_PATTERNS = ["kill -9", "killall", "pkill"]
_DEFAULT_PERMISSION_PATTERNS = ["chmod 777"]
_DEFAULT_SAFE_PATTERNS = [
    "rm -rf node_modules",
    "rm -rf dist",
    "rm -rf build",
    "rm -rf .cache",
    "rm -rf coverage",
    "rm -rf tmp",
    "rm -rf __pycache__",
]


def _load_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _extract_command(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    cmd = tool_input.get("command") or ""
    return cmd if isinstance(cmd, str) else ""


def _careful_active(careful_path: Path) -> bool:
    """Read careful-state.json's `active` boolean. False on any error."""
    data = _load_json(careful_path)
    if data is None:
        return False
    value = data.get("active")
    if isinstance(value, bool):
        return value
    # The .sh treats `.active // false` as false when missing; string
    # values other than "true" (bash string comparison) are treated as
    # false. Match that here.
    return isinstance(value, str) and value == "true"


def _load_patterns() -> tuple[
    list[str], list[str], list[str], list[str], list[str], list[str]
]:
    """Load pattern lists from the config file, falling back to inline defaults.

    Return order: (file, db, git, process, permission, safe).
    """
    data = _load_json(_COMMANDS_FILE)
    if data is None:
        return (
            list(_DEFAULT_FILE_PATTERNS),
            list(_DEFAULT_DB_PATTERNS),
            list(_DEFAULT_GIT_PATTERNS),
            list(_DEFAULT_PROCESS_PATTERNS),
            list(_DEFAULT_PERMISSION_PATTERNS),
            list(_DEFAULT_SAFE_PATTERNS),
        )

    def _list_of_str(key: str) -> list[str]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return []
        return [x for x in raw if isinstance(x, str)]

    return (
        _list_of_str("file_destruction"),
        _list_of_str("database_destruction"),
        _list_of_str("git_destruction"),
        _list_of_str("process_destruction"),
        _list_of_str("permission_escalation"),
        _list_of_str("safe_allowlist"),
    )


# --- Context probes (#862) -------------------------------------------------
#
# Cheap, stdlib-only, fail-safe probes of git/environment state. Each git
# probe is a single `subprocess.run` with a short timeout; any failure (not a
# repo, git binary missing, non-zero exit, timeout) returns None rather than
# raising. Probes are only invoked after a destructive pattern match, and
# only for patterns that carry an escalation rule (see `_load_escalations`
# and `main`) — commands with no match, or matched commands with no
# escalation rule, never pay the subprocess cost.


def _run_git(args: list[str]) -> str | None:
    """Run a single git subprocess with a short timeout. None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _current_branch() -> str | None:
    """Current checked-out branch name, or None (detached HEAD, no repo, etc.)."""
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None or branch == "HEAD":
        return None
    return branch


def _default_branch() -> str | None:
    """Resolved default branch name, or None when it cannot be determined.

    Primary source: `git symbolic-ref --short refs/remotes/origin/HEAD`
    (e.g. "origin/main" -> "main"). Falls back to a local `main`/`master`
    existence heuristic when the symbolic ref is unset (common on fresh
    clones): if exactly one of the two exists as a local branch, use it;
    if both or neither resolve, treat the default branch as unresolved.
    """
    symbolic = _run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if symbolic:
        return symbolic.rsplit("/", 1)[-1]

    candidates = [
        name
        for name in ("main", "master")
        if _run_git(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"])
        is not None
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _remote_url() -> str | None:
    """The `origin` remote URL, or None (no remote, not a repo, etc.)."""
    return _run_git(["remote", "get-url", "origin"])


def _ci_active() -> bool:
    """Whether the `CI` environment variable is set to a truthy value."""
    value = os.environ.get("CI", "")
    return value.strip().lower() not in ("", "0", "false")


def _matches_any(cmd_lower: str, patterns: list[str]) -> str | None:
    """Return the first pattern whose lowercase substring appears in `cmd_lower`."""
    for pattern in patterns:
        if not pattern:
            continue
        # The .sh does `case "$cmd" in *"$pattern"*)` — a plain substring
        # match. Both operands are already lowercased.
        if pattern.lower() in cmd_lower:
            return pattern
    return None


def _first_match(cmd_lower: str, groups: list[tuple[list[str], str]]) -> str | None:
    """Iterate groups in .sh order, return 'category: pattern' on first hit."""
    for patterns, category in groups:
        pattern = _matches_any(cmd_lower, patterns)
        if pattern is not None:
            return f"{category}: {pattern}"
    return None


def _emit(text: str) -> None:
    """Print with trailing newline — matches the .sh's `echo` behavior."""
    sys.stdout.write(text + "\n")


def _matched_pattern_text(match: str) -> str:
    """Recover the raw pattern text from a `_first_match` "category: pattern" label."""
    _, _, pattern = match.partition(": ")
    return pattern


# --- Escalation evaluator (#862) --------------------------------------------


def _load_escalations() -> list[dict[str, Any]]:
    """Load the optional "escalations" list from destructive-commands.json.

    Absent key, missing/unreadable file, or malformed entries -> []. This
    keeps a JSON config without an "escalations" key byte-compatible with
    pre-#862 behavior (no rules -> no escalation lookups ever succeed).
    """
    data = _load_json(_COMMANDS_FILE)
    if data is None:
        return []
    raw = data.get("escalations")
    if not isinstance(raw, list):
        return []
    return [
        rule
        for rule in raw
        if isinstance(rule, dict) and isinstance(rule.get("pattern"), str)
    ]


def _find_escalation_rule(
    escalations: list[dict[str, Any]], pattern: str
) -> dict[str, Any] | None:
    for rule in escalations:
        if rule.get("pattern") == pattern:
            return rule
    return None


def _branch_named_in_command(command_lower: str, branch: str) -> bool:
    """Whether `branch` appears as a whole path segment/token in the command.

    Word-boundary aware so "main" does not match inside "feature/main-fix".
    """
    escaped = re.escape(branch.lower())
    return re.search(rf"(?<![\w/-]){escaped}(?![\w/-])", command_lower) is not None


def _condition_target_branch_default(
    command: str,
    command_lower: str,
    pattern: str,
    current_branch: str | None,
    default_branch: str | None,
) -> bool:
    """`target_branch: "default"` — the command's target resolves to the default branch.

    High-confidence evidence only: either the default branch name appears
    explicitly as the command's target (e.g. `git push --force origin main`,
    `git branch -D main`), or the command has no explicit target (bare
    `git push --force`) and the current branch (HEAD) equals the default
    branch. Any unresolved probe -> False (fail-safe, no escalation).
    """
    if default_branch is None:
        return False
    if _branch_named_in_command(command_lower, default_branch):
        return True
    remainder = command_lower.replace(pattern.lower(), "", 1).strip()
    if remainder == "":
        return current_branch is not None and current_branch == default_branch
    return False


def _condition_current_branch_default(
    current_branch: str | None, default_branch: str | None
) -> bool:
    """`current_branch: "default"` — HEAD is currently the default branch."""
    if current_branch is None or default_branch is None:
        return False
    return current_branch == default_branch


def _rule_escalates(
    rule: dict[str, Any],
    command: str,
    command_lower: str,
    pattern: str,
    current_branch: str | None,
    default_branch: str | None,
) -> bool:
    """Evaluate a rule's `when` conditions. Unknown/unresolvable -> False."""
    when = rule.get("when")
    if not isinstance(when, dict) or not when:
        return False
    if when.get("target_branch") == "default" and not _condition_target_branch_default(
        command, command_lower, pattern, current_branch, default_branch
    ):
        return False
    if when.get("current_branch") == "default" and not _condition_current_branch_default(
        current_branch, default_branch
    ):
        return False
    # Only the two recognized condition keys are supported today; an
    # unrecognized key alone would otherwise vacuously escalate.
    known_keys = {"target_branch", "current_branch"}
    return bool(set(when.keys()) & known_keys)


def _override_active() -> bool:
    """One-shot escalation bypass via `DEV_TEAM_GUARD_OVERRIDE=1` (#862)."""
    return os.environ.get(_OVERRIDE_ENV_VAR, "").strip() == "1"


def main() -> int:
    payload = read_stdin_json() or {}
    command = _extract_command(payload)
    if not command:
        return 0

    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) and raw_cwd and "\0" not in raw_cwd else "."
    session_id = payload.get("session_id")

    lower_command = command.lower()

    careful_path = artifact_paths.resolve_file(
        "hooks", "careful-state.json", root=cwd, migrate=False
    )

    (
        file_patterns,
        database_patterns,
        git_patterns,
        process_patterns,
        permission_patterns,
        safe_patterns,
    ) = _load_patterns()

    # Safe allowlist short-circuit — matches the .sh's `matches_safe` check.
    if _matches_any(lower_command, safe_patterns) is not None:
        return 0

    match = _first_match(
        lower_command,
        [
            (file_patterns, "File destruction"),
            (database_patterns, "Database destruction"),
            (git_patterns, "Git destruction"),
            (process_patterns, "Process destruction"),
            (permission_patterns, "Permission escalation"),
        ],
    )
    if match is None:
        return 0

    careful = _careful_active(careful_path)
    if careful:
        _emit(f"BLOCKED: Destructive command detected ({match}).")
        _emit(f"Command: {command}")
        _emit("Careful mode is active. This command has been blocked.")
        _emit("Use /careful off to disable careful mode, or confirm with the user.")
        emit_boundary_event(cwd, "destructive_guard", "Bash", "block", match, session_id)
        return 2

    # Escalation evaluator (#862) — only consulted for matched commands, and
    # only probes git/environment state when the matched pattern carries an
    # escalation rule, so non-matching and non-escalating commands pay zero
    # added subprocess cost.
    pattern = _matched_pattern_text(match)
    escalations = _load_escalations()
    rule = _find_escalation_rule(escalations, pattern)
    escalated = False
    current_branch: str | None = None
    default_branch: str | None = None
    if rule is not None:
        current_branch = _current_branch()
        default_branch = _default_branch()
        escalated = _rule_escalates(
            rule, command, lower_command, pattern, current_branch, default_branch
        )

    override = escalated and _override_active()

    # Only escalated matches get their own event here — a rule that exists
    # but doesn't escalate falls through to the plain "warn" emission below,
    # and emitting both would double-log one decision.
    if escalated:
        emit_boundary_event(
            cwd,
            "destructive_guard",
            "Bash",
            "block" if not override else "bypass",
            pattern,
            session_id,
        )

    if escalated and not override:
        _emit(f"BLOCKED: Destructive command detected ({match}).")
        _emit(f"Command: {command}")
        _emit(
            f"This command targets the default branch ({default_branch}); "
            "force-push, reset, and branch-delete are hard-blocked on the "
            "default branch regardless of careful mode."
        )
        _emit(
            f"Set {_OVERRIDE_ENV_VAR}=1 for this single command to override, "
            "or confirm with the user."
        )
        return 2

    _emit(f"CAUTION: Destructive command detected ({match}).")
    _emit(f"Command: {command}")
    _emit("This action is hard to reverse. Confirm with the user before proceeding.")
    # An escalated-and-overridden match already emitted its own "bypass"
    # event above; only emit "warn" here for the plain, non-escalated case
    # so one decision never produces two events.
    if not escalated:
        emit_boundary_event(cwd, "destructive_guard", "Bash", "warn", match, session_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
