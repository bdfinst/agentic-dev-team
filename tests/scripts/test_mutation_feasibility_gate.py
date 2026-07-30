"""Tests for mutation_feasibility_gate.py — the mutant-kill loop's shim-first
feasibility arbiter (#1158, part of #1156)."""

from __future__ import annotations

import json
import sys

import pytest
from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_feasibility_gate as gate

# --- decide: the happy path (loop entered) ---------------------------------


def test_fast_pertest_probe_enters_loop():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=10.0,
        scope_file_count=5,
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ENTER_LOOP
    assert d.waiver is None
    assert d.estimated_round_seconds == 50.0


def test_healthy_v2_repo_enters_loop_no_regression(monkeypatch):
    # No shim decline, no capture failure, trivially fast — the plain xunit.v2
    # path must be unchanged. Strip the budget env so the default applies
    # regardless of the host shell (hermetic).
    monkeypatch.delenv("DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS", raising=False)
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.ENTER_LOOP


# --- decide: degrade paths --------------------------------------------------


def test_capture_failure_degrades_regardless_of_timing():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=True,
        probe_seconds=0.1,  # would be "fast" but capture failed
        scope_file_count=1,
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1157" in d.reason
    assert d.waiver == gate.WAIVER_MESSAGE


def test_shim_declined_degrades():
    probe = gate.ProbeResult(
        shim_declined=True,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1160" in d.reason
    assert d.waiver == gate.WAIVER_MESSAGE


def test_over_budget_asks_operator():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=100.0,
        scope_file_count=40,  # 4000s estimated
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert "budget" in d.reason
    assert d.estimated_round_seconds == 4000.0
    assert d.waiver is None


def test_estimate_exactly_at_budget_enters_loop():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=10.0,
        scope_file_count=180,  # 1800s estimated == budget
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ENTER_LOOP
    assert d.waiver is None


def test_shim_decline_wins_precedence_over_budget_alone():
    # Isolates shim_declined from capture_failed (unlike the sibling
    # precedence test below) so this exercises a genuinely distinct case:
    # a decline still short-circuits even when capture succeeded and only
    # the budget signal would otherwise fire.
    probe = gate.ProbeResult(
        shim_declined=True,
        capture_failed=False,
        probe_seconds=100.0,
        scope_file_count=40,  # also over budget
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1160" in d.reason
    assert "budget" not in d.reason


def test_shim_decline_takes_precedence_over_capture_and_budget():
    probe = gate.ProbeResult(
        shim_declined=True,
        capture_failed=True,
        probe_seconds=100.0,
        scope_file_count=40,
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1160" in d.reason  # decline reason wins the short-circuit


def test_capture_failure_takes_precedence_over_budget():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=True,
        probe_seconds=100.0,
        scope_file_count=40,
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1157" in d.reason


# --- Decision.waiver: explicit branch over all three Outcome members -------


def test_waiver_raises_on_unrecognized_outcome():
    # Decision.outcome is typed as Outcome, so this can only happen via a
    # value bypassing the type system — the explicit branch must still guard
    # against it rather than silently falling through to a wrong answer.
    d = gate.Decision(outcome="bogus", reason="not a real Outcome member")
    with pytest.raises(ValueError, match="unknown outcome"):
        _ = d.waiver


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
    assert payload["outcome"] == gate.Outcome.ENTER_LOOP.value
    assert payload["waiver"] is None


def test_cli_capture_failed_json(capsys):
    rc = gate._cli(["--capture-failed"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.Outcome.DEGRADE.value
    assert payload["waiver"] == gate.WAIVER_MESSAGE


def test_cli_shim_declined_flag_wiring(capsys):
    rc = gate._cli(["--shim-declined"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.Outcome.DEGRADE.value
    assert "#1160" in payload["reason"]


def test_cli_budget_flag_wiring(capsys):
    # Small budget + slow probe drives the over-budget ask-operator through argparse.
    rc = gate._cli(
        ["--probe-seconds", "100", "--scope-files", "40", "--budget-seconds", "10"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value
    assert "budget" in payload["reason"]
    assert payload["waiver"] is None


def test_cli_explicit_nonpositive_budget_is_clamped_not_passed_through(capsys):
    # #1549: `--budget-seconds 0` used to reach decide() unclamped (argparse
    # sets 0.0, not None, so the `budget_seconds is None` branch never fired),
    # forcing ASK_OPERATOR regardless of how fast the probe was. A fast probe
    # with an explicit non-positive override must now enter the loop, exactly
    # as it would with no --budget-seconds flag at all.
    rc = gate._cli(
        ["--probe-seconds", "1", "--scope-files", "1", "--budget-seconds", "0"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ENTER_LOOP.value
    assert payload["budget_seconds"] == gate.DEFAULT_ROUND_BUDGET_SECONDS


def test_decide_clamps_an_explicit_negative_budget_seconds():
    probe = gate.ProbeResult(
        shim_declined=False, capture_failed=False, probe_seconds=1.0, scope_file_count=1
    )
    decision = gate.decide(probe, budget_seconds=-5.0)
    assert decision.outcome is gate.Outcome.ENTER_LOOP
    assert decision.budget_seconds == gate.DEFAULT_ROUND_BUDGET_SECONDS
