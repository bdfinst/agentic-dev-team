"""Unit tests for the context-pollution phase-marker pipeline (#1520).

Covers both halves:
  * hooks/lib/cost_meter.py — the `phase-mark` (emit) and `phase-report`
    (per-phase resident/spent) subcommands plus their `_resident_and_spent`
    and `_phase_rows` helpers.
  * hooks/phase_marker.py — the PostToolUse:Skill hook that fires the emit on
    `/handoff`, exercised as a module with a crafted stdin payload (the
    working-tree code path — the installed cache copy is a separate snapshot).
"""

from __future__ import annotations

import importlib.util
import io
import json
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_HOOKS_LIB = _HOOKS / "lib"


def _load(module_name: str, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Distinct sys.modules key — a sibling hooks/cost_meter.py of the same basename
# exists, so pin the lib version by path (see test_cost_meter_lib.py #1120).
cost_meter = _load("cost_meter_lib_phase", _HOOKS_LIB / "cost_meter.py")
phase_marker = _load("phase_marker_hook", _HOOKS / "phase_marker.py")

_PRICING = {"cache_write_multiplier": 1.25, "cache_read_multiplier": 0.1, "models": {}, "aliases": {}}


def _usage(inp, out, cache_read=0, cache_create=0, *, sidechain=False):
    rec = {
        "message": {
            "model": "claude-x",
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create,
            },
        }
    }
    if sidechain:
        rec["isSidechain"] = True
    return json.dumps(rec) + "\n"


# ---------------------------------------------------------------------------
# _resident_and_spent
# ---------------------------------------------------------------------------


