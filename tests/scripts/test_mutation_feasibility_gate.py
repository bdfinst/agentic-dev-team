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


# --- v3 shim-breaking blockers reach the same ask-operator decision point ----
#
# #1791: the ask-operator path used to be a pure time-budget question. When the
# detector finds shim-breaking constructs, that same decision point must carry
# the per-construct breakdown and the four remediation options instead — and it
# must ASK, never silently pick the degrade path on the operator's behalf.


def _finding(file: str, construct: str, **over) -> dict:
    base = {
        "file": file,
        "line": 7,
        "construct": construct,
        "compile_ability": "no-v2-equivalent",
        "coverage_impact": "bearing",
        "snippet": "[AutoData]",
    }
    base.update(over)
    return base


def test_v3_blockers_ask_the_operator_instead_of_degrading():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        project="Acme.Tests",
        v3_blockers=(_finding("A.cs", "autofixture-auto-data"),),
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert d.waiver is None


def test_v3_question_carries_the_per_construct_breakdown():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        project="Acme.Tests",
        v3_blockers=(
            _finding("A.cs", "autofixture-auto-data"),
            _finding("B.cs", "fact-explicit", coverage_impact="neutral"),
        ),
    )
    d = gate.decide(probe)
    constructs = {g["construct"] for g in d.question["breakdown"]}
    assert constructs == {"autofixture-auto-data", "fact-explicit"}
    assert d.question["files"] == ["A.cs", "B.cs"]


def test_v3_question_carries_all_four_remediation_options():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_blockers=(_finding("A.cs", "assert-skip"),),
    )
    d = gate.decide(probe)
    assert [o["id"] for o in d.question["options"]] == [
        "port",
        "exclude",
        "skip",
        "degrade",
    ]
    for option in d.question["options"]:
        assert option["tradeoff"].strip()


def test_v3_reason_names_what_is_blocking():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        project="Acme.Tests",
        v3_blockers=(_finding("A.cs", "autofixture-auto-data"),),
    )
    d = gate.decide(probe)
    assert "autofixture-auto-data" in d.reason
    assert "#1160" in d.reason or "#1791" in d.reason


def test_v3_blockers_and_over_budget_are_one_question_not_two():
    # Both signals fire: the operator gets a single decision point that states
    # the blockers AND the timing, rather than a blockers question that hides
    # the fact that a round is also unaffordable.
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=100.0,
        scope_file_count=40,
        v3_blockers=(_finding("A.cs", "assert-skip"),),
    )
    d = gate.decide(probe, budget_seconds=10.0)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert d.estimated_round_seconds == 4000.0
    assert d.budget_seconds == 10.0
    assert "budget" in d.reason
    assert d.question is not None


