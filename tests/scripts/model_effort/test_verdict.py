"""The stress-matrix verdict (model_effort.verdict): downgrade, upgrade or keep, with a reason."""

from __future__ import annotations

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from _model_effort_support import _trial_result
from model_effort import fixtures as fixture_resolution
from model_effort import run_types
from model_effort.arm import BASELINE_LABEL, Arm
from model_effort.grader_config import DEFAULT_GRADING, AgentGrading, GraderKind
from model_effort.outcome import Outcome
from model_effort.run_status import AbortReason
from model_effort.stress_arms import STEP_DOWN_LABEL, STEP_UP_LABEL
from model_effort.verdict import (
    DECISION_DOWNGRADE,
    DECISION_KEEP,
    DECISION_UPGRADE,
    RECALL_GAP_EXCLUDED_AGENTS,
    ArmTally,
    FixtureTally,
    decide,
    stress_verdict,
    verdict_dict,
)

TRIALS = 4
FINDING = "planted-defect"
CLEAN = "clean-file"


def _tally(
    label: str,
    finding_passes: int,
    *,
    false_positives: int = 0,
    ungraded: dict[str, int] | None = None,
    extra_findings: dict[str, int] | None = None,
    model: str = "sonnet",
    effort: str = "high",
) -> ArmTally:
    findings = {FINDING: finding_passes, **(extra_findings or {})}
    return ArmTally(
        label=label,
        model=model,
        effort=effort,
        fixtures=(
            *(
                FixtureTally(stem, expected_clean=False, trials=TRIALS, passes=passes)
                for stem, passes in findings.items()
            ),
            FixtureTally(
                CLEAN,
                expected_clean=True,
                trials=TRIALS,
                passes=TRIALS - false_positives,
            ),
        ),
        clean_false_positives=false_positives,
        ungraded=ungraded or {},
    )


def _current(passes: int = 2, **kwargs) -> ArmTally:
    return _tally(BASELINE_LABEL, passes, **kwargs)


def _down(passes: int = 2, **kwargs) -> ArmTally:
    return _tally(STEP_DOWN_LABEL, passes, model="haiku", **kwargs)


def _up(passes: int = 0, **kwargs) -> ArmTally:
    return _tally(STEP_UP_LABEL, passes, model="opus", **kwargs)


# --- downgrade (recall, clean-fixture false positives, parse) -------------------


def test_equal_recall_no_extra_false_positive_and_full_parse_downgrades():
    verdict = decide(_current(2), _down(2), _up(0))

    assert verdict.decision == DECISION_DOWNGRADE
    assert verdict.arm_label == STEP_DOWN_LABEL
    assert (verdict.model, verdict.effort) == ("haiku", "high")


def test_one_trial_less_recall_keeps():
    verdict = decide(_current(3), _down(2), _up(0))

    assert verdict.decision == DECISION_KEEP
    assert "recall 2/4 below the current tier's 3/4" in verdict.reason


def test_one_extra_clean_fixture_false_positive_keeps():
    verdict = decide(
        _current(2, false_positives=1), _down(2, false_positives=2), _up(0)
    )

    assert verdict.decision == DECISION_KEEP
    assert (
        "2 clean-fixture false positives, above the current tier's 1" in verdict.reason
    )


def test_equal_false_positives_still_downgrade():
    verdict = decide(
        _current(2, false_positives=1), _down(2, false_positives=1), _up(0)
    )

    assert verdict.decision == DECISION_DOWNGRADE


def test_one_unparsed_output_keeps_even_with_better_recall():
    verdict = decide(
        _current(2), _down(4, ungraded={Outcome.PARSE_FAILURE.value: 1}), _up(0)
    )

    assert verdict.decision == DECISION_KEEP
    assert "1 trial(s) with no gradeable output (parse_failure 1)" in verdict.reason


def test_a_timeout_in_the_lower_arm_also_blocks_the_downgrade():
    verdict = decide(_current(2), _down(2, ungraded={Outcome.TIMEOUT.value: 1}), None)

    assert verdict.decision == DECISION_KEEP
    assert "timeout 1" in verdict.reason


def test_no_step_down_arm_keeps_with_that_reason():
    verdict = decide(_current(2), None, _up(0))

    assert verdict.decision == DECISION_KEEP
    assert (
        "no step-down arm: sonnet/high has no lower rung on the model or effort ladder"
        in verdict.reason
    )


def test_no_arm_either_way_keeps_and_names_both_missing_arms():
    verdict = decide(_current(2), None, None)

    assert verdict.decision == DECISION_KEEP
    assert verdict.downgrade_passes is False
    assert verdict.downgrade_reason == (
        "no step-down arm: sonnet/high has no lower rung on the model or effort ladder"
    )
    assert verdict.upgrade_reason == (
        "no step-up arm: sonnet/high has no higher rung on the model or effort ladder"
    )
    assert verdict.reason == (
        f"downgrade: {verdict.downgrade_reason}. upgrade: {verdict.upgrade_reason}"
    )


