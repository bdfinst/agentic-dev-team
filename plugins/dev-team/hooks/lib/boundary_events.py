"""boundary_events.py — shared boundary-level telemetry emit helper (#859).

Records the decision process of the plugin's guard hooks (policy-gateway
events, per *Code as Agent Harness* §3.5.1): which hook, on which tool,
decided what, because of which rule. Complements `telemetry.py`
(command/skill/gate invocation counts) and `cost_meter.py` (per-agent
token/cost) as the third, boundary-level channel.

ALWAYS-ON: unlike `telemetry.py`, this stream is not gated by
`DEV_TEAM_TELEMETRY` consent — it is a local-only, rule-IDs-only safety /
accountability record (Ambiguity Log, issue #859). Never write free text:
command text, prompt text, file paths, or reasons must never appear in a
`matched_rule` value — only rule IDs from closed vocabularies.

Fail-open: every exception is swallowed. A full disk, read-only
`metrics/`, or malformed state must never change the calling hook's
stdout, stderr, or exit code.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOG_NAME = "boundary-events.jsonl"


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_plugin_version() -> str:
    # hooks/lib/boundary_events.py -> hooks/lib -> hooks -> plugin root
    manifest = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def emit_boundary_event(
    cwd,
    hook: str,
    tool: str,
    decision: str,
    matched_rule: str,
    session_id: Optional[str] = None,
) -> None:
    """Append one compact JSON line to `<cwd>/metrics/boundary-events.jsonl`.

    Fail-open: any error (bad `cwd`, unwritable `metrics/`, disk full,
    etc.) is swallowed silently — this must never affect the caller's
    exit code, stdout, or stderr.

    Args:
        cwd: Directory whose `metrics/` subdirectory receives the event.
            Accepts `str` or `Path`.
        hook: Emitting hook's module name (e.g. "destructive_guard").
        tool: Hooked tool / event name (e.g. "Bash", "UserPromptSubmit").
        decision: One of "block", "warn", "bypass", "intervention".
        matched_rule: A rule ID from a closed vocabulary — never free
            text (no command text, prompt text, file paths, or reasons).
        session_id: Optional opaque session ID from the hook payload,
            enabling per-session joins with session-digest.jsonl.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = base / "metrics" / _LOG_NAME
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "hook": hook,
            "tool": tool,
            "decision": decision,
            "matched_rule": matched_rule,
            "plugin_version": _load_plugin_version(),
        }
        if session_id:
            payload["session_id"] = session_id

        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 — fail-open by design, see module docstring
        pass
