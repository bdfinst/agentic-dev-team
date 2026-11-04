#!/usr/bin/env python3
"""PreToolUse Write|Edit hook: refuse a plan or spec write that breaks the feature record (#2275).

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


def target_path(payload: dict) -> tuple[str, str] | None:
    """Return `(absolute, relative)` for the payload's `file_path`, or `None`.

    The path is resolved against the payload `cwd` (the process directory when
    absent) and must lie inside it. Pure string work: no file is touched.
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
    try:
        rel = os.path.relpath(absolute, base)
    except ValueError:  # another drive on Windows
        return None
    parts = rel.split(os.sep)
    if parts[0] == os.pardir or os.path.isabs(rel):
        return None
    return absolute, "/".join(parts)


# ---------------------------------------------------------------------------
# Payload layer
# ---------------------------------------------------------------------------


def proposed_text(payload: dict, read_text) -> tuple[str, str] | None:
    """Return `(before, after)` text for the write, or `None` when the hook
    cannot judge it and must allow.

    `read_text(path)` returns the file text; it may raise. `Write` proposes
    its `content`. `Edit` applies `old_string` to `new_string` on the on-disk
    text, only when `old_string` is non-empty and occurs exactly once (so
    `replace_all` with several matches is not judged). The before-text of a
    file that does not exist is empty. Any other read error means "cannot
    judge".
    """
    target = target_path(payload)
    if target is None:
        return None
    tool_input = payload["tool_input"]
    try:
        before = read_text(target[0])
    except FileNotFoundError:
        before = ""
    except (OSError, UnicodeError):
        return None

    tool = payload.get("tool_name")
    if tool == "Write":
        content = tool_input.get("content")
        return (before, content) if isinstance(content, str) else None
    if tool == "Edit":
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            return None
        if before.count(old) != 1:
            return None
        return before, before.replace(old, new, 1)
    return None


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


def _load_record():
    """Import `scripts/feature_record.py`, only after a path match.

    `hooks/` reaches into `scripts/` here the way `review_verdict_recorder.py`
    reaches into `scripts/lib/`: both ship inside this plugin, and neither
    `feature_record` nor its helpers import anything from `hooks/` (no cycle).
    The paths are appended so a `hooks/lib` module is never shadowed.
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
    record = _load_record()
    if kind == PLAN:

        def check(text: str) -> list[dict]:
            return record.plan_violations(text, spec_text=None)

    else:
        check = record.spec_violations
    before, after = texts
    # An empty before-state (a new file) has nothing to compare with, so every
    # violation of the proposed text is introduced. Checking "" would not do:
    # `spec_violations("")` already reports all three missing sections.
    known = check(before) if before else []
    return record.introduced(known, check(after))


def _skip(reason: str) -> int:
    sys.stderr.write(f"feature record check skipped: {reason}\n")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0
    target = target_path(payload)
    if target is None or matches(target[1]) is None:
        return 0
    if os.environ.get(ESCAPE_ENV, "").strip().lower() == "off":
        return _skip(f"{ESCAPE_ENV}=off")
    try:
        found = decide(payload, _read_text)
    except Exception as exc:  # noqa: BLE001 - fail open by design
        detail = (str(exc).splitlines() or [""])[0]
        return _skip(f"{type(exc).__name__}: {detail}".rstrip(": "))
    if not found:
        return 0
    sys.stderr.write(
        f"[BLOCK] feature record: {target[1]} - {len(found)} violation(s) introduced\n"
    )
    for violation in found:
        sys.stderr.write(violation["what"] + "\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
