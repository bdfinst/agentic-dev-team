"""#813 — the experiment line's positioning lands in the shipped skills.

`docs/experiments/RECOMMENDATIONS.md` is canonical: /specs's value is human
ambiguity resolution before build, not edge-case synthesis (Rec 1 /
Experiment 03); the review-agent panel — not coverage or mutation — is the
quality signal that separates workflows (Rec 5); and /plan cites the
folded-in Experiment 01 report instead of the retired consolidated report.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

PLAN_SKILL = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text()
SPECS_SKILL = (PLUGIN_ROOT / "skills" / "specs" / "SKILL.md").read_text()
CODE_REVIEW_SKILL = (PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text()
REVIEW_RUBRIC = (PLUGIN_ROOT / "knowledge" / "review-rubric.md").read_text()


def _flat(text: str) -> str:
    """Whitespace-normalized text so assertions survive line wrapping."""
    return re.sub(r"\s+", " ", text)


class TestPlanCitesTheFoldedInExperimentReport:
    def test_plan_cites_experiment_01_final_results(self) -> None:
        assert "docs/experiments/01-final-results.md" in PLAN_SKILL, (
            "/plan must cite the folded-in Experiment 01 final results"
        )

    def test_no_file_outside_the_experiments_archive_cites_the_retired_report(
        self,
    ) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        offenders = []
        for rel in tracked:
            if rel.startswith("docs/experiments/"):
                continue  # the experiments docs are the historical record
            if rel == "tests/repo/test_recommendations_positioning.py":
                continue  # this sensor names the retired report on purpose
            path = REPO_ROOT / rel
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "tdd-vs-test-after-consolidated-report" in content:
                offenders.append(rel)
        assert offenders == [], (
            "retired report referenced outside docs/experiments/: "
            f"{offenders}"
        )


class TestSpecsStatesWhatItIsFor:
    def test_value_is_human_ambiguity_resolution_before_build(self) -> None:
        flat = _flat(SPECS_SKILL)
        assert re.search(
            r"resolv\w* ambigu\w* with a human before (any )?(build|implementation)",
            flat,
            re.IGNORECASE,
        ), "/specs must state its value: ambiguity resolution with a human before build"

    def test_states_it_does_not_outperform_failing_test_discipline_on_edge_cases(
        self,
    ) -> None:
        flat = _flat(SPECS_SKILL)
        assert re.search(
            r"does not out-?perform .{0,80}failing-test discipline",
            flat,
            re.IGNORECASE,
        ), "/specs must state it does not out-perform failing-test discipline at edge cases"
        assert "Experiment 03" in SPECS_SKILL

    def test_cites_the_recommendations_synthesis(self) -> None:
        assert "docs/experiments/RECOMMENDATIONS.md" in SPECS_SKILL


class TestCodeReviewNamesThePrimaryQualityGate:
    def test_skill_names_the_review_agent_panel_the_primary_quality_gate(self) -> None:
        flat = _flat(CODE_REVIEW_SKILL)
        assert re.search(
            r"review[- ]agent panel is the (plugin's )?primary quality gate",
            flat,
            re.IGNORECASE,
        ), "/code-review must name the review-agent panel the primary quality gate"

    def test_skill_positions_coverage_and_mutation_as_saturating(self) -> None:
        flat = _flat(CODE_REVIEW_SKILL)
        assert re.search(r"coverage and mutation .{0,60}saturat", flat, re.IGNORECASE)
        assert re.search(
            r"never.{0,60}rank.{0,40}workflow", flat, re.IGNORECASE
        ), "coverage/mutation must never rank workflow quality"

    def test_skill_cites_the_recommendations_synthesis(self) -> None:
        assert "docs/experiments/RECOMMENDATIONS.md" in CODE_REVIEW_SKILL

    def test_rubric_repeats_the_positioning_for_scoring_consumers(self) -> None:
        flat = _flat(REVIEW_RUBRIC)
        assert re.search(
            r"review[- ]agent panel is the (plugin's )?primary quality gate",
            flat,
            re.IGNORECASE,
        )
        assert re.search(r"saturat", flat, re.IGNORECASE)
        assert re.search(r"Farley", REVIEW_RUBRIC), (
            "the rubric must position the informational Farley Score alongside "
            "coverage/mutation as a saturating metric"
        )
        assert re.search(
            r"higher mutation score .{0,80}(never|must not)",
            flat,
            re.IGNORECASE,
        ), "a higher mutation score must never be evidence a costlier workflow is better"