def test_an_explicit_decline_still_degrades_even_with_blockers():
    # shim_declined means the operator already answered "degrade" at this gate;
    # re-asking would loop.
    probe = gate.ProbeResult(
        shim_declined=True,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_blockers=(_finding("A.cs", "assert-skip"),),
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert d.waiver == gate.WAIVER_MESSAGE


def test_capture_failure_still_degrades_even_with_blockers():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=True,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_blockers=(_finding("A.cs", "assert-skip"),),
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1157" in d.reason


def test_no_blockers_leaves_the_v2_path_untouched():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_blockers=(),
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ENTER_LOOP
    assert d.question is None


def test_unclassified_v3_files_alone_still_ask():
    # The guard's token scan is broader than the detector's classified set; a
    # file it flags but cannot classify must still reach the operator.
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_unclassified_files=("Legacy.cs",),
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert d.question["unclassified_files"] == ["Legacy.cs"]


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


def _empty_findings_file(tmp_path):
    findings_file = tmp_path / "empty-findings.json"
    findings_file.write_text(json.dumps({"findings": []}), encoding="utf-8")
    return findings_file


def test_cli_enter_loop_json(capsys, tmp_path):
    rc = gate._cli(
        ["--probe-seconds", "5", "--scope-files", "3",
         "--v3-findings-json", str(_empty_findings_file(tmp_path))]
    )
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.Outcome.ENTER_LOOP.value
    assert payload["waiver"] is None


def test_cli_capture_failed_json(capsys):
    # Omits --v3-findings-json on purpose: capture_failed short-circuits to
    # DEGRADE before the #1870 fail-closed check is ever reached.
    rc = gate._cli(["--capture-failed"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.Outcome.DEGRADE.value
    assert payload["waiver"] == gate.WAIVER_MESSAGE


def test_cli_shim_declined_flag_wiring(capsys):
    # Omits --v3-findings-json on purpose: shim_declined short-circuits to
    # DEGRADE before the #1870 fail-closed check is ever reached.
    rc = gate._cli(["--shim-declined"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["outcome"] == gate.Outcome.DEGRADE.value
    assert "#1160" in payload["reason"]


def test_cli_budget_flag_wiring(capsys, tmp_path):
    # Small budget + slow probe drives the over-budget ask-operator through argparse.
    rc = gate._cli(
        ["--probe-seconds", "100", "--scope-files", "40", "--budget-seconds", "10",
         "--v3-findings-json", str(_empty_findings_file(tmp_path))]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value
    assert "budget" in payload["reason"]
    assert payload["waiver"] is None


def test_cli_explicit_nonpositive_budget_is_clamped_not_passed_through(capsys, tmp_path):
    # #1549: `--budget-seconds 0` used to reach decide() unclamped (argparse
    # sets 0.0, not None, so the `budget_seconds is None` branch never fired),
    # forcing ASK_OPERATOR regardless of how fast the probe was. A fast probe
    # with an explicit non-positive override must now enter the loop, exactly
    # as it would with no --budget-seconds flag at all.
    rc = gate._cli(
        ["--probe-seconds", "1", "--scope-files", "1", "--budget-seconds", "0",
         "--v3-findings-json", str(_empty_findings_file(tmp_path))]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ENTER_LOOP.value
    assert payload["budget_seconds"] == gate.DEFAULT_ROUND_BUDGET_SECONDS


# --- fail-closed on an omitted --v3-findings-json (#1870) -------------------


def test_cli_missing_v3_findings_json_asks_operator_not_enter_loop(capsys):
    # Every call into this CLI is for an xunit.v3 project by calling
    # convention (agents/mutation-kill.md: "plain xunit.v2 / other stacks
    # skip this gate") — omitting the detector output must not silently read
    # as "detector ran, found nothing".
    rc = gate._cli(["--probe-seconds", "1", "--scope-files", "1"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value
    assert "--v3-findings-json" in payload["reason"]
    assert payload["question"] is None


def test_decide_v3_findings_unknown_forces_ask_operator():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_findings_known=False,
    )
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert d.waiver is None
    assert "#1870" in d.reason


def test_decide_v3_findings_unknown_combines_with_over_budget_reason():
    probe = gate.ProbeResult(
        shim_declined=False,
        capture_failed=False,
        probe_seconds=100.0,
        scope_file_count=40,
        v3_findings_known=False,
    )
    d = gate.decide(probe, budget_seconds=10.0)
    assert d.outcome is gate.Outcome.ASK_OPERATOR
    assert "budget" in d.reason
    assert "#1870" in d.reason


def test_decide_v3_findings_unknown_does_not_override_shim_declined():
    probe = gate.ProbeResult(
        shim_declined=True,
        capture_failed=False,
        probe_seconds=1.0,
        scope_file_count=1,
        v3_findings_known=False,
    )
    d = gate.decide(probe)
    assert d.outcome is gate.Outcome.DEGRADE
    assert "#1160" in d.reason


def test_decide_direct_callers_default_to_known_and_are_unaffected():
    # Direct decide()/ProbeResult(...) callers that already know their own
    # "detector ran, found nothing" state (the default `v3_blockers=()`) must
    # be unaffected by the CLI-only #1870 fail-closed check.
    probe = gate.ProbeResult(
        shim_declined=False, capture_failed=False, probe_seconds=1.0, scope_file_count=1
    )
    assert probe.v3_findings_known is True
    d = gate.decide(probe, budget_seconds=1800.0)
    assert d.outcome is gate.Outcome.ENTER_LOOP


def test_cli_v3_findings_json_flows_into_the_question(capsys, tmp_path):
    findings_file = tmp_path / "findings.json"
    findings_file.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "file": "A.cs",
                        "line": 3,
                        "construct": "autofixture-auto-data",
                        "compile_ability": "no-v2-equivalent",
                        "coverage_impact": "bearing",
                        "snippet": "[AutoData]",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rc = gate._cli(
        [
            "--probe-seconds", "1",
            "--scope-files", "1",
            "--project", "Acme.Tests",
            "--v3-findings-json", str(findings_file),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value
    assert payload["question"]["files"] == ["A.cs"]
    # A ready-to-present rendering travels with the payload so the agent does
    # not have to re-derive the operator-facing text.
    assert "autofixture-auto-data" in payload["question_text"]
    assert "degrade" in payload["question_text"]


def test_cli_accepts_a_bare_findings_list(capsys, tmp_path):
    findings_file = tmp_path / "list.json"
    findings_file.write_text(
        json.dumps([{"file": "A.cs", "construct": "assert-skip"}]), encoding="utf-8"
    )
    rc = gate._cli(["--v3-findings-json", str(findings_file)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value


def test_cli_unreadable_findings_file_is_a_hard_error_not_a_silent_pass(capsys, tmp_path):
    # Silently treating a missing detector output as "no blockers" would hand
    # back enter-loop and skip the operator gate entirely — the exact class of
    # silent decision #1791 exists to stop.
    rc = gate._cli(["--v3-findings-json", str(tmp_path / "missing.json")])
    assert rc != 0


def test_cli_unclassified_flag_wiring(capsys):
    rc = gate._cli(["--v3-unclassified", "Legacy.cs"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["outcome"] == gate.Outcome.ASK_OPERATOR.value
    assert payload["question"]["unclassified_files"] == ["Legacy.cs"]


def test_decide_clamps_an_explicit_negative_budget_seconds():
    probe = gate.ProbeResult(
        shim_declined=False, capture_failed=False, probe_seconds=1.0, scope_file_count=1
    )
    decision = gate.decide(probe, budget_seconds=-5.0)
    assert decision.outcome is gate.Outcome.ENTER_LOOP
    assert decision.budget_seconds == gate.DEFAULT_ROUND_BUDGET_SECONDS