def test_resident_is_last_mainloop_occupancy_spent_is_cumulative_output(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(
        _usage(100, 40, cache_read=10, cache_create=5)
        + _usage(200, 60, cache_read=20, cache_create=5)
    )
    resident, spent = cost_meter._resident_and_spent(t)
    # resident = last main-loop turn's input+cache_read+cache_creation.
    assert resident == 200 + 20 + 5
    # spent = cumulative output across both turns.
    assert spent == 40 + 60


def test_resident_and_spent_ignores_sidechain_turns(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(
        _usage(100, 40)
        + _usage(9999, 9999, cache_read=9999, sidechain=True)  # subagent — excluded
    )
    resident, spent = cost_meter._resident_and_spent(t)
    assert resident == 100  # the sidechain turn did not overwrite it
    assert spent == 40  # nor add to the main-loop spend


def test_resident_and_spent_missing_file_is_zero(tmp_path):
    assert cost_meter._resident_and_spent(tmp_path / "nope.jsonl") == (0, 0)


# ---------------------------------------------------------------------------
# cmd_phase_mark
# ---------------------------------------------------------------------------


def test_cmd_phase_mark_appends_marker(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(300, 50, cache_read=100))
    log = tmp_path / "metrics" / "phase-markers.jsonl"
    cost_meter.cmd_phase_mark(
        SimpleNamespace(transcript=str(t), phase="plan", log=str(log)), _PRICING
    )
    entry = json.loads(log.read_text().splitlines()[-1])
    assert entry["phase"] == "plan"
    assert entry["resident_tokens"] == 400
    assert entry["spent_output_cumulative"] == 50


def test_cmd_phase_mark_missing_transcript_is_noop(tmp_path):
    log = tmp_path / "metrics" / "phase-markers.jsonl"
    rc = cost_meter.cmd_phase_mark(
        SimpleNamespace(transcript=str(tmp_path / "nope.jsonl"), phase=None, log=str(log)),
        _PRICING,
    )
    assert rc == 0
    assert not log.exists()


def test_cmd_phase_mark_defaults_unlabeled(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(10, 5))
    log = tmp_path / "m.jsonl"
    cost_meter.cmd_phase_mark(SimpleNamespace(transcript=str(t), phase=None, log=str(log)), _PRICING)
    assert json.loads(log.read_text().splitlines()[-1])["phase"] == "unlabeled"


# ---------------------------------------------------------------------------
# _phase_rows
# ---------------------------------------------------------------------------


def test_phase_rows_computes_deltas_and_ratio():
    entries = [
        {"phase": "research", "resident_tokens": 5000, "spent_output_cumulative": 1000},
        {"phase": "plan", "resident_tokens": 8000, "spent_output_cumulative": 1400},
    ]
    rows = cost_meter._phase_rows(entries)
    assert rows[0] == {
        "phase": "research",
        "resident_tokens": 5000,
        "spent_tokens": 1000,
        "resident_to_spent_ratio": 5.0,
    }
    # plan's own spend is the delta 1400-1000=400; 8000/400 = 20.0.
    assert rows[1]["spent_tokens"] == 400
    assert rows[1]["resident_to_spent_ratio"] == 20.0


def test_phase_rows_zero_spend_ratio_is_none_not_div_by_zero():
    rows = cost_meter._phase_rows(
        [{"phase": "p", "resident_tokens": 100, "spent_output_cumulative": 0}]
    )
    assert rows[0]["resident_to_spent_ratio"] is None


def test_phase_rows_clamps_counter_reset_to_zero():
    # A transcript rotation resets the cumulative counter; the delta must clamp
    # at 0 rather than go negative.
    rows = cost_meter._phase_rows(
        [
            {"phase": "a", "resident_tokens": 10, "spent_output_cumulative": 900},
            {"phase": "b", "resident_tokens": 10, "spent_output_cumulative": 100},
        ]
    )
    assert rows[1]["spent_tokens"] == 0
    assert rows[1]["resident_to_spent_ratio"] is None


# ---------------------------------------------------------------------------
# cmd_phase_report
# ---------------------------------------------------------------------------


def test_cmd_phase_report_json(tmp_path, capsys):
    log = tmp_path / "m.jsonl"
    log.write_text(
        json.dumps({"phase": "implement", "resident_tokens": 6000, "spent_output_cumulative": 2000}) + "\n"
    )
    cost_meter.cmd_phase_report(SimpleNamespace(log=str(log), json=True), _PRICING)
    out = json.loads(capsys.readouterr().out)
    assert out["by_phase"][0]["phase"] == "implement"
    assert out["by_phase"][0]["resident_to_spent_ratio"] == 3.0


def test_cmd_phase_report_no_file(tmp_path, capsys):
    rc = cost_meter.cmd_phase_report(
        SimpleNamespace(log=str(tmp_path / "nope.jsonl"), json=False), _PRICING
    )
    assert rc == 0
    assert "no phase markers" in capsys.readouterr().out


def test_cmd_phase_report_skips_malformed_lines(tmp_path, capsys):
    log = tmp_path / "m.jsonl"
    log.write_text(
        "not json\n"
        + json.dumps({"phase": "plan", "resident_tokens": 100, "spent_output_cumulative": 50}) + "\n"
    )
    cost_meter.cmd_phase_report(SimpleNamespace(log=str(log), json=True), _PRICING)
    out = json.loads(capsys.readouterr().out)
    assert len(out["by_phase"]) == 1


# ---------------------------------------------------------------------------
# phase_marker.py hook
# ---------------------------------------------------------------------------


@pytest.fixture
def consenting(monkeypatch):
    monkeypatch.setattr(phase_marker.telemetry_consent, "is_enabled", lambda: True)
    monkeypatch.delenv("DEV_TEAM_COST_METER", raising=False)
    yield


def _run_hook(monkeypatch, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return phase_marker.main()


def test_hook_records_marker_on_handoff(tmp_path, monkeypatch, consenting):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(500, 120, cache_read=50))
    payload = {
        "tool_name": "Skill",
        "tool_input": {"skill": "handoff", "args": "research continue"},
        "transcript_path": str(t),
        "cwd": str(tmp_path),
    }
    rc = _run_hook(monkeypatch, payload)
    assert rc == 0
    marker = tmp_path / ".claude" / "metrics" / "phase-markers.jsonl"
    entry = json.loads(marker.read_text().splitlines()[-1])
    assert entry["phase"] == "research"  # derived from the first args token
    assert entry["resident_tokens"] == 550
    assert entry["spent_output_cumulative"] == 120


def test_hook_ignores_non_handoff_skill(tmp_path, monkeypatch, consenting):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(10, 5))
    payload = {
        "tool_input": {"skill": "code-review"},
        "transcript_path": str(t),
        "cwd": str(tmp_path),
    }
    assert _run_hook(monkeypatch, payload) == 0
    assert not (tmp_path / ".claude" / "metrics" / "phase-markers.jsonl").exists()


def test_hook_opt_out_env(tmp_path, monkeypatch, consenting):
    monkeypatch.setenv("DEV_TEAM_COST_METER", "off")
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(10, 5))
    payload = {
        "tool_input": {"skill": "handoff"},
        "transcript_path": str(t),
        "cwd": str(tmp_path),
    }
    assert _run_hook(monkeypatch, payload) == 0
    assert not (tmp_path / ".claude" / "metrics" / "phase-markers.jsonl").exists()


def test_hook_no_consent_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_marker.telemetry_consent, "is_enabled", lambda: False)
    monkeypatch.delenv("DEV_TEAM_COST_METER", raising=False)
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(10, 5))
    payload = {"tool_input": {"skill": "handoff"}, "transcript_path": str(t), "cwd": str(tmp_path)}
    assert _run_hook(monkeypatch, payload) == 0
    assert not (tmp_path / ".claude" / "metrics" / "phase-markers.jsonl").exists()


def test_hook_label_falls_back_to_handoff_when_no_args(tmp_path, monkeypatch, consenting):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage(10, 5))
    payload = {"tool_input": {"skill": "handoff"}, "transcript_path": str(t), "cwd": str(tmp_path)}
    _run_hook(monkeypatch, payload)
    marker = tmp_path / ".claude" / "metrics" / "phase-markers.jsonl"
    assert json.loads(marker.read_text().splitlines()[-1])["phase"] == "handoff"
