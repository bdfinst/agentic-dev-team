#!/usr/bin/env python3
"""PreToolUse Write|Edit hook: refuse a plan or spec write that breaks the feature record.

A write to a plan (`plans/*.md`, `docs/specs/*/plans/*.md`) or a spec
(`docs/specs/*.md`, `docs/specs/*/spec.md`) is checked against the invariants
in `scripts/feature_record.py`. The hook refuses (exit 2) only a violation the
write introduces; it never judges the commit invariant.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with cwd, tool_name and
            tool_input.{file_path, content | old_string, new_string}
    Output: exit 0 = allow
            exit 2 = block; the message is on stderr
    Env   : DEV_TEAM_FEATURE_RECORD_GUARD=off allows every write

Fail open: a payload or file the hook cannot judge, and any internal error,
allows the write.

Stdlib-only. Only `sys` and `os` are imported at the top, plus the shared
stdin reader. A path outside the matcher returns before any file read and
before `feature_record` is imported.
"""

from __future__ import annotations

import os
import sys

_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_HOOK_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from stdin_json import read_stdin_json

ESCAPE_ENV = "DEV_TEAM_FEATURE_RECORD_GUARD"
HOOK_NAME = "feature_record_guard"
RULE_ID = "feature-record-violation"
MAX_BLOCKS = 5
# Appended to every HOW line of an Edit refusal: the hook checks the state
# after each write, so a change that is invalid midway must go in one write.
EDIT_HOW_SUFFIX = (
    " Make the change in a single Edit or Write;"
    " the hook checks the state after each write."
)

PLAN = "plan"
SPEC = "spec"


# ---------------------------------------------------------------------------
# Path layer
# ---------------------------------------------------------------------------


def matches(rel_path: str) -> str | None:
    """Return `"plan"` or `"spec"` for a checked path, else `None`.

    `rel_path` is posix-style and relative to the working directory. Checked:
    `plans/*.md`, `docs/specs/*.md`, `docs/specs/*/spec.md` and
    `docs/specs/*/plans/*.md`. A file named `README.md` is skipped.
    """
    parts = rel_path.split("/")
    name = parts[-1]
    if name == "README.md" or not name.endswith(".md"):
        return None
    count = len(parts)
    if count == 2 and parts[0] == "plans":
        return PLAN
    if parts[:2] == ["docs", "specs"]:
        if count == 3:
            return SPEC
        if count == 4 and name == "spec.md":
            return SPEC
        if count == 5 and parts[3] == "plans":
            return PLAN
    return None


def _relative_inside(absolute: str, base: str) -> str | None:
    """Return the posix path of `absolute` relative to `base`, or `None` when
    it lies outside `base`."""
    try:
        rel = os.path.relpath(absolute, base)
    except ValueError:  # another drive on Windows
        return None
    parts = rel.split(os.sep)
    if parts[0] == os.pardir or os.path.isabs(rel):
        return None
    return "/".join(parts)


def target_path(payload: dict) -> tuple[str, str] | None:
    """Return `(absolute, relative)` for the payload's `file_path`, or `None`.

    The path is resolved against the payload `cwd` (the process directory when
    absent) and must lie inside it. When the plain comparison lands outside,
    both sides are resolved through symlinks and compared again, so a symlinked
    checkout (or macOS `/tmp`) still matches. No file is read.
    """
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    cwd = payload.get("cwd")
    base = os.path.abspath(cwd if isinstance(cwd, str) and cwd else os.getcwd())
    absolute = os.path.abspath(os.path.join(base, file_path))
    rel = _relative_inside(absolute, base)
    if rel is None:
        absolute = os.path.realpath(absolute)
        rel = _relative_inside(absolute, os.path.realpath(base))
        if rel is None:
            return None
    return absolute, rel


# ---------------------------------------------------------------------------
# Payload layer
# ---------------------------------------------------------------------------


def proposed_text(payload: dict, read_text) -> tuple[str | None, str] | None:
    """Return `(before, after)` text for the write, or `None` when the hook
    cannot judge it and must allow.

    `read_text(path)` returns the file text; it may raise. `Write` proposes
    its `content`. `Edit` applies `old_string` to `new_string` on the on-disk
    text, only when `old_string` is non-empty and occurs exactly once (so
    `replace_all` with several matches is not judged). `before` is `None` for
    a file that does not exist, which is not the same as an existing empty
    file (`""`); an `Edit` with an empty `old_string` on a missing file
    creates it. Any other read error means "cannot judge".
    """
    target = target_path(payload)
    if target is None:
        return None
    tool_input = payload["tool_input"]
    try:
        before: str | None = read_text(target[0])
    except FileNotFoundError:
        before = None
    except (OSError, UnicodeError):
        return None

    tool = payload.get("tool_name")
    if tool == "Write":
        content = tool_input.get("content")
        return (before, content) if isinstance(content, str) else None
    if tool == "Edit":
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        if before is None:
            # An Edit with an empty old_string creates a file that does not
            # exist yet, like a Write. Any other Edit on a missing file is not
            # judged.
            return (None, new) if not old else None
        if not old or before.count(old) != 1:
            return None
        return before, before.replace(old, new, 1)
    return None


