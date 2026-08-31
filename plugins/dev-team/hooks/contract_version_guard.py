#!/usr/bin/env python3
"""Python port of hooks/contract-version-guard.sh (#596 / #572 Phase 3).

Byte-compatible port of the Claude Code PreToolUse hook. Blocks Write/Edit
operations that change the body of
`plugins/dev-team/knowledge/security-primitives-contract.md` without also
bumping the `version:` field in its YAML frontmatter.

Semver policy (see the contract file for details):
    PATCH = doc/typo; MINOR = additive; MAJOR = breaking.

Bypass: release-please[bot] commits are allowed through (detected via
GITHUB_ACTOR, GIT_AUTHOR_EMAIL, or GIT_AUTHOR_NAME matching the bot). Bypass
is logged to `metrics/contract-version-guard-audit.jsonl`.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with tool_input.{file_path, content |
            new_string, old_string}
    Output: exit 0 = allow (silent)
            exit 2 = block; stderr contains the operator message

Stdlib-only (json/os/pathlib/re/subprocess/sys). See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from atomic_state import append_line_locked
from boundary_events import emit_boundary_event as _emit_boundary_event
from stdin_json import read_stdin_json  # type: ignore[import-not-found]


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass

# Matches the .sh's SCRIPT_DIR / REPO_ROOT resolution.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]
_CONTRACT_PATH = "plugins/dev-team/knowledge/security-primitives-contract.md"
_AUDIT_LOG = _REPO_ROOT / "metrics" / "contract-version-guard-audit.jsonl"


# ---------------------------------------------------------------------------
# stdin
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# release-please bypass
# ---------------------------------------------------------------------------


def _is_release_please() -> bool:
    for var in ("GITHUB_ACTOR", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME"):
        val = os.environ.get(var, "")
        if "release-please" in val:
            return True
    return False


def _log_bypass(reason: str) -> None:
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "ts": ts,
        "bypass": True,
        "reason": reason,
        "github_actor": os.environ.get("GITHUB_ACTOR", ""),
        "git_email": os.environ.get("GIT_AUTHOR_EMAIL", ""),
    }
    # json.dumps preserves dict insertion order, matching the .sh's printf
    # key order: ts, bypass, reason, github_actor, git_email. Hand-building
    # this line with f-strings (as before) left a `"`/`\` in an env-sourced
    # value able to emit an invalid JSONL line; serialize it properly instead.
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    append_line_locked(_AUDIT_LOG, line)


# ---------------------------------------------------------------------------
# YAML frontmatter helpers
# ---------------------------------------------------------------------------


_DELIM_RE = re.compile(r"^---[ \t]*$")
_VERSION_RE = re.compile(r"^version:[ \t]+(.*)$")


def _extract_version(text: str) -> str:
    """Return the `version:` value from the first `---`-delimited frontmatter
    block, or the empty string if absent.

    Matches the .sh's awk pipeline: enter block after first `---`, exit on
    the second, strip surrounding whitespace, quotes (single or double).
    """
    delim = 0
    for line in text.split("\n"):
        if _DELIM_RE.match(line):
            delim += 1
            if delim == 2:
                return ""
            continue
        if delim == 1:
            m = _VERSION_RE.match(line)
            if m:
                # The .sh does `gsub(/["\047[:space:]]/, "")` on the value,
                # stripping double quote, single quote, and all whitespace.
                value = m.group(1)
                value = re.sub(r'["\'\s]', "", value)
                return value
    return ""


def _body_digest(text: str) -> str:
    """Return the body (post-frontmatter) normalized for comparison.

    Matches the .sh's awk pipeline + `tr -s '[:space:]' ' '`: strip
    frontmatter, join with newlines, then collapse all whitespace runs to a
    single space. The .sh's `awk { print }` only emits when it has real
    content — the pipeline sees nothing when the body is empty — so an
    empty body must round-trip to the empty string, not to " ".
    """
    delim = 0
    in_body = False
    body_lines = []
    for line in text.split("\n"):
        if _DELIM_RE.match(line):
            delim += 1
            if delim == 2:
                in_body = True
                continue
            continue
        if in_body:
            body_lines.append(line)
    # Drop trailing empty lines produced by `text.split("\n")` on a
    # newline-terminated body — awk print never emits them either.
    while body_lines and body_lines[-1] == "":
        body_lines.pop()
    if not body_lines:
        return ""
    joined = "\n".join(body_lines) + "\n"
    return re.sub(r"\s+", " ", joined)


# ---------------------------------------------------------------------------
# HEAD content lookup
# ---------------------------------------------------------------------------


def _head_content() -> str:
    """Return the HEAD version of the contract file, or empty string.

    Silently returns "" on any subprocess/git failure — matches the .sh's
    `git show ... || true`.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--git-dir"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        show = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "show", f"HEAD:{_CONTRACT_PATH}"],
            capture_output=True,
            check=False,
        )
        if show.returncode != 0:
            return ""
        return show.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------------------
