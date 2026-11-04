"""Doc-shape contract for the speculative dispatch case in
orchestration-benchmark/SKILL.md (plan Slice 4, Step 4.3).

The case is the last H3 of `## Task matrix`. These tests pin its structure:
position, the arms, the pilot, the repetition rules it reuses, the metrics,
the pre-registered rule, and the report subsection.

Threshold tolerance: the pre-registered numbers can change without breaking
the structural facts. Every threshold lives in one small group of facts named
`thresholds_*`, built from the constants below. Every other fact and test is
free of those numbers. The `3` in `--candidates 3` names an arm, not a
threshold, so the arm fact still pins it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    Fact,
    assert_fact,
    collapsed,
    headings_outside_code,
    section_outside_code,
)

SKILL = PLUGIN_ROOT / "skills" / "orchestration-benchmark" / "SKILL.md"

CASE_HEADING = "Speculative dispatch case (#2273)"
TASK_MATRIX = "Task matrix"
PRECEDING_PARAGRAPH = "Reuse existing `/agent-eval` fixtures"

# Pre-registered thresholds. Change them here and in the skill, nowhere else.
RUNS_MINIMUM = 5
CAP_MULTIPLE = 5
PASS_RATE_MARGIN = 20
COST_MULTIPLE = 3
NOISE_RUNS_WORD = "five"
EXTENDED_RUNS = 10

TIMES = r"(×| times)"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _case(text: str) -> str:
    """The case subsection, up to the next heading of any level 1-3."""
    return section_outside_code(
        text, rf"^### {re.escape(CASE_HEADING)}$", boundary_pattern=r"^#{1,3} "
    )


def _h2(name: str) -> Callable[[str], str]:
    """The H2 section whose heading matches the regex `name`, in full."""
    return lambda text: section_outside_code(
        text, rf"^## {name}$", boundary_pattern=r"^## "
    )


SECTIONS: dict[str, Callable[[str], str]] = {
    "case": _case,
    "task_matrix": _h2(TASK_MATRIX),
    "decision_rule": _h2(r"Decision rule \(pre-registered.*"),
    "report": _h2("Report"),
}


FACTS = [
    Fact(
        "class_is_complex_only",
        "case",
        literal_required=("**Class.** `complex` only.",),
    ),
    Fact(
        "class_fixture_is_a_plan_fixture_with_one_complex_step_and_eval_assertions",
        "case",
        literal_required=(
            (
                "The fixture is a plan fixture with one `complex` step and its "
                "eval assertions under `evals/fixtures/`."
            ),
        ),
    ),
    Fact(
        "class_fixture_is_added_when_the_case_first_runs_and_run_with_build",
        "case",
        literal_required=(
            "Add it when the case first runs (none exists).",
            "Run that step with `/build`.",
        ),
    ),
    Fact(
        "pilot_is_a_candidates_1_run_excluded_from_the_runs",
        "case",
        literal_required=(
            "Run `/build --candidates 1` once on the fixture step.",
            "Exclude the pilot from the runs.",
        ),
        required=((r"cap at \d+ ?(×| times) the pilot's step cost", False),),
    ),
    Fact(
        "pilot_step_cost_is_the_cost_meter_delta_across_the_step",
        "case",
        literal_required=(
            (
                "Step cost is the cost-meter delta across the step: "
                "`cost_meter.py report` before the step and after its "
                "checkpoint passes."
            ),
        ),
    ),
    Fact(
        "arms_are_two_variants_of_arm_b_named_by_candidate_count",
        "case",
        literal_required=(
            "Two variants of Arm B, named by candidate count",
            "N = 1 (`--candidates 1`)",
            "N = 3 (`--candidates 3 --max-cost-usd <cap>`)",
        ),
    ),
    Fact(
        "repetition_rules_are_reused_unchanged_and_linked",
        "case",
        literal_required=(
            "(`--runs`)",
            "interleaved order (1, 3, 1, 3, …)",
            "median + spread",
            "model-pinning",
            "[Repetitions and isolation](#repetitions-and-isolation)",
            "apply unchanged",
        ),
    ),
    Fact(
        "runs_execute_one_at_a_time",
        "case",
        literal_required=(
            "Runs execute one at a time; no run overlaps another run or the pilot.",
        ),
    ),
    Fact(
        "metrics_are_the_table_plus_the_plan_summary_speculative_rows",
        "case",
        literal_required=(
            (
                "Use the Metrics table plus the `Speculative dispatch` rows of "
                "the plan's `## Plan Review Summary`."
            ),
            "the kept candidate's rank inputs and the `Cost (USD)` column",
        ),
    ),
    Fact(
        "screening_spend_is_all_step_cost_outside_the_cap",
        "case",
        literal_required=(
            (
                "Screening spend is all step cost outside the cap: suite runs, "
                "screening, and the winner's inline checkpoint."
            ),
        ),
    ),
    Fact(
        "screening_spend_equals_the_step_cost_minus_the_cost_column",
        "case",
        literal_required=(
            (
                "It equals the run's measured step cost − the sum of the "
                "`Cost (USD)` column."
            ),
        ),
    ),
    Fact(
        "rule_needs_both_conditions",
        "case",
        literal_required=(
            "N = 3 earns its cost only when both conditions hold",
            "Its acceptance pass rate (the Quality metric) exceeds N = 1's",
            "Its median cost is at most",
        ),
    ),
    Fact(
        "cost_condition_adds_the_median_screening_spend_of_the_n_3_runs",
        "case",
        literal_required=("plus the median screening spend of the N = 3 runs.",),
    ),
    Fact(
        "tie_is_inconclusive_and_extends_the_case_before_the_rule",
        "case",
        literal_required=("is inconclusive", "Extend the case to"),
        required=(
            (r"Extend the case to \d+ runs, then apply the rule as written", False),
        ),
    ),
    Fact(
        "failing_rule_retains_n_1_and_updates_the_experimental_note",
        "case",
        literal_required=(
            "N = 1 is retained",
            "follow-up PR",
            "experimental note",
            "`--candidates` bullet",
            "`skills/build/SKILL.md`, Parse Arguments",
        ),
    ),
    Fact(
        "report_subsection_is_named_under_per_class_results",
        "case",
        literal_required=(
            "one subsection `Speculative dispatch` under **Per-class results**",
        ),
    ),
    Fact(
        "decision_rule_item_4_applies_the_case_rule_and_links_it",
        "decision_rule",
        literal_required=(
            "4. **Speculative dispatch case:** apply the rule in",
            "[Speculative dispatch case (#2273)](#speculative-dispatch-case-2273).",
        ),
    ),
    Fact(
        "report_item_1_says_the_case_adds_the_subsection",
        "report",
        required=(
            (
                (
                    r"\*\*Per-class results\*\*.*speculative dispatch case adds"
                    r".*`Speculative dispatch` subsection.*\*\*Crossover threshold\*\*"
                ),
                True,
            ),
        ),
    ),
    Fact(
        "report_item_3_routes_the_case_verdict_to_its_per_class_subsection",
        "report",
        required=(
            (
                (
                    r"\*\*Decision-rule outcomes\*\*.*earn/retain verdict goes in "
                    r"its Per-class `Speculative dispatch` subsection"
                    r".*\*\*Threats to validity\*\*"
                ),
                True,
            ),
        ),
    ),
    # Thresholds: the only facts that carry numbers.
    Fact(
        "thresholds_runs_minimum",
        "case",
        literal_required=(f"The ≥ {RUNS_MINIMUM} runs (`--runs`)",),
    ),
    Fact(
        "thresholds_cap_multiple",
        "case",
        required=((rf"cap at {CAP_MULTIPLE}{TIMES} the pilot's step cost", False),),
    ),
    Fact(
        "thresholds_pass_rate_margin",
        "case",
        literal_required=(f"by at least {PASS_RATE_MARGIN} points",),
    ),
    Fact(
        "thresholds_cost_multiple_groups_the_screening_spend_outside_the_multiple",
        "case",
        required=(
            (
                (
                    rf"at most {COST_MULTIPLE}{TIMES} N = 1's median, "
                    r"plus the median screening spend"
                ),
                False,
            ),
        ),
    ),
    Fact(
        "thresholds_noise_below_the_margin",
        "case",
        literal_required=(
            f"under {PASS_RATE_MARGIN} points is noise at {NOISE_RUNS_WORD} runs",
        ),
    ),
    Fact(
        "thresholds_tie_is_exactly_the_margin_and_extends_to_more_runs",
        "case",
        literal_required=(
            f"exactly {PASS_RATE_MARGIN} points",
            f"Extend the case to {EXTENDED_RUNS} runs",
        ),
    ),
]


@pytest.mark.parametrize("fact", FACTS, ids=lambda f: f.id)
def test_case_states(skill_text, fact):
    assert_fact(SECTIONS, skill_text, fact)


def test_task_matrix_ends_with_the_case_subsection(skill_text):
    task_matrix = SECTIONS["task_matrix"](skill_text)
    assert headings_outside_code(task_matrix, 3)[-1] == CASE_HEADING


def test_the_case_follows_the_matrix_prose(skill_text):
    task_matrix = collapsed(SECTIONS["task_matrix"](skill_text))
    assert task_matrix.index(PRECEDING_PARAGRAPH) < task_matrix.index(CASE_HEADING)


def test_the_case_is_a_single_subsection_of_its_own(skill_text):
    assert headings_outside_code(skill_text, 3).count(CASE_HEADING) == 1


def test_the_decision_rule_link_targets_the_case_heading(skill_text):
    slug = re.sub(r"[^\w\s-]", "", CASE_HEADING.lower()).replace(" ", "-")
    assert f"(#{slug})" in SECTIONS["decision_rule"](skill_text)
