"""telemetry_consent.py — shared, home-scoped telemetry consent check (#1405).

Single source of truth for whether the user has opted in to the plugin's
local telemetry writers. Reads **only** `~/.claude/telemetry.json` —
deliberately no environment-variable branch and no project-scoped
(`<cwd>/.claude/telemetry.json`) fallback. Consent is a user-level decision,
not a per-project or per-invocation one.

Fail-open: a missing file, a malformed file, or any read error is treated as
"not enabled" — never raises, never blocks the calling hook.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
from pathlib import Path


def _consent_path() -> Path:
    return Path.home() / ".claude" / "telemetry.json"


def is_enabled() -> bool:
    """Return True only when `~/.claude/telemetry.json` contains
    `{"enabled": true}`. Any other state — file absent, malformed JSON,
    `"enabled"` false or missing, or a read error — returns False."""
    config = _consent_path()
    try:
        if not config.is_file():
            return False
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return data.get("enabled") is True
