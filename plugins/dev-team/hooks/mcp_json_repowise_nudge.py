#!/usr/bin/env python3
"""mcp_json_repowise_nudge — Claude Code SessionStart hook (#1747).

`project-init/SKILL.md`'s `.mcp.json` standing check can only relocate a
stale, git-tracked `repowise` entry when someone actually runs
`/project-init` (or `/setup`). For an already-initialized project, nobody
is prompted to do that — the entry sits untouched indefinitely. This hook
is that proactive nudge, mirroring `pending_review_notify.py`'s /
`repo_review_nudge.py`'s shape: read a small state signal, print a one-line
stdout notice, fail-open, stdlib-only.

Shares its detection predicate — `hooks/lib/mcp_json_repowise.py::detect()`
— with the standing check itself (invoked from skill markdown via that
module's own CLI), so the two can never disagree on what counts as "needs
fixing" (#1747's single-commit requirement: this hook is meaningless
without that module's `relocate()` existing, so the two ship together).

Nudges every session until the condition clears (no snooze/debounce) — same
posture as the existing pending-review-queue and repo-review nudges.

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
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

try:
    from mcp_json_repowise import detect  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def detect(cwd):  # type: ignore[misc]
        return None


_NUDGE_MESSAGE = (
    "⚠️ .mcp.json is git-tracked and registers repowise with a "
    "machine-specific path (breaks for every other clone/teammate) — run "
    "/project-init (or /setup) to relocate it to local scope\n"
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

    if detect(Path(cwd)) is None:
        return 0

    sys.stdout.write(_NUDGE_MESSAGE)
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a session
        sys.exit(0)
