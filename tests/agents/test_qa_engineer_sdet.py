"""Senior SDET identity, routing, and behavior guards for qa-engineer.md.

Source: reports/improve-qa-agent.md

Ported from tests/agents/qa_engineer_sdet_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
QA = REPO_ROOT / "plugins" / "dev-team" / "agents" / "qa-engineer.md"
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"


@pytest.fixture(scope="module")
def qa_text() -> str:
    return QA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


def test_frontmatter_description_names_sdet_and_non_gatekeeping(qa_text: str) -> None:
    assert re.search(r"^description:.*SDET", qa_text, re.MULTILINE)
    assert re.search(r"^description:.*non-gatekeeping", qa_text, re.MULTILINE)


def test_identity_opens_as_senior_software_engineer_in_test(qa_text: str) -> None:
    assert "Senior Software Engineer in Test" in qa_text


def test_contains_request_routing_table(qa_text: str) -> None:
    assert re.search(r"^## Request routing", qa_text, re.MULTILINE)


def test_routing_table_references_four_primary_test_skills(qa_text: str) -> None:
    for skill in (
        "test-health",
        "cd-test-architecture",
        "test-design-advisor",
        "/test-design",
    ):
        assert skill in qa_text, f"missing: {skill}"


def test_encodes_minimum_cd_vocabulary_constraint(qa_text: str) -> None:
    assert "MinimumCD" in qa_text


def test_encodes_four_condition_e2e_discipline(qa_text: str) -> None:
    assert "e2e discipline" in qa_text.lower()


def test_drops_release_sign_off_gatekeeper_language(qa_text: str) -> None:
    assert "release sign-off" not in qa_text.lower()


def test_drops_quality_is_non_negotiable_gatekeeper_language(qa_text: str) -> None:
    assert "quality is non-negotiable" not in qa_text.lower()


def test_encodes_pyramid_is_a_cost_heuristic_framing(qa_text: str) -> None:
    assert "cost heuristic" in qa_text.lower()


def test_references_dora_metrics(qa_text: str) -> None:
    assert "DORA" in qa_text


def test_states_automation_code_is_production_code(qa_text: str) -> None:
    assert "Automation code is production code" in qa_text


def test_contains_three_amigos_and_example_mapping_shift_left_language(
    qa_text: str,
) -> None:
    assert "three-amigos" in qa_text
    assert "example mapping" in qa_text


def test_includes_example_dispatch_section(qa_text: str) -> None:
    assert "## Example dispatch" in qa_text


def test_orchestrator_routes_strategic_test_design_via_qa_engineer_to_test_health(
    orch_text: str,
) -> None:
    assert "Test-review request routing" in orch_text
    assert "qa-engineer" in orch_text
    # The strategic row mentions test-health under qa-engineer dispatch.
    assert re.search(r"qa-engineer.+test-health|test-health.+qa-engineer", orch_text)
