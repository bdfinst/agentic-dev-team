"""Delta C (#179): frequency -> lever escalation over the cross-machine
rollup. rare -> hint; recurring+judgment -> instruction-rule;
frequent+matchable -> hook.

Ported from tests/repo/session_extract_escalate_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


@pytest.fixture
def digests(tmp_path: Path) -> Path:
    box = tmp_path / "digests" / "box"
    box.mkdir(parents=True)
    # 2 sessions. permission_denials total 4 (rate 2.0, matchable -> hook).
    # failed_edits total 1 (rate 0.5, not matchable -> instruction-rule).
    # compaction_events total 0 across... add a rare matchable:
    #   retried_bash 1 over 2 sessions = rate 0.4 (>=rare, <frequent),
    #   matchable -> instruction-rule.
    # user_correction_turns total 0 -> omitted (no count).
    (box / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"box","project":"p","session_id":"s1",'
        '"tokens":{"input_tokens":1},"cost_usd":0,'
        '"rework":{"permission_denials":3,"failed_edits":1,"retried_bash_commands":1},'
        '"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},'
        '"utilization":{"skills_invoked":{},"agents_invoked":{}}}\n'
        '{"schema":"session-sync/v1","host":"box","project":"p","session_id":"s2",'
        '"tokens":{"input_tokens":1},"cost_usd":0,'
        '"rework":{"permission_denials":1,"failed_edits":0,"retried_bash_commands":0},'
        '"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},'
        '"utilization":{"skills_invoked":{},"agents_invoked":{}}}\n'
    )
    return tmp_path / "digests"


def _esc(digests: Path, *extra: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--escalate",
            str(digests),
            "--plugin-root",
            str(PLUGIN),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _rec(data: dict, signal: str) -> dict:
    matches = [r for r in data["recommendations"] if r["signal"] == signal]
    assert matches, f"no recommendation for signal {signal}"
    return matches[0]


def test_escalate_frequent_and_matchable_friction_to_hook(digests: Path) -> None:
    data = _esc(digests)
    assert data["schema"] == "telemetry-escalation/v1"
    assert data["sessions"] == 2
    # permission_denials: 4 / 2 = 2.0 rate, matchable -> hook
    rec = _rec(data, "permission_denials")
    assert rec["lever"] == "hook"
    assert rec["per_session_rate"] == 2.0


def test_escalate_recurring_judgment_shaped_friction_to_instruction_rule(
    digests: Path,
) -> None:
    data = _esc(digests)
    # failed_edits: 1/2 = 0.5, not matchable -> instruction-rule
    assert _rec(data, "failed_edits")["lever"] == "instruction-rule"


def test_escalate_matchable_but_below_hook_threshold_to_instruction_rule(
    digests: Path,
) -> None:
    data = _esc(digests)
    # retried_bash_commands: 1/2 = 0.5 (>=rare 0.25, <frequent 1.0), matchable
    assert _rec(data, "retried_bash_commands")["lever"] == "instruction-rule"


def test_escalate_rare_friction_to_hint_threshold_override(digests: Path) -> None:
    # raise rare-rate so 0.5 counts as rare
    data = _esc(digests, "--rare-rate", "0.6")
    assert _rec(data, "failed_edits")["lever"] == "hint"


def test_escalate_recommendations_ranked_worst_first_by_rate(digests: Path) -> None:
    data = _esc(digests)
    # permission_denials (2.0) must rank above failed_edits (0.5)
    assert data["recommendations"][0]["signal"] == "permission_denials"


def test_escalate_zero_count_signals_are_omitted(digests: Path) -> None:
    data = _esc(digests)
    # user_correction_turns total 0 -> not in recommendations
    assert not [
        r for r in data["recommendations"] if r["signal"] == "user_correction_turns"
    ]
