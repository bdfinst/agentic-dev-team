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

CONSENT: OFF by default. Enable by writing `{"enabled": true}` to the
user-level `~/.claude/telemetry.json` (see `hooks/lib/telemetry_consent.py`).
This is a config-file-only, home-scoped switch — `DEV_TEAM_TELEMETRY` and any
project-scoped `<cwd>/.claude/telemetry.json` have no effect. When off,
nothing is recorded and nothing leaves the machine. Detecting either now-inert
legacy signal prints a one-time-per-session stderr notice pointing at the new
home-scoped path.

TRANSPORT: local-only. Events append to `~/.claude/metrics/telemetry.jsonl`;
`artifact-usage.json` lives alongside it under the same home-scoped
`~/.claude/metrics/` directory, never under a project's own `metrics/`.
No network egress.

Posture: record-only, fail-open. Never blocks; any error → exit 0.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event
import telemetry_consent


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
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


def _legacy_signal_path(session_id: object) -> Path:
    """Per-session dedupe marker for the one-time inert-legacy-signal notice
    (#1405, Slice 1 Step 1.4). Mirrors context_ceiling_guard.py's marker
    pattern: TMPDIR (or the system temp dir) keyed by a sanitized session id.
    """
    tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or "")) or "nosession"
    return Path(tmpdir) / f"dev-team-telemetry-legacy-notice-{session}"


def _legacy_signal_present(cwd: Path) -> bool:
    """True when either now-inert consent mechanism is in use: the
    `DEV_TEAM_TELEMETRY` env var, or a project-scoped
    `<cwd>/.claude/telemetry.json`. Neither has any effect on consent."""
    if os.environ.get("DEV_TEAM_TELEMETRY"):
        return True
    return (cwd / ".claude" / "telemetry.json").is_file()


def _notice_legacy_signal_once(session_id: object) -> None:
    """Emit a one-time-per-session stderr notice that consent moved to
    `~/.claude/telemetry.json`. Fail-open: any error creating the dedupe
    marker must never raise or block the calling hook.

    Uses atomic exclusive creation (`O_CREAT | O_EXCL | O_NOFOLLOW`)
    instead of a separate `is_file()` check + `write_text()` — that
    pattern has a TOCTOU window and follows symlinks, so a pre-created
    dangling symlink at the predictable marker path could redirect the
    write. `EEXIST` doubles as "already notified this session", so the
    dedupe check and the atomic create are one operation.
    """
    marker = _legacy_signal_path(session_id)
    try:
        fd = os.open(
            str(marker),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
    except OSError:
        # EEXIST (already notified this session), a symlink at the marker
        # path, or any other failure (permission denied) — fail-open.
        return

    sys.stderr.write(
        "NOTE: dev-team telemetry consent now lives only in "
        "~/.claude/telemetry.json. DEV_TEAM_TELEMETRY and a project-level "
        ".claude/telemetry.json no longer have any effect.\n"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("1")
    except OSError:
        pass


def _home_metrics_dir() -> Path:
    """`telemetry.jsonl` and `artifact-usage.json` always live here — never
    under a project's own `metrics/` (#1405, Slice 1 Step 1.3)."""
    return Path.home() / ".claude" / "metrics"


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


def _emit(log: Path, event: str, name: str, outcome: str, version: str) -> None:
    """Append one JSONL event to `log`. Fail-open on any error — but per
    AC5, a failure to create or write to `log` still produces a diagnostic
    stderr line; it just never blocks the calling operation."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"WARN: could not create {log.parent}: {exc}\n")
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
    except OSError as exc:
        sys.stderr.write(f"WARN: could not write {log}: {exc}\n")


def _upsert_artifact_usage(skill: str) -> None:
    """Atomically bump the use count for `skill` in artifact-usage.json.

    Always writes under the home-scoped `~/.claude/metrics/`, never a
    project's own `metrics/` (#1405, Slice 1 Step 1.3). Callers gate this
    on `telemetry_consent.is_enabled()` before invoking it (see `main()`)
    — there is no separate per-writer consent check.
    """
    usage_dir = _home_metrics_dir()
    usage_file = usage_dir / "artifact-usage.json"
    try:
        usage_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"WARN: could not create {usage_dir}: {exc}\n")
        return

    existing: dict = {}
    if usage_file.is_file():
        try:
            existing = json.loads(usage_file.read_text())
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            sys.stderr.write(
                "WARN: ~/.claude/metrics/artifact-usage.json contained malformed JSON; discarding\n"
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
    except OSError as exc:
        sys.stderr.write(f"WARN: could not create temp file in {usage_dir}: {exc}\n")
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            # bash `jq -nc` writes with a trailing newline — match it so the
            # parity harness's side-effect tree hash lines up.
            handle.write(json.dumps(existing, separators=(",", ":")) + "\n")
        os.replace(tmp_path, usage_file)
    except OSError as exc:
        sys.stderr.write(f"WARN: could not write {usage_file}: {exc}\n")
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

    # One-time-per-session notice (#1405, Slice 1 Step 1.4): unconditional,
    # independent of telemetry_consent.is_enabled() — a user relying on the
    # now-inert DEV_TEAM_TELEMETRY/project-config signal should hear about
    # the move even while consent is off.
    if _legacy_signal_present(cwd):
        _notice_legacy_signal_once(session_id)

    # Boundary events (#859) are ALWAYS-ON — unlike telemetry.jsonl below,
    # they are not gated by telemetry consent (Ambiguity Log:
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

    if not telemetry_consent.is_enabled():
        return 0

    hook_dir = Path(__file__).resolve().parent
    version = _load_plugin_version(hook_dir)
    log = _home_metrics_dir() / "telemetry.jsonl"

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
                _upsert_artifact_usage(skill)
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
