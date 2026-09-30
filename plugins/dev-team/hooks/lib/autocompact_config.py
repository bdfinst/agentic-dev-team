"""Detect whether harness autocompact is configured (#2177, slice 2).

Single decider used by both `scripts/set_autocompact_env.py` (the `/setup`
writer) and `hooks/autocompact_setup_nudge.py`. Import direction is
scripts -> hooks/lib; this module never imports from `scripts/` or
`.claude/lib`.

The harness env var `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is an integer 1-100
(percent of the auto-compact window). Values above the harness default are
ignored, so the variable can only lower the threshold. `HARNESS_DEFAULT_PCT`
(~83) is REPORTED, not confirmed against primary docs.

Sources consulted, highest precedence first: the process environment,
`.claude/settings.local.json`, `.claude/settings.json`, then the user
settings (`$CLAUDE_CONFIG_DIR/settings.json`, else `~/.claude/settings.json`).
The first source that defines the key decides. An unreadable or malformed
settings file is skipped, never raised.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

KEY = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
DEFAULT_PCT = 40
HARNESS_DEFAULT_PCT = 83  # reported, not verified against primary docs

# Plain ASCII integer 1-100: no sign, no whitespace, no decimal point, no leading zero.
_PCT_RE = re.compile(r"(?:100|[1-9][0-9]?)")


class Status(Enum):
    CONFIGURED = "configured"
    INVALID = "invalid"
    ABSENT = "absent"


@dataclass(frozen=True)
class Detection:
    status: Status
    raw: object = None
    source: str | None = None


def validate_pct(raw: object) -> int | None:
    """Return the integer percent for a valid string 1-100, else None."""
    if not isinstance(raw, str) or not _PCT_RE.fullmatch(raw):
        return None
    return int(raw)


def user_settings_path(env: Mapping[str, str]) -> Path:
    cfg = env.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return Path(cfg) / "settings.json"
    home = env.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".claude" / "settings.json"


def _env_block(path: Path) -> Mapping[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError, RuntimeError):
        return None
    block = data.get("env") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else None


def detect(project_dir: str | Path, env: Mapping[str, str]) -> Detection:
    """Find the first source defining the key and classify its value."""
    if KEY in env:
        raw = env[KEY]
        return Detection(
            Status.CONFIGURED if validate_pct(raw) is not None else Status.INVALID,
            raw,
            "process env",
        )
    root = Path(project_dir)
    candidates = (
        ("settings.local.json", root / ".claude" / "settings.local.json"),
        ("settings.json", root / ".claude" / "settings.json"),
        ("user settings.json", user_settings_path(env)),
    )
    for label, path in candidates:
        block = _env_block(path)
        if block is not None and KEY in block:
            raw = block[KEY]
            ok = validate_pct(raw) is not None
            return Detection(Status.CONFIGURED if ok else Status.INVALID, raw, label)
    return Detection(Status.ABSENT)


def autocompact_configured(project_dir: str | Path, env: Mapping[str, str]) -> Status:
    """CONFIGURED (valid), INVALID (present, bad value) or ABSENT."""
    return detect(project_dir, env).status