def test_recall_compares_rates_not_counts():
    current = ArmTally(
        BASELINE_LABEL,
        "sonnet",
        "high",
        (FixtureTally(FINDING, False, trials=4, passes=2),),
        0,
        {},
    )
    lower = ArmTally(
        STEP_DOWN_LABEL,
        "haiku",
        "high",
        (FixtureTally(FINDING, False, trials=2, passes=1),),
        0,
        {},
    )

    assert decide(current, lower, None).decision == DECISION_DOWNGRADE


# --- upgrade (higher tier catches what the current tier always misses) ----------


def test_higher_tier_passing_exactly_half_its_trials_on_a_finding_current_always_misses_upgrades():
    verdict = decide(_current(0), _down(0), _up(TRIALS // 2))

    assert verdict.decision == DECISION_UPGRADE
    assert verdict.arm_label == STEP_UP_LABEL
    assert verdict.upgrade_findings == (FINDING,)
    assert (verdict.model, verdict.effort) == ("opus", "high")


def test_higher_tier_passing_just_under_half_does_not_upgrade():
    verdict = decide(_current(0), None, _up(TRIALS // 2 - 1))

    assert verdict.decision == DECISION_KEEP
    assert verdict.upgrade_findings == ()


def test_current_tier_catching_the_finding_once_blocks_the_upgrade():
    verdict = decide(_current(1), None, _up(TRIALS))

    assert verdict.decision == DECISION_KEEP


def test_odd_trial_count_needs_more_than_the_lower_half():
    odd = 5
    current = ArmTally(
        BASELINE_LABEL, "sonnet", "high", (FixtureTally(FINDING, False, odd, 0),), 0, {}
    )
    up_two = ArmTally(
        STEP_UP_LABEL, "opus", "high", (FixtureTally(FINDING, False, odd, 2),), 0, {}
    )
    up_three = ArmTally(
        STEP_UP_LABEL, "opus", "high", (FixtureTally(FINDING, False, odd, 3),), 0, {}
    )

    assert decide(current, None, up_two).decision == DECISION_KEEP
    assert decide(current, None, up_three).decision == DECISION_UPGRADE


def test_a_clean_fixture_is_never_an_upgrade_finding():
    current = ArmTally(
        BASELINE_LABEL, "sonnet", "high", (FixtureTally(CLEAN, True, 4, 0),), 4, {}
    )
    up = ArmTally(
        STEP_UP_LABEL, "opus", "high", (FixtureTally(CLEAN, True, 4, 4),), 0, {}
    )

    assert decide(current, None, up).decision == DECISION_KEEP


def test_upgrade_wins_over_a_passing_downgrade():
    verdict = decide(
        _current(2, extra_findings={"subtle": 0}),
        _down(2, extra_findings={"subtle": 0}),
        _up(2, extra_findings={"subtle": 3}),
    )

    assert verdict.decision == DECISION_UPGRADE
    assert verdict.upgrade_findings == ("subtle",)
    assert verdict.downgrade_passes is True


def test_an_ungraded_step_up_trial_blocks_the_upgrade_and_says_why():
    verdict = decide(
        _current(0), None, _up(TRIALS, ungraded={Outcome.PARSE_FAILURE.value: 1})
    )

    assert verdict.decision == DECISION_KEEP
    assert (
        "step-up has 1 trial(s) with no gradeable output (parse_failure 1)"
        in verdict.upgrade_reason
    )
    assert verdict.upgrade_reason in verdict.reason


def test_more_step_up_clean_fixture_false_positives_block_the_upgrade():
    verdict = decide(_current(0), None, _up(TRIALS, false_positives=1))

    assert verdict.decision == DECISION_KEEP
    assert (
        "step-up has 1 clean-fixture false positives, above the current tier's 0"
        in verdict.upgrade_reason
    )


def test_equal_step_up_false_positives_still_upgrade():
    verdict = decide(
        _current(0, false_positives=1), None, _up(TRIALS, false_positives=1)
    )

    assert verdict.decision == DECISION_UPGRADE


def test_a_blocked_upgrade_falls_back_to_a_passing_downgrade():
    verdict = decide(
        _current(0), _down(0), _up(TRIALS, ungraded={Outcome.TIMEOUT.value: 2})
    )

    assert verdict.decision == DECISION_DOWNGRADE
    assert "timeout 2" in verdict.upgrade_reason


def test_upgrade_lists_every_finding_it_adds_in_fixture_order():
    verdict = decide(
        _current(0, extra_findings={"second": 0}),
        None,
        _up(2, extra_findings={"second": 4}),
    )

    assert verdict.upgrade_findings == (FINDING, "second")


def test_keep_reason_names_both_directions():
    verdict = decide(_current(3), _down(2), _up(0))

    assert "downgrade:" in verdict.reason
    assert "upgrade:" in verdict.reason


# --- the artifact's verdict, from the run's arms --------------------------------


def _arm_run(label, model, outcomes_by_stem, clean_stems=()):
    return run_types.ArmRun(
        arm=Arm(label, model, "high"),
        trials_per_fixture=max(len(o) for o in outcomes_by_stem.values()),
        fixture_trials=[
            run_types.FixtureTrials(
                stem=stem,
                kind=fixture_resolution.FixtureKind.FILE,
                expected_clean=stem in clean_stems,
                results=[_trial_result(outcome) for outcome in outcomes],
            )
            for stem, outcomes in outcomes_by_stem.items()
        ],
    )


def _runs(trials: int, down_pass: bool = True):
    finding = [Outcome.PASS] * trials
    lower = [Outcome.PASS if down_pass else Outcome.GRADED_FAIL] * trials
    return [
        _arm_run(BASELINE_LABEL, "sonnet", {FINDING: finding}),
        _arm_run(STEP_DOWN_LABEL, "haiku", {FINDING: lower}),
    ]


RUBRIC = AgentGrading(GraderKind.RUBRIC)


def test_stress_verdict_tallies_the_run_and_downgrades():
    verdict = stress_verdict("scout", _runs(3), DEFAULT_GRADING, [FINDING], None)

    assert verdict.decision == DECISION_DOWNGRADE


def test_stress_verdict_counts_a_graded_fail_on_a_clean_fixture_as_a_false_positive():
    current = _arm_run(BASELINE_LABEL, "sonnet", {CLEAN: [Outcome.PASS]}, (CLEAN,))
    lower = _arm_run(STEP_DOWN_LABEL, "haiku", {CLEAN: [Outcome.GRADED_FAIL]}, (CLEAN,))

    verdict = stress_verdict("scout", [current, lower], DEFAULT_GRADING, [CLEAN], None)

    assert verdict.decision == DECISION_KEEP
    assert "false positive" in verdict.reason


@pytest.mark.parametrize(
    ("trials", "decision"), [(9, DECISION_KEEP), (10, DECISION_DOWNGRADE)]
)
def test_rubric_evidence_moves_a_tier_only_at_ten_trials_per_arm(trials, decision):
    verdict = stress_verdict("scout", _runs(trials), RUBRIC, [FINDING], None)

    assert verdict.decision == decision


def test_rubric_keep_below_ten_trials_says_why():
    verdict = stress_verdict("scout", _runs(9), RUBRIC, [FINDING], None)

    assert "rubric-judged evidence needs 10 graded trials" in verdict.reason


def test_an_incomplete_run_keeps():
    verdict = stress_verdict(
        "scout", _runs(3), DEFAULT_GRADING, [FINDING], AbortReason.MAX_COST
    )

    assert verdict.decision == DECISION_KEEP
    assert "run incomplete (max-cost)" in verdict.reason


def test_correctness_review_results_never_move_a_tier():
    assert "correctness-review" in RECALL_GAP_EXCLUDED_AGENTS

    verdict = stress_verdict(
        "correctness-review", _runs(10), DEFAULT_GRADING, [FINDING], None
    )

    assert verdict.decision == DECISION_KEEP
    assert "recall gap" in verdict.reason


def test_verdict_dict_records_the_decision_the_arm_and_both_directions():
    data = verdict_dict(decide(_current(0), _down(0), _up(TRIALS)))

    assert data == {
        "decision": DECISION_UPGRADE,
        "reason": data["reason"],
        "arm": STEP_UP_LABEL,
        "model": "opus",
        "effort": "high",
        "downgrade": {"passes": True, "reason": data["downgrade"]["reason"]},
        "upgrade": {"findings": [FINDING], "reason": data["upgrade"]["reason"]},
        "recall": {
            BASELINE_LABEL: {"passes": 0, "trials": TRIALS},
            STEP_DOWN_LABEL: {"passes": 0, "trials": TRIALS},
            STEP_UP_LABEL: {"passes": TRIALS, "trials": TRIALS},
        },
    }


def test_verdict_dict_for_a_blocked_keep_has_no_arm():
    verdict = stress_verdict(
        "scout", _runs(3), DEFAULT_GRADING, [FINDING], AbortReason.INTERRUPT
    )

    data = verdict_dict(verdict)

    assert (data["decision"], data["arm"], data["model"], data["effort"]) == (
        DECISION_KEEP,
        None,
        None,
        None,
    )


def test_the_decision_log_gate_excludes_the_same_agents():
    import ast

    from _repo_root import REPO_ROOT

    gate = (REPO_ROOT / "tests" / "docs" / "_model_effort_gate.py").read_text(
        encoding="utf-8"
    )
    assigned = next(
        node.value
        for node in ast.walk(ast.parse(gate))
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "RECALL_GAP_AGENTS" for t in node.targets)
    )

    assert ast.literal_eval(assigned) == set(RECALL_GAP_EXCLUDED_AGENTS)
