"""Tests for hooks/task_completion_metrics.py (issue #1044)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = (
    Path(__file__).resolve().parent.parent.parent / "hooks" / "task_completion_metrics.py"
)


def _run(stdin: str, env: dict | None = None, cwd: Path | None = None):
    import os

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(cwd) if cwd else None,
    )
    return result


class TestOptOut:
    def test_off_env_var_exits_zero(self, tmp_path):
        result = _run("{}", env={"DEV_TEAM_TASK_METRICS": "off"}, cwd=tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / "metrics").exists()


class TestNoScratch:
    def test_empty_payload_no_scratch_no_output(self, tmp_path):
        """With no scratch file and no payload, hook skips writing."""
        result = _run("", cwd=tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / "metrics").exists()

    def test_stop_payload_writes_task_log(self, tmp_path):
        """A minimal Stop payload with no scratch file still writes a task entry."""
        payload = json.dumps({"stop_reason": "end_turn"})
        result = _run(payload, cwd=tmp_path)
        assert result.returncode == 0
        metrics = tmp_path / "metrics"
        logs = list(metrics.glob("*-task-log.jsonl"))
        assert len(logs) == 1
        entry = json.loads(logs[0].read_text().strip())
        assert entry["stop_reason"] == "end_turn"
        assert entry["hallucination_detected"] is False
        assert entry["rework_cycles"] == 0


class TestScratchFile:
    def test_scratch_fields_appear_in_task_log(self, tmp_path):
        scratch = {
            "task_id": "t-1",
            "task_type": "implementation",
            "task_description": "Add auth",
            "agents_used": ["software-engineer"],
            "skills_used": ["quality-gate-pipeline"],
            "hallucination_detected": True,
            "rework_cycles": 2,
            "defects_found": 3,
        }
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        (dot_claude / "session-metrics.json").write_text(json.dumps(scratch))

        result = _run(json.dumps({"stop_reason": "end_turn"}), cwd=tmp_path)
        assert result.returncode == 0

        logs = list((tmp_path / "metrics").glob("*-task-log.jsonl"))
        assert len(logs) == 1
        entry = json.loads(logs[0].read_text().strip())
        assert entry["task_id"] == "t-1"
        assert entry["hallucination_detected"] is True
        assert entry["rework_cycles"] == 2
        assert entry["defects_found"] == 3

    def test_scratch_cleared_after_write(self, tmp_path):
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        scratch_path = dot_claude / "session-metrics.json"
        scratch_path.write_text(json.dumps({"task_type": "fix"}))

        _run(json.dumps({}), cwd=tmp_path)
        assert not scratch_path.exists()

    def test_config_change_writes_changelog(self, tmp_path):
        scratch = {
            "config_change": {
                "parameter": "DEV_TEAM_CONTEXT_CEILING_PCT",
                "old_value": "40",
                "new_value": "50",
                "reason": "Test",
            }
        }
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        (dot_claude / "session-metrics.json").write_text(json.dumps(scratch))

        result = _run(json.dumps({}), cwd=tmp_path)
        assert result.returncode == 0

        changelog = tmp_path / "metrics" / "config-changelog.jsonl"
        assert changelog.exists()
        entry = json.loads(changelog.read_text().strip())
        assert entry["parameter"] == "DEV_TEAM_CONTEXT_CEILING_PCT"
        assert entry["new_value"] == "50"

    def test_no_config_change_no_changelog(self, tmp_path):
        scratch = {"task_type": "fix"}
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        (dot_claude / "session-metrics.json").write_text(json.dumps(scratch))

        _run(json.dumps({}), cwd=tmp_path)
        assert not (tmp_path / "metrics" / "config-changelog.jsonl").exists()


class TestFailOpen:
    def test_invalid_json_payload_exits_zero(self, tmp_path):
        result = _run("not-json", cwd=tmp_path)
        assert result.returncode == 0

    def test_metrics_dir_creation_failure_exits_zero(self, tmp_path):
        """Simulate metrics dir being a file (cannot mkdir) — hook must exit 0."""
        (tmp_path / "metrics").write_text("file")
        result = _run(json.dumps({"stop_reason": "end_turn"}), cwd=tmp_path)
        assert result.returncode == 0
