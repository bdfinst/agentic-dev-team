#!/usr/bin/env python3
"""autocompact_setup_nudge — Claude Code SessionStart hook (#2177, slice 3).

The plugin no longer forces a handoff at a context ceiling; instead
`/dev-team:setup` sets the harness's own `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`.
That makes `/setup` load-bearing, so this hook advises running it when a repo
shows no sign it has been.

Channel: plain stdout (`sys.stdout.write`), matching the other nudge hooks
(`repo_review_nudge.py`, `mcp_json_repowise_nudge.py`). Like them it is
self-silencing from state — once the key is configured it never prints — and
has no once-per-session marker.

- Key absent (process env, settings.local.json, settings.json, user settings):
  one advisory line.
- Key present but invalid (not an integer 1-100): one corrective line.
- Key valid, opted out, or SessionStart source is "compact": silent.

Opt-out: `DEV_TEAM_AUTOCOMPACT_NUDGE=0` or the marker file
`.claude/memory/autocompact-nudge-off` (written by `/setup --no-autocompact`).

Project dir: `$CLAUDE_PROJECT_DIR`, else the payload `cwd`, else the process
cwd. Advisory only: fail-open, always exits 0, never blocks session start.
Stdlib only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from autocompact_config import KEY, Status, detect  # type: ignore[import-not-found]
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]

OPT_OUT_ENV = "DEV_TEAM_AUTOCOMPACT_NUDGE"
OPT_OUT_MARKER = Path(".claude") / "memory" / "autocompact-nudge-off"

ABSENT_MESSAGE = (
    "dev-team: context autocompact is not configured for this repo; "
    "run /dev-team:setup to set it (default 40%). "
    f"Silence: {OPT_OUT_ENV}=0 or create {OPT_OUT_MARKER.as_posix()}\n"
)


def invalid_message(raw: object) -> str:
    return (
        f"dev-team: {KEY}={raw!r} is invalid (need integer 1-100); "
        "re-run /dev-team:setup\n"
    )


def _project_dir(payload: dict) -> Path:
    override = os.environ.get("CLAUDE_PROJECT_DIR")
    if override and Path(override).is_dir():
        return Path(override)
    return Path(resolve_cwd(payload))


def message_for(payload: dict) -> str:
    """The text to print, or '' when the hook should stay silent."""
    if payload.get("source") == "compact":
        return ""
    if os.environ.get(OPT_OUT_ENV) == "0":
        return ""
    project = _project_dir(payload)
    if (project / OPT_OUT_MARKER).exists():
        return ""
    detection = detect(project, os.environ)
    if detection.status is Status.ABSENT:
        return ABSENT_MESSAGE
    if detection.status is Status.INVALID:
        return invalid_message(detection.raw)
    return ""


def main() -> int:
    try:
        text = message_for(read_stdin_json() or {})
        if text:
            sys.stdout.write(text)
    except Exception:  # noqa: BLE001 - advisory hook: never block session start
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