def _read_text(path: str) -> str:
    # Default newline translation: a multi-line `old_string` written with LF
    # must match a CRLF file, as the Edit tool matches it.
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


def _import_feature_record():
    """Import `scripts/feature_record.py`, only after a path match.

    `hooks/` reaches into `scripts/` here the way `review_verdict_recorder.py`
    reaches into `scripts/lib/`: both ship inside this plugin, and neither
    `feature_record` nor its helpers import anything from `hooks/` (no cycle).
    `scripts/` and `scripts/lib` are appended to `sys.path`, so a module of the
    same name earlier on the path (`hooks/`, `hooks/lib`) wins. `feature_record`
    also puts `scripts/lib` at the front of `sys.path` itself, but only when
    its resolved path is not already listed, so with the append here it adds
    nothing in a normal checkout; under a symlinked plugin directory it can.
    """
    scripts = os.path.join(os.path.dirname(_HOOK_DIR), "scripts")
    for path in (scripts, os.path.join(scripts, "lib")):
        if path not in sys.path:
            sys.path.append(path)
    import feature_record

    return feature_record


def decide(payload: dict, read_text) -> list[dict]:
    """Return the violations the write would introduce; empty means allow.

    Pure apart from `read_text`. A plan is checked without its spec
    (`spec_text=None`); a spec is checked on its own, only when the spec file
    itself is written. Only violations absent before the write count.
    """
    target = target_path(payload)
    kind = matches(target[1]) if target else None
    if kind is None:
        return []
    texts = proposed_text(payload, read_text)
    if texts is None:
        return []
    feature_record_module = _import_feature_record()
    if kind == PLAN:

        def check(text: str) -> list[dict]:
            return feature_record_module.plan_violations(text, spec_text=None)

    else:
        check = feature_record_module.spec_violations
    before, after = texts
    # A file that does not exist has nothing to compare with, so every
    # violation of the proposed text is introduced. Checking "" would not do:
    # `spec_violations("")` already reports all three missing sections. An
    # existing empty file does have a before-state, and it is checked.
    known = [] if before is None else check(before)
    return feature_record_module.introduced(known, check(after))


def format_refusal(rel_path: str, found: list[dict], tool: str | None) -> str:
    """Return the refusal text: a `[BLOCK]` header, then WHAT / WHY / HOW per
    violation, at most `MAX_BLOCKS` of them. The words come from the violations
    themselves, which `feature_record` fills from its one copy table."""
    lines = [
        f"[BLOCK] feature record: {rel_path} - {len(found)} violation(s) introduced"
    ]
    for violation in found[:MAX_BLOCKS]:
        how = violation["how"] + (EDIT_HOW_SUFFIX if tool == "Edit" else "")
        lines += [
            "",
            f"WHAT: {violation['what']}",
            f"WHY: {violation['why']}",
            f"HOW: {how}",
        ]
    if len(found) > MAX_BLOCKS:
        lines += ["", f"and {len(found) - MAX_BLOCKS} more."]
    return "\n".join(lines) + "\n"


def emit_boundary_event(*args, **kwargs) -> None:
    """Record the refusal. A failing emitter, or a missing helper, must never
    change this hook's exit code or output (same safety net as
    `verify_guard.py`). The import is local so an allowed write never pays it."""
    try:
        from boundary_events import emit_boundary_event as _emit

        _emit(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def _skip(reason: str) -> int:
    try:
        sys.stderr.write(f"feature record check skipped: {reason}\n")
    except (OSError, ValueError):  # stderr closed: still allow
        pass
    return 0


def _check() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0
    target = target_path(payload)
    if target is None or matches(target[1]) is None:
        return 0
    if os.environ.get(ESCAPE_ENV, "").strip().lower() == "off":
        return _skip(f"{ESCAPE_ENV}=off")
    found = decide(payload, _read_text)
    if not found:
        return 0
    tool = payload.get("tool_name")
    message = format_refusal(target[1], found, tool)
    # Stderr is what Claude Code surfaces on a block; stdout mirrors it as the
    # hook contract asks of an exit-2 hook.
    sys.stderr.write(message)
    sys.stdout.write(message)
    cwd = payload.get("cwd")
    session_id = payload.get("session_id")
    emit_boundary_event(
        cwd if isinstance(cwd, str) and cwd else os.getcwd(),
        HOOK_NAME,
        tool if isinstance(tool, str) else "Write",
        "block",
        RULE_ID,
        session_id if isinstance(session_id, str) else None,
    )
    return 2


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Check one write. Any error, in reading the payload, resolving the
    working directory, judging the write or printing the refusal, allows the
    write with a one-line notice. `SystemExit` and `KeyboardInterrupt` are not
    swallowed."""
    try:
        return _check()
    except Exception as exc:  # noqa: BLE001 - fail open by design
        detail = (str(exc).splitlines() or [""])[0]
        return _skip(f"{type(exc).__name__}: {detail}".rstrip(": "))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
