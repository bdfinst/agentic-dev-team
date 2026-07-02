"""#103 — eval variance aggregator: pass@k, flap detection, quarantine.
Model-free (synthetic per-trial actuals), so it runs in CI like the rest of
the grader.

Ported from tests/repo/eval_variance_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIANCE = REPO_ROOT / "scripts" / "eval_variance.py"


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "trials").mkdir()
    # Two pairs: stable-pass (clean::a) and flapping (flap::b).
    (tmp_path / "expected" / "clean.json").write_text(
        '{"fixture":"clean.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}\n'
    )
    (tmp_path / "expected" / "flap.json").write_text(
        '{"fixture":"flap.ts","applicableAgents":["b"],'
        '"agents":{"b":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}\n'
    )
    # Trial 1: both pass.
    (tmp_path / "trials" / "t1.json").write_text(
        '{"clean":{"agents":{"a":{"status":"pass","issues":[]}}},'
        '"flap":{"agents":{"b":{"status":"pass","issues":[]}}}}\n'
    )
    # Trial 2: clean passes, flap FAILS (wrong status).
    (tmp_path / "trials" / "t2.json").write_text(
        '{"clean":{"agents":{"a":{"status":"pass","issues":[]}}},'
        '"flap":{"agents":{"b":{"status":"fail","issues":[]}}}}\n'
    )
    return tmp_path


def _run(case: Path, *extra: str) -> dict:
    res = subprocess.run(
        [
            sys.executable,
            str(VARIANCE),
            "--trials-dir",
            str(case / "trials"),
            "--expected-dir",
            str(case / "expected"),
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else {}


def test_variance_pass_at_k_computed_per_pair(case: Path) -> None:
    data = _run(case)
    assert data["trials"] == 2
    assert data["by_pair"]["clean::a"]["pass_at_k"] == 1.0
    assert data["by_pair"]["flap::b"]["pass_at_k"] == 0.5


def test_variance_a_flapping_pair_is_flagged_and_quarantined(case: Path) -> None:
    data = _run(case)
    assert data["by_pair"]["flap::b"]["flap"] is True
    assert data["by_pair"]["clean::a"]["flap"] is False
    assert data["flaky_count"] == 1
    assert "flap::b" in data["quarantine"]


def test_variance_per_agent_stability_summary(case: Path) -> None:
    data = _run(case)
    assert data["by_agent"]["a"]["mean_pass_at_k"] == 1.0
    assert data["by_agent"]["b"]["flaky_fixtures"] == 1


def test_variance_append_writes_a_metrics_only_trend_record(case: Path) -> None:
    trend = case / "trend.jsonl"
    res = subprocess.run(
        [
            sys.executable,
            str(VARIANCE),
            "--trials-dir",
            str(case / "trials"),
            "--expected-dir",
            str(case / "expected"),
            "--append",
            str(trend),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    lines = trend.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["flaky_count"] == 1
    # metrics only — no fixture/agent names in the trend record
    assert "flap::b" not in trend.read_text()
