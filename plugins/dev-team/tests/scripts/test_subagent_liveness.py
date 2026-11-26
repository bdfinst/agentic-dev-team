"""Unit tests for scripts/subagent_liveness.py — hung-subagent detection."""

from __future__ import annotations

import json
import os
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import subagent_liveness

NOW = 1_000_000.0


def _agent(tmp_path, agent_id, age_s):
    path = tmp_path / "subagents" / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("{}\n")
    os.utime(path, (NOW - age_s, NOW - age_s))
    return path


def _stops(tmp_path, *agent_ids):
    log = tmp_path / "subagent-stops.jsonl"
    log.write_text("".join(json.dumps({"agent_id": a}) + "\n" for a in agent_ids))
    return log


def _hung(tmp_path, threshold=600, stops=None):
    return [
        h["agent_id"]
        for h in subagent_liveness.find_hung(
            tmp_path / "subagents", stops, threshold, now=NOW
        )
    ]


def test_stale_unfinished_agent_is_reported(tmp_path):
    _agent(tmp_path, "stale", 601)
    assert _hung(tmp_path, stops=_stops(tmp_path)) == ["stale"]


def test_finished_agent_is_not_reported_however_old(tmp_path):
    _agent(tmp_path, "done", 99999)
    assert _hung(tmp_path, stops=_stops(tmp_path, "done")) == []


def test_fresh_agent_is_not_reported(tmp_path):
    _agent(tmp_path, "fresh", 30)
    assert _hung(tmp_path, stops=_stops(tmp_path)) == []


def test_agent_exactly_at_the_threshold_is_not_reported(tmp_path):
    _agent(tmp_path, "edge", 600)
    assert _hung(tmp_path, stops=_stops(tmp_path)) == []


def test_threshold_is_configurable(tmp_path):
    _agent(tmp_path, "a", 120)
    assert _hung(tmp_path, threshold=60, stops=_stops(tmp_path)) == ["a"]
    assert _hung(tmp_path, threshold=300, stops=_stops(tmp_path)) == []


def test_missing_stops_log_treats_every_agent_as_unfinished(tmp_path):
    _agent(tmp_path, "stale", 700)
    assert _hung(tmp_path, stops=tmp_path / "absent.jsonl") == ["stale"]


def test_malformed_stop_rows_are_skipped(tmp_path):
    _agent(tmp_path, "done", 700)
    log = tmp_path / "subagent-stops.jsonl"
    log.write_text('not json\n{"agent_id": "done"}\n[]\n')
    assert _hung(tmp_path, stops=log) == []


def test_missing_subagent_dir_reports_nothing(tmp_path):
    assert subagent_liveness.find_hung(tmp_path / "none", None, 600, now=NOW) == []


def test_main_exits_1_when_a_hung_agent_exists(tmp_path, capsys):
    stale = _agent(tmp_path, "stale", 5000)
    os.utime(stale, (0, 0))
    code = subagent_liveness.main(
        ["--dir", str(tmp_path / "subagents"), "--stops", str(_stops(tmp_path))]
    )
    assert code == 1
    assert json.loads(capsys.readouterr().out)["hung"][0]["agent_id"] == "stale"


def test_main_exits_0_when_nothing_is_hung(tmp_path, capsys):
    _agent(tmp_path, "fresh", 0)
    os.utime(tmp_path / "subagents" / "agent-fresh.jsonl")
    code = subagent_liveness.main(["--dir", str(tmp_path / "subagents")])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["hung"] == []


def test_default_threshold_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DEV_TEAM_SUBAGENT_STUCK_SECONDS", "42")
    assert subagent_liveness.default_threshold() == 42
    monkeypatch.setenv("DEV_TEAM_SUBAGENT_STUCK_SECONDS", "junk")
    assert subagent_liveness.default_threshold() == 600


def test_open_tool_call_gets_extra_grace(tmp_path):
    import json as _json
    import os as _os

    path = tmp_path / "agent-a1.jsonl"
    path.write_text(_json.dumps({"message": {"content": [{"type": "tool_use", "id": "t"}]}}) + "\n")
    _os.utime(path, (1000, 1000))
    assert subagent_liveness.find_hung(tmp_path, None, 600, now=1000 + 1200) == []
    assert subagent_liveness.find_hung(tmp_path, None, 600, now=1000 + 4000)
