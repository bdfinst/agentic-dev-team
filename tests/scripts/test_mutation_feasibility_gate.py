"""Tests for mutation_feasibility_gate.py — the mutant-kill loop's shim-first
feasibility arbiter (#1158, part of #1156)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_feasibility_gate as gate

# --- decide: the happy path (loop entered) ---------------------------------


def test_fast_pertest_probe_enters_loop():
    d = gate.decide(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=10.0,
        scope_file_count=5,
        budget_seconds=1800.0,
    )
    assert d.outcome == gate.ENTER_LOOP
    assert d.waiver is None
    assert d.estimated_round_seconds == 50.0


def test_healthy_v2_repo_enters_loop_no_regression(monkeypatch):
    # No shim decline, no capture failure, trivially fast — the plain xunit.v2
    # path must be unchanged. Strip the budget env so the default applies
    # regardless of the host shell (hermetic).
    monkeypatch.delenv("DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS", raising=False)
    d = gate.decide(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
    )
    assert d.outcome == gate.ENTER_LOOP


# --- decide: degrade paths --------------------------------------------------


def test_capture_failure_degrades_regardless_of_timing():
    d = gate.decide(
        shim_declined=False,
        capture_failed=True,
        probe_seconds=0.1,  # would be "fast" but capture failed
        scope_file_count=1,
        budget_seconds=1800.0,
    )
    assert d.outcome == gate.DEGRADE
    assert "#1157" in d.reason
    assert d.waiver == gate.WAIVER_MESSAGE


def test_shim_declined_degrades():
    d = gate.decide(
        shim_declined=True,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
    )
    assert d.outcome == gate.DEGRADE
    assert "#1160" in d.reason
    assert d.waiver == gate.WAIVER_MESSAGE


def test_over_budget_degrades():
    d = gate.decide(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=100.0,
        scope_file_count=40,  # 4000s estimated
        budget_seconds=1800.0,
    )
    assert d.outcome == gate.DEGRADE
    assert "budget" in d.reason
    assert d.estimated_round_seconds == 4000.0


def test_shim_decline_takes_precedence_over_capture_and_budget():
    d = gate.decide(
        shim_declined=True,
        capture_failed=True,
        probe_seconds=100.0,
        scope_file_count=40,
    )
    assert d.outcome == gate.DEGRADE
    assert "#1160" in d.reason  # decline reason wins the short-circuit


def test_capture_failure_takes_precedence_over_budget():
    d = gate.decide(
        shim_declined=False,
        capture_failed=True,
        probe_seconds=100.0,
        scope_file_count=40,
    )
    assert d.outcome == gate.DEGRADE
    assert "#1157" in d.reason


# --- estimate_round_seconds -------------------------------------------------


def test_estimate_scales_with_scope():
    assert gate.estimate_round_seconds(10.0, 5) == 50.0


def test_estimate_floors_scope_at_one():
    assert gate.estimate_round_seconds(10.0, 0) == 10.0


def test_estimate_clamps_negative_probe():
    assert gate.estimate_round_seconds(-5.0, 3) == 0.0


# --- resolve_budget_seconds -------------------------------------------------


def test_budget_default_when_unset():
    assert gate.resolve_budget_seconds({}) == gate.DEFAULT_ROUND_BUDGET_SECONDS


def test_budget_reads_real_environ_when_no_dict(monkeypatch):
    # The env is None path reads os.environ; strip then set to pin the branch.
    monkeypatch.delenv("DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS", raising=False)
    assert gate.resolve_budget_seconds() == gate.DEFAULT_ROUND_BUDGET_SECONDS
    monkeypatch.setenv("DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS", "600")
    assert gate.resolve_budget_seconds() == 600.0


def test_budget_env_override():
    assert gate.resolve_budget_seconds(
        {"DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS": "300"}
    ) == 300.0


def test_budget_ignores_nonpositive_and_garbage():
    assert (
        gate.resolve_budget_seconds({"DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS": "0"})
        == gate.DEFAULT_ROUND_BUDGET_SECONDS
    )
    assert (
        gate.resolve_budget_seconds({"DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS": "nan?"})
        == gate.DEFAULT_ROUND_BUDGET_SECONDS
    )


# --- CLI --------------------------------------------------------------------


def test_cli_enter_loop_json(capsys):
    rc = gate._cli(["--probe-seconds", "5", "--scope-files", "3"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.ENTER_LOOP
    assert payload["waiver"] is None


def test_cli_capture_failed_json(capsys):
    rc = gate._cli(["--capture-failed"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.DEGRADE
    assert payload["waiver"] == gate.WAIVER_MESSAGE


def test_cli_shim_declined_flag_wiring(capsys):
    rc = gate._cli(["--shim-declined"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.DEGRADE
    assert "#1160" in payload["reason"]


def test_cli_budget_flag_wiring(capsys):
    # Small budget + slow probe drives the over-budget degrade through argparse.
    rc = gate._cli(
        ["--probe-seconds", "100", "--scope-files", "40", "--budget-seconds", "10"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.DEGRADE
    assert "budget" in payload["reason"]
