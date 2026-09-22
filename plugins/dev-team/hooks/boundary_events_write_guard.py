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
            `hooks/lib/boundary_events.py` CLI's actual invocable shape
            (`python3 plugins/dev-team/hooks/lib/boundary_events.py --event
            <event> --subject-hash <hash> ...`, #1461) — the message
            interpolates the live `<event>` choice set from
            `boundary_events.cli_event_names()` rather than restating it
            here, so this docstring never drifts the way the message
            itself used to (review finding, #2171). `--event` is a flag
            drawn from a closed `choices` set, not a positional, and most
            events require `--subject-hash`; the CLI cannot construct an
            arbitrary row by design — a genuinely custom row still needs
            `emit_boundary_event()` called from a hook (plan-review-ux
            finding, Step 1.2, corrected by review).
    Exit  : 2 to block, 0 to allow. Fail-open on any exception (malformed
            payload, unreadable cwd, unresolvable repo root) — never raises.

Path matching is lexical only (`os.path.abspath` — `.`/`..` collapsing, no
symlink following): a symlink-escape sandbox is explicitly out of scope
(plan Step 1.1 TEST note) — this guard raises the cost of forgery, it does
not sandbox the filesystem. One narrow exception: `targets_ledger()`
resolves the `cwd` anchor itself via `os.path.realpath` before joining a
relative `file_path` against it (review finding — see `targets_ledger()`'s
own docstring) so that anchor stays symmetric with the ledger side, which
already passes through `git rev-parse --show-toplevel`'s own symlink
resolution via `artifact_paths.resolve_file()`/`project_root()`. Everything
beyond that single anchor — the rest of the joined path, and all Bash
command-text matching below — stays purely lexical, no further symlink
following.

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
from boundary_events import cli_event_names as _cli_event_names
from boundary_events import emit_boundary_event as _emit_boundary_event
from review_dispatch_ledger import LEDGER_STREAM as _LEDGER_NAME
from review_dispatch_ledger import resolve_stream as _resolve_ledger_stream
from stdin_json import read_stdin_json  # type: ignore[import-not-found]


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
    path = tool_input.get("path")
    if isinstance(path, str) and path:
        return path
    return ""


def targets_ledger(file_path: str, cwd: str) -> bool:
    """True when `file_path` (joined against `cwd` if not absolute) names
    the same on-disk path `emit_boundary_event()` itself resolves and
    writes to — `artifact_paths.resolve_file("metrics", ...)` under the
    repo root, not a bare `.claude/metrics/` prefix match (so
    `review-verdicts.jsonl`, Slice 2's own store, is unaffected) — OR the
    pre-migration legacy path `<project-root>/metrics/boundary-events.jsonl`
    (review finding, #2171): `resolve_file(..., migrate=True)`, the default
    every `emit_boundary_event()` call uses, `shutil.move`s an untracked
    file at that legacy path into the ledger the *next* time anything
    emits, whenever the new-location file does not yet exist. Matching
    only the new-location path would let a Write/Edit plant a forged file
    at the legacy path — invisible to this guard — that a later, entirely
    legitimate `emit_boundary_event()` call then silently promotes into
    ledger history. Both candidates must be blocked for the guard's
    forgery-cost claim to hold.

    The `cwd` anchor is realpath'd before the join (review finding): the
    ledger side already resolves symlinks transparently, because
    `artifact_paths.resolve_file()` -> `project_root()` finds the repo root
    via `git rev-parse --show-toplevel`, and git itself resolves a
    symlinked `cwd` to its real location. Joining `file_path` against the
    *unresolved* `cwd` string, then comparing both sides with only
    `os.path.abspath` (no symlink resolution), left the two sides
    comparing a symlinked-form candidate against a resolved-form ledger —
    a real, if narrow, false negative on a symlinked `cwd`. Resolving only
    the `cwd` anchor keeps this guard's `os.path.abspath` comparison the
    same symmetric idiom `pre_tool_guard.py` uses elsewhere, without
    resolving symlinks anywhere else in the path (module docstring)."""
    if not file_path:
        return False
    base = Path(os.path.realpath(cwd)) if cwd else Path.cwd()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate_norm = os.path.abspath(str(candidate))

    # Cheap lexical pre-check (performance review finding, #2171): every
    # candidate this function can match ends in `_LEDGER_NAME` — skip the
    # `git rev-parse` subprocess `resolve_stream()`/`project_root()` incur
    # for the overwhelming majority of Write/Edit calls that plainly don't.
    if os.path.basename(candidate_norm) != _LEDGER_NAME:
        return False

    ledger = _resolve_ledger_stream("metrics", _LEDGER_NAME, Path(cwd) if cwd else Path.cwd())
    ledger_norm = os.path.abspath(str(ledger))
    if candidate_norm == ledger_norm:
        return True

    legacy_ledger = artifact_paths.project_root(start=cwd) / "metrics" / _LEDGER_NAME
    legacy_norm = os.path.abspath(str(legacy_ledger))

    return candidate_norm == legacy_norm


def _extract_command(tool_input: object) -> str:
    """Return `tool_input.command`, or empty string — mirrors
    `destructive_guard._extract_command`'s field access."""
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


# Any prefix of path characters ending in the ledger's literal filename.
# Matches the filename in every ordinary path form the plan requires
# (relative, absolute, "./"-prefixed, bare after a `cd .claude/metrics`
# prefix, `~/`-prefixed, `$VAR`/`${VAR}`-expanded, or a quoted path
# containing a space), since all of those literally end in this substring.
# Widening this class is not an attempt at obfuscation-grade path matching
# (shell escapes, `$(...)` substitution, base64-encoded paths, etc. remain
# out of scope — see the module docstring's "heuristic, not a sandbox"
# note); it only covers path forms a real command would ordinarily write.
_LEDGER_PATH_SUFFIX = r"[\w./~${} -]*" + re.escape(_LEDGER_NAME)

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
    # `tee` writing to the ledger, within the same shell statement (same
    # same-statement scoping as the cp/mv/rm pattern below) — the ledger
    # can be any of tee's operands (`tee /tmp/log boundary-events.jsonl`),
    # not just its first.
    re.compile(rf"\btee\b[^;|&\n]*['\"]?{_LEDGER_PATH_SUFFIX}"),
    # `sed -i`/`sed --in-place` (in-place edit) targeting the ledger, within
    # the same shell statement (stops at `;`/`|`/`&` so an unrelated later
    # statement that happens to also mention the ledger doesn't
    # false-positive).
    re.compile(
        rf"\bsed\b[^;|&\n]*(?:-i\b|--in-place\b)[^;|&\n]*['\"]?{_LEDGER_PATH_SUFFIX}"
    ),
    # cp/mv/rm/truncate/dd targeting the ledger, within the same shell
    # statement (same same-statement scoping as the sed pattern above).
    re.compile(rf"\b(?:cp|mv|rm|truncate|dd)\b[^;|&\n]*{_LEDGER_PATH_SUFFIX}"),
    # A Python `open(...)` call on the ledger using any mode that permits
    # writing: "w"/"a"/"x" (optionally suffixed, e.g. "wb"/"a+"/"x+"), or a
    # "+" read-write mode such as "r+"/"rb+"/"r+b" — any mode string
    # containing w/a/x/+ can write. The mode may be positional or the
    # keyword form (`mode='a'`). "Allowed" means read-ONLY: a mode-omitted
    # (default "r") or explicit pure-"r" `open()` never matches this
    # pattern — not "read-mode" generically, since "r+" is a read-*and*-
    # write mode despite starting with "r".
    re.compile(
        rf"open\(\s*['\"]{_LEDGER_PATH_SUFFIX}['\"]\s*,\s*"
        r"(?:mode\s*=\s*)?['\"][^'\"]*[wax+][^'\"]*['\"]"
    ),
)


def bash_command_writes_to_ledger(command: str) -> bool:
    """True when `command` is write-shaped AND targets the ledger by
    filename, in any path form — see `_BASH_WRITE_SHAPE_PATTERNS`. A
    read-shaped command referencing the same filename (`cat`, `grep`,
    `tail`, `head`, a read-mode `open()`) never matches any pattern here,
    so it is allowed without a separate read-allowlist check.

    O(n) fast path first (security review finding, #2171): every pattern in
    `_BASH_WRITE_SHAPE_PATTERNS` requires the literal `_LEDGER_NAME`
    substring, so a command that lacks it cannot match any of them — this
    is semantically equivalent to running the patterns, not a heuristic
    shortcut. Skipping straight to `False` on a long non-matching command
    (e.g. a `rm` of padding data) avoids the patterns' overlapping
    `[^;|&\\n]*`/path-suffix character classes backtracking quadratically
    on input that was never going to match."""
    if not command or _LEDGER_NAME not in command:
        return False
    return any(pattern.search(command) for pattern in _BASH_WRITE_SHAPE_PATTERNS)


def _block(
    cwd: str,
    tool: str,
    session_id: str | None,
    blocked_message: str,
    remedy_message: str,
) -> int:
    """Shared block sequence for both `main()` branches: record the guard's
    own decision (every sibling guard does — see the module docstring),
    print the block explanation, and return the block exit code.

    Mirrors every line to stderr in addition to stdout (docs/python-hook-
    contract.md § stderr, "Exception — exit-2 (block) messages"): some
    Claude Code hook-error wrappers surface only stderr on a nonzero hook
    exit, so a stdout-only block message can go unseen there. Stdout stays
    the canonical channel; stderr is additive duplication for this exit-2
    path only — this is a new hook, so it converges to the documented
    standard from the start rather than joining the stdout-only legacy list."""
    emit_boundary_event(
        cwd, "boundary_events_write_guard", tool, "block", "ledger-write-blocked", session_id
    )
    lines = (
        blocked_message,
        (
            "This file is the boundary-events accountability ledger (#859) — "
            "it is append-only from the session's perspective."
        ),
        remedy_message,
    )
    for line in lines:
        print(line)
    for line in lines:
        print(line, file=sys.stderr)
    return 2


def _handle_bash_tool(payload: dict, cwd: str, session_id: str | None) -> int:
    command = _extract_command(payload.get("tool_input"))
    if not bash_command_writes_to_ledger(command):
        return 0

    events = "|".join(_cli_event_names())
    return _block(
        cwd,
        "Bash",
        session_id,
        f"BLOCKED: This Bash command writes to '.claude/metrics/{_LEDGER_NAME}', "
        "which is not allowed.",
        "Use 'python3 plugins/dev-team/hooks/lib/boundary_events.py "
        f"--event <{events}> "
        "--subject-hash <hash> ...' instead of writing to it from Bash — "
        "an arbitrary row isn't CLI-constructible by design (that CLI only "
        "accepts a closed --event vocabulary); this exact row needs a "
        "Python-side hook change instead.",
    )


def _handle_write_edit_tool(
    payload: dict, cwd: str, tool: str, session_id: str | None
) -> int:
    file_path = _extract_file_path(payload.get("tool_input"))
    if not file_path:
        return 0

    if not targets_ledger(file_path, cwd):
        return 0

    return _block(
        cwd,
        tool,
        session_id,
        f"BLOCKED: Direct write to '{file_path}' is not allowed.",
        "Use emit_boundary_event() in plugins/dev-team/hooks/lib/boundary_events.py "
        "instead of writing to it directly.",
    )


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
            return _handle_bash_tool(payload, cwd, session_id)

        return _handle_write_edit_tool(payload, cwd, tool, session_id)
    except Exception:  # noqa: BLE001 - fail-open by design, see module docstring
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
