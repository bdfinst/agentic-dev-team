#!/usr/bin/env python3
"""boundary_events_write_guard.py — Claude Code PreToolUse hook (#2171).

`.claude/metrics/boundary-events.jsonl` is the plugin's boundary-level
accountability ledger (`hooks/lib/boundary_events.py`, #859) — every guard
hook's block/warn/bypass decision is recorded there, and that module's own
docstring states rows must never carry free text (command text, prompt
text, file paths, reasons), only rule IDs from closed vocabularies. A
direct `Write` or `Edit` tool call targeting that file bypasses
`emit_boundary_event()` entirely and could forge or corrupt that record
from inside the session — this hook raises the cost of that forgery the
same way `pre_tool_guard.py` raises it for other sensitive paths, by
blocking a Write/Edit whose `file_path`/`path` resolves to the ledger.

Step 1.1 of plans/2164-verdict-ledger-writer.md added the Write/Edit
path-match guard. Step 1.2 extends this same module to also inspect Bash
`tool_input.command` text for write-shaped commands (redirect, `tee`,
`sed -i`, `cp`/`mv`/`rm`/`truncate`/`dd`, or a write/append/exclusive-mode
Python `open()`) that target the ledger by filename, in any path form —
see `bash_command_writes_to_ledger()` and `_BASH_WRITE_SHAPE_PATTERNS`
below. The hook is registered in `settings.json`'s existing `Write|Edit`
and `Bash` `PreToolUse` matcher groups.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin — for Write/Edit, `tool_input.file_path`
            or `tool_input.path`, resolved relative to `cwd` when not
            absolute; for Bash, `tool_input.command`
    Output: block message on stdout. The Write/Edit-path message names
            `emit_boundary_event()` (`hooks/lib/boundary_events.py`) as the
            remedy — a Python-only function unreachable from a shell
            command. The Bash-path message instead names the
            `hooks/lib/boundary_events.py` CLI (`python3
            hooks/lib/boundary_events.py <event> ...`, #1461) — the only
            remedy actually reachable from a Bash command (plan-review-ux
            finding, Step 1.2).
    Exit  : 2 to block, 0 to allow. Fail-open on any exception (malformed
            payload, unreadable cwd, unresolvable repo root) — never raises.

Path matching is lexical only (`os.path.abspath` — `.`/`..` collapsing, no
symlink following): a symlink-escape sandbox is explicitly out of scope
(plan Step 1.1 TEST note) — this guard raises the cost of forgery, it does
not sandbox the filesystem.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from boundary_events import emit_boundary_event as _emit_boundary_event
from stdin_json import read_stdin_json  # type: ignore[import-not-found]

_LEDGER_NAME = "boundary-events.jsonl"


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def _extract_file_path(tool_input: object) -> str:
    """Return `tool_input.file_path`, `tool_input.path`, or empty string —
    mirrors `pre_tool_guard._extract_file_path`'s field-preference order."""
    if not isinstance(tool_input, dict):
        return ""
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path
    other = tool_input.get("path")
    if isinstance(other, str) and other:
        return other
    return ""


def targets_ledger(file_path: str, cwd: str) -> bool:
    """True when `file_path` (joined against `cwd` if not absolute) names
    the same on-disk path `emit_boundary_event()` itself resolves and
    writes to — `artifact_paths.resolve_file("metrics", ...)` under the
    repo root, not a bare `.claude/metrics/` prefix match (so
    `review-verdicts.jsonl`, Slice 2's own store, is unaffected)."""
    if not file_path:
        return False
    base = Path(cwd) if cwd else Path.cwd()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate_norm = os.path.abspath(str(candidate))

    ledger = artifact_paths.resolve_file(
        "metrics", _LEDGER_NAME, root=cwd, migrate=False
    )
    ledger_norm = os.path.abspath(str(ledger))

    return candidate_norm == ledger_norm


def _extract_command(tool_input: object) -> str:
    """Return `tool_input.command`, or empty string — mirrors
    `destructive_guard._extract_command`'s field access."""
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


# Any prefix of path characters (word chars, dots, slashes, hyphens) ending
# in the ledger's literal filename. Matches the filename in every path form
# the plan requires (relative, absolute, "./"-prefixed, or bare after a
# `cd .claude/metrics`-shaped prefix) with a single suffix, since all four
# forms literally end in this substring.
_LEDGER_PATH_SUFFIX = r"[\w./-]*" + re.escape(_LEDGER_NAME)

