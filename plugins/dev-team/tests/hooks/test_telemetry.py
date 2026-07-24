"""Unit tests for hooks/telemetry.py (#606)."""

from __future__ import annotations

import io
import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import telemetry

# ---------------------------------------------------------------------------
# Consent gate
# ---------------------------------------------------------------------------


def test_consent_env_var_on_enables(tmp_path, monkeypatch):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    assert telemetry._consent_enabled(tmp_path) is True


def test_consent_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    assert telemetry._consent_enabled(tmp_path) is False


def test_consent_file_enabled_true(tmp_path, monkeypatch):
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":true}')
    assert telemetry._consent_enabled(tmp_path) is True


def test_consent_file_enabled_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":false}')
    assert telemetry._consent_enabled(tmp_path) is False


def test_consent_file_malformed(tmp_path, monkeypatch):
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text("{not json")
    assert telemetry._consent_enabled(tmp_path) is False


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


def test_emit_appends_jsonl_with_trailing_newline(tmp_path):
    log = tmp_path / "metrics" / "telemetry.jsonl"
    telemetry._emit(log, "command", "plan", "invoked", "1.0.0")
    telemetry._emit(log, "gate", "pre-commit-review", "fired", "1.0.0")
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "command"
    assert first["name"] == "plan"
    assert first["outcome"] == "invoked"
    assert first["plugin_version"] == "1.0.0"
    assert "ts" in first
    assert log.read_text().endswith("\n")


# ---------------------------------------------------------------------------
# Artifact usage upsert
# ---------------------------------------------------------------------------


def test_upsert_creates_entry(tmp_path):
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    data = json.loads((tmp_path / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 1
    assert data["plan"]["lifecycle"] == "active"


def test_upsert_bumps_existing_count(tmp_path):
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    data = json.loads((tmp_path / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 3


def test_upsert_disabled_when_file_says_false(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":false}')
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    assert not (tmp_path / "metrics" / "artifact-usage.json").exists()


def test_upsert_recovers_from_malformed_file(tmp_path, capsys):
    (tmp_path / "metrics").mkdir()
    (tmp_path / "metrics" / "artifact-usage.json").write_text("{not json")
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    warn = capsys.readouterr().err
    assert "malformed JSON" in warn
    data = json.loads((tmp_path / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 1


def test_upsert_trailing_newline_matches_bash(tmp_path):
    telemetry._upsert_artifact_usage(tmp_path, "plan")
    assert (tmp_path / "metrics" / "artifact-usage.json").read_text().endswith("\n")


# ---------------------------------------------------------------------------
# main() decision paths
# ---------------------------------------------------------------------------


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_consent_off_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(tmp_path),
                "prompt": "/plan",
            }
        ),
    )
    assert telemetry.main() == 0
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


def test_main_user_prompt_records_command(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(tmp_path),
                "prompt": "/plan something",
            }
        ),
    )
    assert telemetry.main() == 0
    line = json.loads((tmp_path / "metrics" / "telemetry.jsonl").read_text().strip())
    assert line["event"] == "command"
    assert line["name"] == "plan"


def test_main_non_slash_prompt_records_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(tmp_path),
                "prompt": "just a question",
            }
        ),
    )
    assert telemetry.main() == 0
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


def test_main_git_commit_fires_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "cwd": str(tmp_path),
                "tool_input": {"command": "git commit -m msg"},
            }
        ),
    )
    assert telemetry.main() == 0
    payload = json.loads((tmp_path / "metrics" / "telemetry.jsonl").read_text().strip())
    assert payload["outcome"] == "fired"


@pytest.mark.parametrize(
    "cmd",
    ["git commit --no-verify", "git commit -m msg -n", "git commit -n -m msg"],
)
def test_main_git_commit_bypass_variants(monkeypatch, tmp_path, cmd):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "cwd": str(tmp_path),
                "tool_input": {"command": cmd},
            }
        ),
    )
    assert telemetry.main() == 0
    payload = json.loads((tmp_path / "metrics" / "telemetry.jsonl").read_text().strip())
    assert payload["outcome"] == "bypassed"


def test_main_skill_records_and_upserts(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "cwd": str(tmp_path),
                "tool_input": {"skill": "plan"},
            }
        ),
    )
    assert telemetry.main() == 0
    ev = json.loads((tmp_path / "metrics" / "telemetry.jsonl").read_text().strip())
    assert ev["event"] == "skill"
    assert ev["name"] == "plan"
    usage = json.loads((tmp_path / "metrics" / "artifact-usage.json").read_text())
    assert usage["plan"]["use_count"] == 1


def test_main_malformed_stdin_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(monkeypatch, "not-json")
    assert telemetry.main() == 0
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()
