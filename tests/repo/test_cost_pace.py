"""Tests for cost_meter.py `pace` — account-level budget pace guidance (#142).

Ported from tests/repo/cost_pace_tests.bats (issue #672).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _repo_root import REPO_ROOT

METER = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "cost_meter.py"


def _ts(days_ago: int) -> str:
    """A timestamp N days before now, in the meter's ISO format."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(METER), "pace", *args], capture_output=True, text=True
    )


def test_pace_no_log_says_nothing_to_pace(tmp_path: Path) -> None:
    res = _run("--log", str(tmp_path / "none.jsonl"))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "nothing to pace" in res.stdout


def test_pace_reports_cumulative_spend_over_the_window(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text(
        f'{{"timestamp":"{_ts(2)}","total":{{"cost_usd":10.0}}}}\n'
        f'{{"timestamp":"{_ts(1)}","total":{{"cost_usd":5.0}}}}\n'
    )
    res = _run("--log", str(log), "--window-days", "7")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "cumulative spend:   $15.0000" in res.stdout


def test_pace_flags_when_projected_spend_exceeds_the_budget(tmp_path: Path) -> None:
    # ~$25/day over 2 days -> projected ~$750/30d, well past a $100 budget.
    log = tmp_path / "log.jsonl"
    log.write_text(
        f'{{"timestamp":"{_ts(2)}","total":{{"cost_usd":30.0}}}}\n'
        f'{{"timestamp":"{_ts(1)}","total":{{"cost_usd":20.0}}}}\n'
    )
    res = _run(
        "--log",
        str(log),
        "--budget",
        "100",
        "--period-days",
        "30",
        "--window-days",
        "7",
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PACE EXCEEDS BUDGET" in res.stdout
    assert "Opus→Sonnet" in res.stdout


def test_pace_within_budget_does_not_flag(tmp_path: Path) -> None:
    # $0.10 total over 2 days -> projected ~$1.5/30d, well under a $100 budget.
    log = tmp_path / "log.jsonl"
    log.write_text(
        f'{{"timestamp":"{_ts(2)}","total":{{"cost_usd":0.05}}}}\n'
        f'{{"timestamp":"{_ts(1)}","total":{{"cost_usd":0.05}}}}\n'
    )
    res = _run(
        "--log",
        str(log),
        "--budget",
        "100",
        "--period-days",
        "30",
        "--window-days",
        "7",
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PACE EXCEEDS BUDGET" not in res.stdout


def test_pace_entries_older_than_the_window_are_excluded(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text(
        f'{{"timestamp":"{_ts(30)}","total":{{"cost_usd":999.0}}}}\n'
        f'{{"timestamp":"{_ts(1)}","total":{{"cost_usd":5.0}}}}\n'
    )
    res = _run("--log", str(log), "--window-days", "7")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "cumulative spend:   $5.0000" in res.stdout
    assert "sessions in window: 1" in res.stdout
