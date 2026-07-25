"""Unit tests for hooks/telemetry.py (#606, #1405)."""

from __future__ import annotations

import io
import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import telemetry


def _isolate_home(monkeypatch, tmp_path):
    """Point ~/.claude/telemetry.json at a fresh, empty home dir, and TMPDIR
    at a fresh scratch dir, so tests never read the real machine's consent
    file nor leave a stray Step-1.4 notice marker in the real temp dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    return home


def _enable_consent(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    (home / ".claude").mkdir()
    (home / ".claude" / "telemetry.json").write_text('{"enabled":true}')
    return home


# ---------------------------------------------------------------------------
# Consent gate — config-file-only, home-scoped (Slice 1, Step 1.2)
# ---------------------------------------------------------------------------


def test_env_var_has_no_effect(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
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
    assert not (home / ".claude" / "metrics" / "telemetry.jsonl").exists()


def test_project_level_config_has_no_effect(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":true}')
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
    assert not (home / ".claude" / "metrics" / "telemetry.jsonl").exists()


def test_home_config_governs(monkeypatch, tmp_path):
    home = _enable_consent(monkeypatch, tmp_path)
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
    assert (home / ".claude" / "metrics" / "telemetry.jsonl").exists()
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


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


def test_upsert_creates_entry(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    telemetry._upsert_artifact_usage("plan")
    data = json.loads((home / ".claude" / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 1
    assert data["plan"]["lifecycle"] == "active"


def test_upsert_bumps_existing_count(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    telemetry._upsert_artifact_usage("plan")
    telemetry._upsert_artifact_usage("plan")
    telemetry._upsert_artifact_usage("plan")
    data = json.loads((home / ".claude" / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 3


def test_upsert_recovers_from_malformed_file(monkeypatch, tmp_path, capsys):
    home = _isolate_home(monkeypatch, tmp_path)
    (home / ".claude" / "metrics").mkdir(parents=True)
    (home / ".claude" / "metrics" / "artifact-usage.json").write_text("{not json")
    telemetry._upsert_artifact_usage("plan")
    warn = capsys.readouterr().err
    assert "malformed JSON" in warn
    data = json.loads((home / ".claude" / "metrics" / "artifact-usage.json").read_text())
    assert data["plan"]["use_count"] == 1


def test_upsert_trailing_newline_matches_bash(monkeypatch, tmp_path):
    home = _isolate_home(monkeypatch, tmp_path)
    telemetry._upsert_artifact_usage("plan")
    assert (
        (home / ".claude" / "metrics" / "artifact-usage.json").read_text().endswith("\n")
    )


def test_upsert_never_writes_under_a_project_directory(monkeypatch, tmp_path):
    """Slice 1 Gherkin: 'artifact usage always lands under the home metrics
    dir' — a project cwd must never receive metrics/artifact-usage.json."""
    _isolate_home(monkeypatch, tmp_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    telemetry._upsert_artifact_usage("plan")
    assert not (project_dir / "metrics" / "artifact-usage.json").exists()


# ---------------------------------------------------------------------------
# main() decision paths
# ---------------------------------------------------------------------------


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_consent_off_writes_nothing(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
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
    home = _enable_consent(monkeypatch, tmp_path)
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
    log = home / ".claude" / "metrics" / "telemetry.jsonl"
    line = json.loads(log.read_text().strip())
    assert line["event"] == "command"
    assert line["name"] == "plan"
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


def test_main_non_slash_prompt_records_nothing(monkeypatch, tmp_path):
    home = _enable_consent(monkeypatch, tmp_path)
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
    assert not (home / ".claude" / "metrics" / "telemetry.jsonl").exists()


def test_main_git_commit_fires_gate(monkeypatch, tmp_path):
    home = _enable_consent(monkeypatch, tmp_path)
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
    log = home / ".claude" / "metrics" / "telemetry.jsonl"
    payload = json.loads(log.read_text().strip())
    assert payload["outcome"] == "fired"


@pytest.mark.parametrize(
    "cmd",
    ["git commit --no-verify", "git commit -m msg -n", "git commit -n -m msg"],
)
def test_main_git_commit_bypass_variants(monkeypatch, tmp_path, cmd):
    home = _enable_consent(monkeypatch, tmp_path)
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
    log = home / ".claude" / "metrics" / "telemetry.jsonl"
    payload = json.loads(log.read_text().strip())
    assert payload["outcome"] == "bypassed"


def test_main_skill_records_and_upserts(monkeypatch, tmp_path):
    home = _enable_consent(monkeypatch, tmp_path)
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
    metrics_dir = home / ".claude" / "metrics"
    ev = json.loads((metrics_dir / "telemetry.jsonl").read_text().strip())
    assert ev["event"] == "skill"
    assert ev["name"] == "plan"
    usage = json.loads((metrics_dir / "artifact-usage.json").read_text())
    assert usage["plan"]["use_count"] == 1
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()
    assert not (tmp_path / "metrics" / "artifact-usage.json").exists()


def test_main_malformed_stdin_silent(monkeypatch, tmp_path):
    home = _enable_consent(monkeypatch, tmp_path)
    _feed(monkeypatch, "not-json")
    assert telemetry.main() == 0
    assert not (home / ".claude" / "metrics" / "telemetry.jsonl").exists()


# ---------------------------------------------------------------------------
# One-time inert-legacy-signal notice (Slice 1, Step 1.4)
# ---------------------------------------------------------------------------


def _prompt_payload(cwd, session_id=None):
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(cwd),
        "prompt": "/plan",
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return json.dumps(payload)


def test_no_notice_when_neither_legacy_signal_present(monkeypatch, tmp_path, capsys):
    _isolate_home(monkeypatch, tmp_path)
    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-none"))
    assert telemetry.main() == 0
    assert capsys.readouterr().err == ""


def test_notice_fires_for_env_var_signal(monkeypatch, tmp_path, capsys):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")
    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-env"))
    assert telemetry.main() == 0
    err = capsys.readouterr().err
    assert "~/.claude/telemetry.json" in err


def test_notice_fires_for_project_level_config_signal(monkeypatch, tmp_path, capsys):
    _isolate_home(monkeypatch, tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":true}')
    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-proj"))
    assert telemetry.main() == 0
    err = capsys.readouterr().err
    assert "~/.claude/telemetry.json" in err


def test_notice_fires_once_per_session_not_per_invocation(monkeypatch, tmp_path, capsys):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")

    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-repeat"))
    assert telemetry.main() == 0
    first_err = capsys.readouterr().err
    assert "~/.claude/telemetry.json" in first_err

    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-repeat"))
    assert telemetry.main() == 0
    second_err = capsys.readouterr().err
    assert second_err == ""


def test_notice_is_per_session_not_global(monkeypatch, tmp_path, capsys):
    """A different session_id gets its own one-time notice."""
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("DEV_TEAM_TELEMETRY", "on")

    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-a"))
    telemetry.main()
    capsys.readouterr()  # discard first session's notice

    _feed(monkeypatch, _prompt_payload(tmp_path, "sess-b"))
    assert telemetry.main() == 0
    err = capsys.readouterr().err
    assert "~/.claude/telemetry.json" in err
