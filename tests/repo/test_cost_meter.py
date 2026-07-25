"""Tests for the runtime cost/token meter (issues #102, #170, #1094):
transcript parsing, per-model + per-thread (main/subagent) + per-agent-type
attribution, token->dollar conversion via model-pricing.json, the append-only
metrics log, regression detection, and the Stop hook wrapper.

#170: attribution is limited to what the harness actually records — the
per-command / per-phase / per-iteration buckets were removed because the
harness exposes no such fields (see scripts spike) and a plugin cannot stamp
them onto the transcript.

#1094: the agent-type dimension reads only fields the harness demonstrably
writes (verified against a real transcript): the native `attributionAgent`
field on sidechain records, the Task/Agent `tool_use` `input.subagent_type` +
`toolUseResult.agentId` dispatch join, and the sibling per-subagent transcript
files under `<dir>/<session-id>/subagents/agent-*.jsonl`. Sidechain usage that
carries none of those signals lands in the honest `unattributed` bucket.

Ported from tests/repo/cost_meter_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

METER = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "cost_meter.py"
HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "cost_meter.py"

TRANSCRIPT = """{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000,"cache_read_input_tokens":5000}}}
{"type":"user","message":{"content":"hi"}}
{"type":"assistant","isSidechain":true,"message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":8000,"output_tokens":1500,"cache_creation_input_tokens":3000}}}
"""


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "t.jsonl").write_text(TRANSCRIPT)
    return tmp_path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(METER), *args], capture_output=True, text=True, check=False
    )


def _report(case: Path) -> dict:
    res = _run("report", "--transcript", str(case / "t.jsonl"), "--json")
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_meter_report_attributes_tokens_per_model_and_totals(case: Path) -> None:
    data = _report(case)
    assert data["by_model"]["claude-opus-4-8"]["input_tokens"] == 10000
    assert data["by_model"]["claude-sonnet-4-6"]["output_tokens"] == 1500
    assert data["totals"]["input_tokens"] == 18000


def test_meter_report_splits_spend_by_thread_main_vs_subagent_via_issidechain(
    case: Path,
) -> None:
    data = _report(case)
    # main-loop opus turn
    assert data["by_thread"]["main"]["input_tokens"] == 10000
    # subagent sonnet turn
    assert data["by_thread"]["subagent"]["output_tokens"] == 1500


def test_meter_the_removed_inert_buckets_are_gone_170(case: Path) -> None:
    data = _report(case)
    assert "by_command" not in data
    assert "by_phase" not in data
    assert "by_iteration" not in data
    # by_agent_type (#1094) is a distinct, genuinely-attributed dimension —
    # the inert opaque "by_agent" bucket stays gone.
    assert "by_agent" not in data


# ---------------------------------------------------------------------------
# by_agent_type (#1094) — agent-type attribution from harness-recorded fields
# ---------------------------------------------------------------------------

# Main transcript exercising all three attribution outcomes:
#   * a plain main-loop turn                         -> "main"
#   * a Task dispatch (tool_use subagent_type) whose paired tool_result
#     carries toolUseResult.agentId                  -> join map agent001
#   * a sidechain turn with native attributionAgent  -> "test-review" (primary)
#   * a sidechain turn with only agentId=agent001    -> "security-review" (join)
#   * a sidechain turn with neither signal           -> "unattributed"
AGENT_TYPE_TRANSCRIPT = (
    '{"type":"assistant","message":{"model":"claude-opus-4-8",'
    '"usage":{"input_tokens":1000,"output_tokens":100}}}\n'
    '{"type":"assistant","message":{"model":"claude-opus-4-8",'
    '"content":[{"type":"tool_use","id":"toolu_1","name":"Task",'
    '"input":{"subagent_type":"security-review","description":"d",'
    '"prompt":"sekrit-dispatch-prompt"}}]}}\n'
    '{"type":"user","toolUseResult":{"agentId":"agent001","status":"async_launched"},'
    '"message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1"}]}}\n'
    '{"type":"assistant","isSidechain":true,"attributionAgent":"test-review",'
    '"message":{"model":"claude-sonnet-4-6",'
    '"usage":{"input_tokens":2000,"output_tokens":200}}}\n'
    '{"type":"assistant","isSidechain":true,"agentId":"agent001",'
    '"message":{"model":"claude-sonnet-4-6",'
    '"usage":{"input_tokens":3000,"output_tokens":300}}}\n'
    '{"type":"assistant","isSidechain":true,'
    '"message":{"model":"claude-sonnet-4-6",'
    '"usage":{"input_tokens":4000,"output_tokens":400}}}\n'
)


@pytest.fixture
def agent_case(tmp_path: Path) -> Path:
    (tmp_path / "a.jsonl").write_text(AGENT_TYPE_TRANSCRIPT)
    return tmp_path


def _agent_report(agent_case: Path) -> dict:
    res = _run("report", "--transcript", str(agent_case / "a.jsonl"), "--json")
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_meter_attributes_sidechain_spend_via_native_attribution_agent_field(
    agent_case: Path,
) -> None:
    data = _agent_report(agent_case)
    assert data["by_agent_type"]["test-review"]["input_tokens"] == 2000
    assert data["by_agent_type"]["test-review"]["messages"] == 1


def test_meter_attributes_sidechain_spend_via_task_dispatch_agent_id_join(
    agent_case: Path,
) -> None:
    data = _agent_report(agent_case)
    assert data["by_agent_type"]["security-review"]["input_tokens"] == 3000


def test_meter_buckets_unmappable_sidechain_spend_as_unattributed(
    agent_case: Path,
) -> None:
    data = _agent_report(agent_case)
    assert data["by_agent_type"]["unattributed"]["input_tokens"] == 4000


def test_meter_main_loop_spend_lands_in_main_and_dimension_sums_to_totals(
    agent_case: Path,
) -> None:
    data = _agent_report(agent_case)
    assert data["by_agent_type"]["main"]["input_tokens"] == 1000
    assert sum(b["input_tokens"] for b in data["by_agent_type"].values()) == (
        data["totals"]["input_tokens"]
    )


def test_meter_no_sidechain_transcript_yields_only_a_main_bucket(case: Path) -> None:
    record = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-8",
            "usage": {"input_tokens": 100, "output_tokens": 10},
        },
    }
    (case / "m.jsonl").write_text(json.dumps(record) + "\n")
    res = _run("report", "--transcript", str(case / "m.jsonl"), "--json")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert list(data["by_agent_type"]) == ["main"]
    assert "unattributed" not in data["by_agent_type"]


def test_meter_report_folds_in_sibling_per_subagent_transcript_files(
    tmp_path: Path,
) -> None:
    """Newer harness layout (#1094): sidechain turns live in
    <dir>/<session-id>/subagents/agent-*.jsonl, not inline — the meter must
    scan them or subagent spend is invisible."""
    (tmp_path / "s.jsonl").write_text(
        '{"type":"assistant","message":{"model":"claude-opus-4-8",'
        '"usage":{"input_tokens":1000,"output_tokens":100}}}\n'
    )
    subdir = tmp_path / "s" / "subagents"
    subdir.mkdir(parents=True)
    (subdir / "agent-abc123.jsonl").write_text(
        '{"type":"assistant","isSidechain":true,"agentId":"abc123",'
        '"attributionAgent":"security-review",'
        '"message":{"model":"claude-sonnet-4-6",'
        '"usage":{"input_tokens":5000,"output_tokens":500}}}\n'
    )
    res = _run("report", "--transcript", str(tmp_path / "s.jsonl"), "--json")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["totals"]["input_tokens"] == 6000
    assert data["by_thread"]["subagent"]["input_tokens"] == 5000
    assert data["by_agent_type"]["security-review"]["input_tokens"] == 5000


def test_meter_record_log_line_carries_by_agent_type_but_never_prompt_text(
    agent_case: Path,
) -> None:
    log = agent_case / "log.jsonl"
    res = _run("record", "--transcript", str(agent_case / "a.jsonl"), "--log", str(log))
    assert res.returncode == 0, res.stdout + res.stderr
    raw = log.read_text()
    entry = json.loads(raw.splitlines()[0])
    assert entry["by_agent_type"]["test-review"]["input_tokens"] == 2000
    assert entry["by_agent_type"]["security-review"]["input_tokens"] == 3000
    assert entry["by_agent_type"]["unattributed"]["input_tokens"] == 4000
    # Privacy boundary: agent-type identifiers only — the dispatch prompt from
    # the Task tool_use input must never reach the metrics log.
    assert "sekrit-dispatch-prompt" not in raw


def test_meter_dollar_cost_matches_the_pricing_table(case: Path) -> None:
    data = _report(case)
    # opus: 10000/1e6*5 + 2000/1e6*25 + 5000/1e6*5*0.1 = 0.05+0.05+0.0025 = 0.1025
    assert data["by_model"]["claude-opus-4-8"]["cost_usd"] == 0.1025
    # sonnet: 8000/1e6*3 + 1500/1e6*15 + 3000/1e6*3*1.25 = 0.024+0.0225+0.01125 = 0.05775
    assert data["by_model"]["claude-sonnet-4-6"]["cost_usd"] == 0.05775


def test_meter_unknown_model_is_flagged_as_unpriced_cost_0_not_crash(
    case: Path,
) -> None:
    record = {
        "type": "assistant",
        "message": {
            "model": "gpt-fake",
            "usage": {"input_tokens": 100, "output_tokens": 10},
        },
    }
    (case / "u.jsonl").write_text(json.dumps(record) + "\n")
    res = _run("report", "--transcript", str(case / "u.jsonl"), "--json")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["unpriced_models"][0] == "gpt-fake"
    assert data["totals"]["cost_usd"] == 0.0


def test_meter_record_appends_a_session_summary_line_with_by_model_and_by_thread(
    case: Path,
) -> None:
    log = case / "log.jsonl"
    res = _run("record", "--transcript", str(case / "t.jsonl"), "--log", str(log))
    assert res.returncode == 0, res.stdout + res.stderr
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["total"]["messages"] == 2
    assert entry["by_model"]["claude-opus-4-8"]["input_tokens"] == 10000
    assert entry["by_thread"]["subagent"]["output_tokens"] == 1500


def test_meter_regression_flags_a_cost_spike_passes_within_tolerance(
    tmp_path: Path,
) -> None:
    ok = tmp_path / "ok.jsonl"
    ok.write_text('{"total":{"cost_usd":1.0}}\n{"total":{"cost_usd":1.1}}\n')
    res = _run("regression", "--log", str(ok), "--tolerance", "0.5")
    assert res.returncode == 0, res.stdout + res.stderr

    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":5.0}}\n'
    )
    res = _run("regression", "--log", str(bad), "--tolerance", "0.5")
    assert res.returncode == 1
    assert "COST REGRESSION" in res.stdout + res.stderr


def test_meter_regression_window_uses_only_recent_priors(tmp_path: Path) -> None:
    # priors: 1,1,1, then a high 9; latest 5. All-time mean(1,1,1,9)=3 -> limit 4.5
    # -> 5 regresses. Windowed mean of last 1 prior (9) -> limit 13.5 -> 5 passes.
    log = tmp_path / "w.jsonl"
    log.write_text(
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":9.0}}\n'
        '{"total":{"cost_usd":5.0}}\n'
    )
    res = _run("regression", "--log", str(log), "--tolerance", "0.5")
    assert res.returncode == 1

    res = _run("regression", "--log", str(log), "--tolerance", "0.5", "--window", "1")
    assert res.returncode == 0


def _consent_env(tmp_path: Path, **extra: str) -> dict:
    """os.environ overlaid with a HOME whose ~/.claude/telemetry.json opts in."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "telemetry.json").write_text('{"enabled": true}')
    return {**os.environ, "HOME": str(home), **extra}


def _no_consent_env(tmp_path: Path, **extra: str) -> dict:
    """os.environ overlaid with a HOME that has no ~/.claude/telemetry.json."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "HOME": str(home), **extra}


def test_hook_stop_payload_writes_a_metrics_line_under_cwd_metrics(
    case: Path,
) -> None:
    payload = json.dumps({"transcript_path": str(case / "t.jsonl"), "cwd": str(case)})
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=_consent_env(case),
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert (case / ".claude" / "metrics" / "cost-metering.jsonl").is_file()


def test_hook_dev_team_cost_meter_off_is_a_noop(case: Path) -> None:
    payload = json.dumps({"transcript_path": str(case / "t.jsonl"), "cwd": str(case)})
    env = _consent_env(case, DEV_TEAM_COST_METER="off")
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (case / ".claude" / "metrics" / "cost-metering.jsonl").exists()


def test_hook_missing_transcript_fails_open_exit_0_no_write(case: Path) -> None:
    payload = json.dumps({"transcript_path": "/nope/x.jsonl", "cwd": str(case)})
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=_consent_env(case),
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (case / ".claude" / "metrics" / "cost-metering.jsonl").exists()


def test_hook_no_consent_file_is_a_noop(case: Path) -> None:
    payload = json.dumps({"transcript_path": str(case / "t.jsonl"), "cwd": str(case)})
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=_no_consent_env(case),
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (case / ".claude" / "metrics" / "cost-metering.jsonl").exists()


def test_hook_consent_enabled_but_per_writer_opt_out_still_suppresses(
    case: Path,
) -> None:
    payload = json.dumps({"transcript_path": str(case / "t.jsonl"), "cwd": str(case)})
    env = _consent_env(case, DEV_TEAM_COST_METER="off")
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (case / ".claude" / "metrics" / "cost-metering.jsonl").exists()


def test_settings_json_registers_cost_meter_py_on_stop_and_subagentstop() -> None:
    settings = json.loads(
        (REPO_ROOT / "plugins" / "dev-team" / "settings.json").read_text()
    )
    stop_hooks = [
        h["command"] for entry in settings["hooks"]["Stop"] for h in entry["hooks"]
    ]
    assert any("cost_meter.py" in c for c in stop_hooks)
    subagent_stop_hooks = [
        h["command"]
        for entry in settings["hooks"]["SubagentStop"]
        for h in entry["hooks"]
    ]
    assert any("cost_meter.py" in c for c in subagent_stop_hooks)
