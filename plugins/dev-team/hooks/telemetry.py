#!/usr/bin/env python3
"""telemetry.py — opt-in, privacy-clean telemetry beacon (Python port of telemetry.sh).

The plugin enforces observability on its targets but has none of its own.
This records MINIMAL local events so the author can see which commands /
skills get used and how often the pre-commit review gate is bypassed.

One hook registered on multiple events; it branches on `hook_event_name`:

  UserPromptSubmit    — user-typed slash command; record its name only.
  PreToolUse (Skill)  — skill invoked by user OR agent/model; record its name.
  PreToolUse (Bash)   — `git commit`: record the review gate as fired, or
                        BYPASSED when --no-verify or a bare `-n` argument is
                        present.

PRIVACY: records only an event type, a grammar-matched name (never free
text), an outcome, and the plugin version.

CONSENT: OFF by default. Enable with `DEV_TEAM_TELEMETRY=on`, or a
`<cwd>/.claude/telemetry.json` containing `{"enabled": true}`. When off,
nothing is recorded and nothing leaves the machine.

TRANSPORT: local-only. Events append to `<cwd>/metrics/telemetry.jsonl`.
No network egress.

Posture: record-only, fail-open. Never blocks; any error → exit 0.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


_SLASH_CMD_RE = re.compile(r"^/([a-zA-Z][a-zA-Z0-9_-]*)")
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_:-]*$")
_NO_VERIFY_RE = re.compile(r"(?:^|\s)-n(?:\s|$)")

# Human-intervention keyword grammar (#859, Ambiguity Log): anchored
# whole-prompt match — same grammar-match-only posture as _SLASH_CMD_RE —
# substring matching would flood the stream with false positives on
# ordinary prose ("stop" mid-sentence must NOT match). An optional
# `:`-suffixed payload following the keyword is captured by the prompt
# but deliberately discarded — never logged.
_INTERVENTION_RE = re.compile(r"^\s*(override|pause|stop)\b", re.IGNORECASE)


def _isoformat_utc() -> str:
    # Match bash `date -u +%Y-%m-%dT%H:%M:%SZ`.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_plugin_version(hook_dir: Path) -> str:
    manifest = hook_dir / ".." / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text())
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _consent_enabled(cwd: Path) -> bool:
    """Return True when telemetry is opted in for the current cwd.

    Env var `DEV_TEAM_TELEMETRY=on` takes precedence; failing that, a
    `<cwd>/.claude/telemetry.json` containing `{"enabled": true}` also
    enables it. `{"enabled": false}` in that file only affects the
    `artifact-usage.json` sub-emitter (see `_artifact_usage_disabled`).
    """
    if os.environ.get("DEV_TEAM_TELEMETRY") == "on":
        return True
    config = cwd / ".claude" / "telemetry.json"
    if not config.is_file():
        return False
    try:
        data = json.loads(config.read_text())
    except (OSError, ValueError):
        return False
    return bool(data.get("enabled") is True)


def _artifact_usage_disabled(cwd: Path) -> bool:
    """Return True when telemetry.json explicitly disables usage tracking."""
    config = cwd / ".claude" / "telemetry.json"
    if not config.is_file():
        return False
    try:
        data = json.loads(config.read_text())
    except (OSError, ValueError):
        return False
    return data.get("enabled") is False


def _emit(log: Path, event: str, name: str, outcome: str, version: str) -> None:
    """Append one JSONL event to `log`. Fail-open on any error."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    payload = {
        "ts": _isoformat_utc(),
        "event": event,
        "name": name,
        "outcome": outcome,
        "plugin_version": version,
    }
    try:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _upsert_artifact_usage(cwd: Path, skill: str) -> None:
    """Atomically bump the use count for `skill` in artifact-usage.json."""
    if _artifact_usage_disabled(cwd):
        return
    usage_dir = cwd / "metrics"
    usage_file = usage_dir / "artifact-usage.json"
    try:
        usage_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    existing: dict = {}
    if usage_file.is_file():
        try:
            existing = json.loads(usage_file.read_text())
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            sys.stderr.write(
                "WARN: metrics/artifact-usage.json contained malformed JSON; discarding\n"
            )
            existing = {}

    ts = _isoformat_utc()
    if skill not in existing or not isinstance(existing.get(skill), dict):
        existing[skill] = {"use_count": 1, "last_used_at": ts, "lifecycle": "active"}
    else:
        current = existing[skill]
        current["use_count"] = int(current.get("use_count", 0)) + 1
        current["last_used_at"] = ts

    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".artifact-usage-",
            suffix=".json",
            dir=str(usage_dir),
        )
    except OSError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            # bash `jq -nc` writes with a trailing newline — match it so the
            # parity harness's side-effect tree hash lines up.
            handle.write(json.dumps(existing, separators=(",", ":")) + "\n")
        os.replace(tmp_path, usage_file)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    cwd_str = payload.get("cwd")
    cwd = Path(cwd_str) if isinstance(cwd_str, str) and cwd_str else Path.cwd()
    if not cwd.is_dir():
        cwd = Path.cwd()

    event_name = payload.get("hook_event_name") or ""
    session_id = payload.get("session_id")

    # Boundary events (#859) are ALWAYS-ON — unlike telemetry.jsonl below,
    # they are not gated by DEV_TEAM_TELEMETRY consent (Ambiguity Log:
    # safety/accountability channel must have no observability holes; no
    # free text is ever recorded, only the matched keyword).
    if event_name == "UserPromptSubmit":
        prompt = payload.get("prompt") or ""
        if isinstance(prompt, str):
            intervention = _INTERVENTION_RE.match(prompt)
            if intervention:
                emit_boundary_event(
                    cwd,
                    "telemetry",
                    "UserPromptSubmit",
                    "intervention",
                    intervention.group(1).lower(),
                    session_id,
                )

    if not _consent_enabled(cwd):
        return 0

    hook_dir = Path(__file__).resolve().parent
    version = _load_plugin_version(hook_dir)
    log = cwd / "metrics" / "telemetry.jsonl"

    if event_name == "UserPromptSubmit":
        prompt = payload.get("prompt") or ""
        if not isinstance(prompt, str):
            return 0
        match = _SLASH_CMD_RE.match(prompt)
        if match:
            _emit(log, "command", match.group(1), "invoked", version)
        return 0

    if event_name == "PreToolUse":
        tool = payload.get("tool_name") or ""
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0
        if tool == "Skill":
            skill = tool_input.get("skill") or tool_input.get("name") or ""
            if isinstance(skill, str) and _SKILL_NAME_RE.match(skill):
                _emit(log, "skill", skill, "invoked", version)
                _upsert_artifact_usage(cwd, skill)
            return 0
        if tool == "Bash":
            cmd = tool_input.get("command") or ""
            if not isinstance(cmd, str):
                return 0
            if "git commit" not in cmd:
                return 0
            if "--no-verify" in cmd or _NO_VERIFY_RE.search(cmd):
                _emit(log, "gate", "pre-commit-review", "bypassed", version)
            else:
                _emit(log, "gate", "pre-commit-review", "fired", version)
            return 0
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
