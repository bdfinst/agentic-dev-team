"""Content-guard: telemetry/SKILL.md documents home-scoped consent only
(#1405, Slice 1 Step 1.5).

Asserts the skill's on/off/status/report instructions read and write
~/.claude/telemetry.json exclusively, reference ~/.claude/metrics/telemetry.jsonl
(never the bare project-scoped metrics/telemetry.jsonl), and contain no
DEV_TEAM_TELEMETRY instruction text — the env var and any project-level
.claude/telemetry.json no longer have any effect (Slice 1).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

TELEMETRY_SKILL = PLUGIN_ROOT / "skills" / "telemetry" / "SKILL.md"


def _text() -> str:
    return TELEMETRY_SKILL.read_text()


def test_no_dev_team_telemetry_env_var_mentions():
    assert "DEV_TEAM_TELEMETRY" not in _text()


def test_no_bare_project_scoped_telemetry_jsonl_reference():
    text = _text()
    # Every telemetry.jsonl reference must be prefixed by the home-scoped
    # metrics dir — a bare "metrics/telemetry.jsonl" (no ~/.claude/ prefix)
    # would mean a stale project-scoped path slipped back in.
    assert "metrics/telemetry.jsonl" not in text.replace(
        "~/.claude/metrics/telemetry.jsonl", ""
    ).replace('"$HOME/.claude/metrics/telemetry.jsonl"', "")


def test_home_scoped_telemetry_jsonl_path_present():
    assert "~/.claude/metrics/telemetry.jsonl" in _text()


def test_home_scoped_consent_file_path_present():
    assert "~/.claude/telemetry.json" in _text()


def test_no_project_scoped_bare_dot_claude_telemetry_json_reference():
    text = _text()
    # Every ".claude/telemetry.json" reference must be home-scoped
    # (~/.claude/telemetry.json), never the bare project-relative form.
    assert ".claude/telemetry.json" not in text.replace("~/.claude/telemetry.json", "")