# Edit simulation — first-occurrence substring replace, matching Edit tool
# ---------------------------------------------------------------------------


def _apply_edit_first_line(head: str, old: str, new: str) -> str:
    """Substitute `old` with `new` in the first line that contains it.

    Mirrors the .sh's awk pipeline which processes line-by-line and stops
    after the first replacement. This is intentionally NOT a full-string
    replace — it matches the .sh's precise behavior.
    """
    replaced = False
    out = []
    for line in head.split("\n"):
        if not replaced:
            idx = line.find(old)
            if idx >= 0:
                line = line[:idx] + new + line[idx + len(old) :]
                replaced = True
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------


def _msg_initial_add() -> str:
    return (
        f"contract-version-guard: initial add of {_CONTRACT_PATH} must "
        "include a 'version:' field in frontmatter."
    )


def _msg_removed_version() -> str:
    return (
        "contract-version-guard: proposed edit removes or blanks the "
        "'version:' field. The contract MUST carry a semver version string."
    )


def _msg_missing_bump(head_ver: str, new_ver: str) -> str:
    displayed_head = head_ver if head_ver else "<none>"
    return (
        f"contract-version-guard: edit to {_CONTRACT_PATH} changes the body "
        "without bumping 'version:'.\n"
        "\n"
        f"  current HEAD version: {displayed_head}\n"
        f"  proposed version:     {new_ver}\n"
        "\n"
        "Per the contract's semver policy:\n"
        f"  - PATCH ({head_ver} → next) for typos / clarifications / doc polish\n"
        "  - MINOR (e.g. 1.x → 1.(x+1)) for additive changes (new optional "
        "fields, new enum values, new agent/skill IDs)\n"
        "  - MAJOR (e.g. 1.y → 2.0.0) for breaking changes (renamed/removed "
        "fields, new required fields)\n"
        "\n"
        "Bump the version to match your change, then retry the edit."
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _normalize_path(file_path: str) -> str:
    """Repo-relative path. Absolute repo-root prefix stripped, otherwise passed through."""
    prefix = str(_REPO_ROOT) + "/"
    if file_path.startswith(prefix):
        return file_path[len(prefix) :]
    return file_path


def main() -> int:
    payload = read_stdin_json() or {}
    tool_input = (
        payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    )

    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    tool_name = payload.get("tool_name") or ""
    session_id = payload.get("session_id")

    if not isinstance(file_path, str) or not file_path:
        return 0

    rel_path = _normalize_path(file_path)
    if rel_path != _CONTRACT_PATH:
        return 0

    if _is_release_please():
        _log_bypass("release-please-actor")
        return 0

    # Extract proposed content
    new_content: str = ""
    old_string: str = ""
    new_string: str = ""
    if tool_name == "Write":
        new_content = tool_input.get("content") or ""
        if not isinstance(new_content, str):
            new_content = ""
    elif tool_name == "Edit":
        old_string = tool_input.get("old_string") or ""
        new_string = tool_input.get("new_string") or ""
        if not isinstance(old_string, str):
            old_string = ""
        if not isinstance(new_string, str):
            new_string = ""

    head_content = _head_content()

    # Initial add — Write must include a version field; Edit passes through
    # (nothing to bump against).
    if not head_content:
        if tool_name == "Write":
            new_version = _extract_version(new_content)
            if not new_version:
                sys.stderr.write(_msg_initial_add() + "\n")
                emit_boundary_event(
                    _REPO_ROOT, "contract_version_guard", tool_name, "block",
                    "contract-version-missing", session_id,
                )
                return 2
        return 0

    head_version = _extract_version(head_content)

    if tool_name == "Edit":
        if not old_string or not new_string:
            # Unusual edit (e.g. replace_all empty) — conservative allow.
            return 0
        new_content = _apply_edit_first_line(head_content, old_string, new_string)

    new_version = _extract_version(new_content)

    if not new_version:
        sys.stderr.write(_msg_removed_version() + "\n")
        emit_boundary_event(
            _REPO_ROOT, "contract_version_guard", tool_name, "block",
            "contract-version-removed", session_id,
        )
        return 2

    head_body = _body_digest(head_content)
    new_body = _body_digest(new_content)

    if head_body == new_body:
        # Body unchanged — allow.
        return 0

    if head_version == new_version:
        sys.stderr.write(_msg_missing_bump(head_version, new_version) + "\n")
        emit_boundary_event(
            _REPO_ROOT, "contract_version_guard", tool_name, "block",
            "contract-version-missing-bump", session_id,
        )
        return 2

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
