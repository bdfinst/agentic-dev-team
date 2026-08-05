#!/usr/bin/env python3
"""task_completion_metrics.py — Stop/SubagentStop hook for JSONL audit logging.

Fires on task/session completion signals (Stop + SubagentStop) and writes
standard metrics fields to their respective JSONL files, mechanically,
regardless of which skill or agent was active.

Skills no longer need "remember to log X" prose in their Output sections.
They only need to have populated the shared scratch file
`.claude/session-metrics.json` with any task-local values they want recorded.
The hook consumes that file and clears it after writing.

## Scratch file format (.claude/session-metrics.json)

```json
{
  "task_id": "optional-human-slug",
  "task_type": "implementation",
  "task_description": "Short description of the task",
  "agents_used": ["software-engineer"],
  "skills_used": ["quality-gate-pipeline"],
  "hallucination_detected": false,
  "rework_cycles": 0,
  "defects_found": 0,
  "config_change": {
    "parameter": "DEV_TEAM_CONTEXT_CEILING_PCT",
    "old_value": "40",
    "new_value": "50",
    "reason": "Increased for larger context models"
  }
}
```

All fields are optional. If the scratch file is absent or empty, the hook
writes **nothing** and exits — a Stop/SubagentStop with no task-local payload
carries no signal worth recording, and a bare heartbeat only produces
`task_type:"unknown"` noise that dilutes `/harness-audit` Step 3 (see #1258;
a single 2026-07-20 audit run emitted 172 empty heartbeats vs 10 real rows).

## Output files

- `.claude/metrics/{date}-task-log.jsonl`  — task completion entry
- `.claude/metrics/config-changelog.jsonl` — config change entry (if `config_change` present)

## Contract (docs/python-hook-contract.md)

    Input : Stop / SubagentStop JSON on stdin
    Output: appends to metrics JSONL files; no stdout. Exit 0.
    Posture: record-only and fail-open. Any error -> exit 0 silently.
    Opt-out: DEV_TEAM_TASK_METRICS=off disables entirely.

Stdlib-only (datetime/json/os/pathlib/sys/uuid).
See ADR 0014, ADR 0015.

Refs: #1044 (this hook), #1042 (parent epic).
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import uuid
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_PLUGIN_DIR = _HOOK_DIR.parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import telemetry_consent
from atomic_state import append_line_locked

# Scratch file location: resolved relative to the project root (cwd when hook
# fires) so it is session-local, not baked into the plugin install tree.
_SCRATCH_RELATIVE = Path(".claude") / "session-metrics.json"


def _env_off(var: str) -> bool:
    return os.environ.get(var, "").strip().lower() == "off"


def _read_stdin() -> dict:
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}


def _load_scratch(cwd: Path) -> dict:
    scratch = cwd / _SCRATCH_RELATIVE
    try:
        if not scratch.exists():
            return {}
        text = scratch.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}


def _clear_scratch(cwd: Path) -> None:
    scratch = cwd / _SCRATCH_RELATIVE
    try:
        if scratch.exists():
            scratch.unlink()
    except OSError:  # best-effort cleanup; a stale scratch file is harmless
        pass


def _ensure_metrics_dir(cwd: Path) -> Path:
    metrics = artifact_paths.metrics_dir(cwd)
    metrics.mkdir(parents=True, exist_ok=True)
    return metrics


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d")


def _append_jsonl(path: Path, entry: dict) -> None:
    """Append one JSON line to a JSONL file, creating it if needed.

    Serialized against concurrent writers via `atomic_state.append_line_locked`
    (#1896) — fail-open, matching this hook's outer `main()` try/except.
    """
    line = json.dumps(entry, separators=(",", ":"), sort_keys=False)
    append_line_locked(path, line + "\n")


def _write_task_completion(cwd: Path, scratch: dict, payload: dict) -> None:
    """Write a task completion entry to .claude/metrics/{date}-task-log.jsonl."""
    ts = _now_iso()
    entry: dict = {
        "timestamp": ts,
        "task_id": scratch.get("task_id") or str(uuid.uuid4()),
        "task_type": scratch.get("task_type", "unknown"),
        "task_description": scratch.get("task_description", ""),
        "agents_used": scratch.get("agents_used") or [],
        "skills_used": scratch.get("skills_used") or [],
        "hallucination_detected": bool(scratch.get("hallucination_detected", False)),
        "rework_cycles": int(scratch.get("rework_cycles", 0)),
        "defects_found": int(scratch.get("defects_found", 0)),
    }

    # Include stop-reason from harness if available (informational).
    stop_reason = payload.get("stop_reason") or payload.get("stopReason")
    if stop_reason:
        entry["stop_reason"] = stop_reason

    log_path = artifact_paths.resolve_file(
        "metrics", f"{_today()}-task-log.jsonl", cwd
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl(log_path, entry)


def _write_config_changelog(cwd: Path, scratch: dict) -> None:
    """Write a config-changelog entry if scratch contains config_change."""
    change = scratch.get("config_change")
    if not change or not isinstance(change, dict):
        return

    ts = _now_iso()
    entry: dict = {
        "timestamp": ts,
        "parameter": change.get("parameter", ""),
        "old_value": change.get("old_value", ""),
        "new_value": change.get("new_value", ""),
        "reason": change.get("reason", ""),
    }
    log_path = artifact_paths.resolve_file("metrics", "config-changelog.jsonl", cwd)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl(log_path, entry)


def main() -> int:
    if _env_off("DEV_TEAM_TASK_METRICS"):
        return 0
    if not telemetry_consent.is_enabled():
        return 0

    payload = _read_stdin()

    # Resolve project root from the hook payload's cwd, falling back to
    # process cwd (which the harness sets to the project root).
    raw_cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ""
    cwd = Path(raw_cwd).resolve() if raw_cwd else Path.cwd()

    scratch = _load_scratch(cwd)

    # Suppress empty heartbeats (#1258). A Stop/SubagentStop with no scratch
    # payload has nothing task-local to record — writing an entry would only
    # emit a hollow task_type:"unknown" row that dilutes downstream analysis
    # (harness-audit Step 3). The stop payload alone (stop_reason, cost) is not
    # enough to justify a row; a skill that wants a row populates the scratch.
    if not scratch:
        return 0

    try:
        _ensure_metrics_dir(cwd)
        _write_task_completion(cwd, scratch, payload)
        _write_config_changelog(cwd, scratch)
        _clear_scratch(cwd)
    except Exception:  # noqa: BLE001, S110
        # Fail-open: never block the session on a metrics write failure.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