# Bash write-shaped patterns targeting the ledger (Step 1.2, #2171). Each
# pattern embeds `_LEDGER_PATH_SUFFIX` directly, so a match always means the
# command's write operation targets the ledger specifically — not merely
# that the ledger's filename appears somewhere unrelated in the command
# (e.g. `cat boundary-events.jsonl | tee /tmp/copy.txt` reads the ledger and
# writes elsewhere; it does not match the `tee` pattern below because
# `tee`'s own argument is `/tmp/copy.txt`, not the ledger). Heuristic, not a
# sandbox — see the plan's Risks note ("raises the cost of forgery," per
# #2171's Out of Scope). Mirrors destructive_guard.py's own pattern-table
# idiom (a module-level constant, one comment per pattern).
_BASH_WRITE_SHAPE_PATTERNS: tuple[re.Pattern, ...] = (
    # `>`/`>>` redirect whose target is the ledger. Also catches a
    # heredoc's trailing redirect operator (`cat <<'EOF' >> ...`) — the
    # heredoc `<<` marker itself is never parsed or matched (plan Decision
    # note); detection is via this same trailing operator, like any other
    # write-shaped command.
    re.compile(rf">{{1,2}}\s*['\"]?{_LEDGER_PATH_SUFFIX}"),
    # `tee` writing to the ledger.
    re.compile(rf"\btee\b(?:\s+-{{1,2}}\S+)*\s+['\"]?{_LEDGER_PATH_SUFFIX}"),
    # `sed -i` (in-place edit) targeting the ledger, within the same shell
    # statement (stops at `;`/`|`/`&` so an unrelated later statement that
    # happens to also mention the ledger doesn't false-positive).
    re.compile(rf"\bsed\b[^;|&\n]*-i\b[^;|&\n]*['\"]?{_LEDGER_PATH_SUFFIX}"),
    # cp/mv/rm/truncate/dd targeting the ledger, within the same shell
    # statement (same same-statement scoping as the sed pattern above).
    re.compile(rf"\b(?:cp|mv|rm|truncate|dd)\b[^;|&\n]*{_LEDGER_PATH_SUFFIX}"),
    # A Python `open(...)` call on the ledger using a write/append/
    # exclusive mode ("w"/"a"/"x", optionally suffixed e.g. "wb"/"a+"/"x+").
    # A read-mode or mode-omitted (default "r") `open()` never matches this
    # pattern, so it is allowed.
    re.compile(
        rf"open\(\s*['\"]{_LEDGER_PATH_SUFFIX}['\"]\s*,\s*['\"](?:w|a|x)[\w+]*['\"]"
    ),
)


def bash_command_writes_to_ledger(command: str) -> bool:
    """True when `command` is write-shaped AND targets the ledger by
    filename, in any path form — see `_BASH_WRITE_SHAPE_PATTERNS`. A
    read-shaped command referencing the same filename (`cat`, `grep`,
    `tail`, `head`, a read-mode `open()`) never matches any pattern here,
    so it is allowed without a separate read-allowlist check."""
    if not command:
        return False
    return any(pattern.search(command) for pattern in _BASH_WRITE_SHAPE_PATTERNS)


def main() -> int:
    try:
        payload = read_stdin_json()
        if payload is None:
            return 0

        raw_cwd = payload.get("cwd")
        cwd = (
            raw_cwd
            if isinstance(raw_cwd, str) and raw_cwd and "\0" not in raw_cwd
            else "."
        )
        raw_tool = payload.get("tool_name")
        tool = raw_tool if isinstance(raw_tool, str) and raw_tool else "Write"
        raw_session_id = payload.get("session_id")
        session_id = raw_session_id if isinstance(raw_session_id, str) else None

        if tool == "Bash":
            command = _extract_command(payload.get("tool_input"))
            if not bash_command_writes_to_ledger(command):
                return 0

            emit_boundary_event(
                cwd, "boundary_events_write_guard", tool, "block", "ledger-write-blocked", session_id
            )
            print(
                f"BLOCKED: This Bash command writes to '.claude/metrics/{_LEDGER_NAME}', "
                "which is not allowed."
            )
            print(
                "This file is the boundary-events accountability ledger (#859) — "
                "it is append-only from the session's perspective."
            )
            print(
                "Use 'python3 hooks/lib/boundary_events.py <event> ...' "
                "(plugins/dev-team/hooks/lib/boundary_events.py) instead of writing to it from Bash."
            )
            return 2

        file_path = _extract_file_path(payload.get("tool_input"))
        if not file_path:
            return 0

        if not targets_ledger(file_path, cwd):
            return 0

        emit_boundary_event(
            cwd, "boundary_events_write_guard", tool, "block", "ledger-write-blocked", session_id
        )
        print(f"BLOCKED: Direct write to '{file_path}' is not allowed.")
        print(
            "This file is the boundary-events accountability ledger (#859) — "
            "it is append-only from the session's perspective."
        )
        print(
            "Use emit_boundary_event() in plugins/dev-team/hooks/lib/boundary_events.py "
            "instead of writing to it directly."
        )
        return 2
    except Exception:  # noqa: BLE001 - fail-open by design, see module docstring
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
