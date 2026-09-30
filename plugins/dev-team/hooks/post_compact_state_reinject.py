#!/usr/bin/env python3
"""post_compact_state_reinject — Claude Code SessionStart hook (#2177, slice 4).

Harness auto-compact replaces the conversation with a generic summary;
plan-step state is not guaranteed to survive. Matcher `compact` fires
`SessionStart` with `source: "compact"` after compaction, and this hook
re-injects the active `/build` state as `additionalContext`:

    Restored after compaction: phase=refactor step=2.3 plan=plans/foo.md. Unchecked: 2.3, 2.4.

State comes from the one shared reader, `hooks/lib/build_state.py`
(`.claude/memory/build-phase.json`, written by `/build`); the plan file is
the path recorded there — never a glob. Unchecked items are the `- [ ]`
lines under the plan's `## Build Progress`. Between steps (`/build` keeps a
`between-steps` record) the line reads "between steps, next step=N.M". Plans that live only in an
issue (no local file) degrade to phase/step. No active state -> no output.

Budget: `additionalContext` is capped at 10,000 characters by the harness.
Truncation priority is phase/step > plan path > items; items are dropped
last-first and the text then ends with `...[truncated; see plan file]`.
Counts are characters, never bytes, and never split a code point.

The injected text is repo-derived data: control characters are stripped and
every field is length-bounded. A `systemMessage` gives the user a visible
line. Fail-open: always exits 0. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from build_state import (  # type: ignore[import-not-found]
    BETWEEN_STEPS,
    read_active_build_state,
)
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]

MAX_CONTEXT_CHARS = 10_000
TRUNCATION_MARKER = "...[truncated; see plan file]"
_MAX_FIELD = 64
_MAX_PATH = 512
_MAX_ITEM = 200
_MAX_PLAN_BYTES = 2_000_000

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_HEADING_RE = re.compile(r"^##\s+(.*?)\s*$")
_UNCHECKED_RE = re.compile(r"^\s*[-*]\s+\[ \]\s+(.*?)\s*$")


def _clean(text: str, limit: int) -> str:
    return _CONTROL_RE.sub(" ", text).strip()[:limit]


def unchecked_items(plan_text: str) -> list[str]:
    """`- [ ]` items under `## Build Progress` (until the next `## ` heading)."""
    items: list[str] = []
    in_section = False
    for line in plan_text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            in_section = heading.group(1).lower() == "build progress"
            continue
        if not in_section:
            continue
        match = _UNCHECKED_RE.match(line)
        if match:
            item = _clean(match.group(1), _MAX_ITEM)
            if item:
                items.append(item)
    return items


def assemble(
    phase: str,
    step: str,
    plan_path: str | None,
    items: list[str],
    limit: int = MAX_CONTEXT_CHARS,
) -> str:
    """Build the injected text within `limit` characters (priority-truncated)."""
    if phase == BETWEEN_STEPS:
        head = f"Restored after compaction: between steps, next step={step}"
    else:
        head = f"Restored after compaction: phase={phase} step={step}"
    if plan_path:
        head += f" plan={plan_path}"
    if not items:
        return head[:limit]

    prefix = head + ". Unchecked: "
    # Lengths are computed arithmetically so the work is linear in len(items):
    # the text is rendered once, never re-built per dropped item.
    total = len(prefix) + sum(map(len, items)) + 2 * (len(items) - 1) + 1
    if total <= limit:
        return prefix + ", ".join(items) + "."

    used = len(prefix) + 1 + len(TRUNCATION_MARKER)  # trailing "." + marker
    kept = 0
    for item in items:
        cost = len(item) + (2 if kept else 0)
        if used + cost > limit:
            break
        used += cost
        kept += 1
    if kept:
        return prefix + ", ".join(items[:kept]) + "." + TRUNCATION_MARKER
    return (head + TRUNCATION_MARKER)[:limit]


def _project_dir(payload: dict) -> Path:
    override = os.environ.get("CLAUDE_PROJECT_DIR")
    if override and Path(override).is_dir():
        return Path(override)
    return Path(resolve_cwd(payload))


def _plan_items(project: Path, plan_path: str | None) -> list[str]:
    if not plan_path:
        return []
    try:
        plan = project / plan_path
        if plan.stat().st_size > _MAX_PLAN_BYTES:
            return []
        return unchecked_items(plan.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


def build_output(payload: dict) -> str:
    """The JSON to print, or '' when there is nothing to restore."""
    if payload.get("source") != "compact":
        return ""
    project = _project_dir(payload)
    state = read_active_build_state(project)
    if state is None:
        return ""
    phase = _clean(state.phase, _MAX_FIELD)
    step = _clean(state.step, _MAX_FIELD)
    plan_path = _clean(state.plan_path, _MAX_PATH) if state.plan_path else None
    text = assemble(phase, step, plan_path, _plan_items(project, state.plan_path))
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": text,
            },
            "systemMessage": f"dev-team: restored build state (step {step}) after compaction",
        }
    )


def main() -> int:
    try:
        out = build_output(read_stdin_json() or {})
        if out:
            sys.stdout.write(out + "\n")
    except Exception:  # noqa: BLE001 - must never error or block the session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
