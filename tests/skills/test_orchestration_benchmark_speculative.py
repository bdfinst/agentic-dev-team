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
NEXT_H2 = "Repetitions and isolation"
PRECEDING_PARAGRAPH = "Reuse existing `/agent-eval` fixtures"

# Pre-registered thresholds. Change them here and in the skill, nowhere else.
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
    return lambda text: section_outside_code(
        text, rf"^## {name}$", boundary_pattern=r"^## "
    )


SECTIONS: dict[str, Callable[[str], str]] = {
    "case": _case,
    "report": _h2("Report"),
}


FACTS = [
    Fact(
        "class_is_complex_only",
        "case",
        literal_required=(
            "**Class.** `complex` only.",
            "a `complex` step of a plan built with `/build`",
        ),
    ),
    Fact(
        "pilot_is_a_candidates_1_run_excluded_from_the_runs",
        "case",
        literal_required=(
            "Run `/build --candidates 1` once on the fixture step.",
            "(`cost_meter.py report`)",
            "Exclude the pilot from the runs.",
        ),
        required=((r"cap at \d+ ?(×| times) its measured cost", False),),
    ),
    Fact(
        "arms_are_candidates_1_and_3_under_arm_b",
        "case",
        literal_required=(
            "Arm B's configuration",
            "`--candidates 1`",
            "`--candidates 3 --max-cost-usd <cap>`",
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
        "metrics_are_the_table_plus_speculative_rows_and_screening_spend",
        "case",
        literal_required=(
            "the Metrics table",
            "`### Speculative dispatch` rows",
            "rank inputs",
            "Cost column",
            "Screening spend = the run's measured step cost − the sum of the Cost column",
        ),
    ),
    Fact(
        "rule_needs_both_conditions",
        "case",
        literal_required=(
            "N = 3 earns its cost only when both conditions hold",
            "acceptance pass rate exceeds N = 1's",
            "median cost is at most",
            "N = 1's median plus the measured screening spend",
        ),
    ),
    Fact(
        "tie_is_inconclusive_and_extends_the_case_before_the_rule",
        "case",
        literal_required=("is inconclusive", "Extend the case to"),
        required=((r"Extend the case to \d+ runs before applying the rule", False),),
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
    # Thresholds: the only facts that carry numbers.
    Fact(
        "thresholds_cap_multiple",
        "case",
        required=((rf"cap at {CAP_MULTIPLE}{TIMES} its measured cost", False),),
    ),
    Fact(
        "thresholds_pass_rate_margin",
        "case",
        literal_required=(f"by at least {PASS_RATE_MARGIN} points",),
    ),
    Fact(
        "thresholds_cost_multiple",
        "case",
        required=((rf"at most {COST_MULTIPLE}{TIMES} N = 1's median", False),),
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
    task_matrix = section_outside_code(
        skill_text, rf"^## {TASK_MATRIX}$", boundary_pattern=r"^## "
    )
    assert headings_outside_code(task_matrix, 3)[-1] == CASE_HEADING


def test_the_case_follows_the_matrix_prose_and_precedes_the_next_h2(skill_text):
    task_matrix = section_outside_code(
        skill_text, rf"^## {TASK_MATRIX}$", boundary_pattern=r"^## "
    )
    assert collapsed(task_matrix).index(PRECEDING_PARAGRAPH) < collapsed(
        task_matrix
    ).index(CASE_HEADING)
    h2s = headings_outside_code(skill_text, 2)
    assert h2s[h2s.index(TASK_MATRIX) + 1] == NEXT_H2


def test_the_case_is_a_single_subsection_of_its_own(skill_text):
    assert headings_outside_code(skill_text, 3).count(CASE_HEADING) == 1
