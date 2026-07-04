"""Vocabulary, pyramid-framing, and E2E-justification guards for the
test-design-advisor / test-design / cd-test-architecture skills.

Source: reports/improve-test-design-skills.md

Ported from tests/docs/test_design_skill_vocabulary_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADVISOR = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design-advisor" / "SKILL.md"
)
DESIGN = REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design" / "SKILL.md"
CDARCH = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "cd-test-architecture" / "SKILL.md"
)
SMELL = REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-smell-review.md"
DOTNET_EXAMPLE = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "test-matrix-examples"
    / "dotnet-grpc-fronting-api.md"
)

TARGET_SHAPE_ALLOWLIST = re.compile(
    r"not a target shape|not target shape|no target shape|NOT.*target shape|"
    r"do not.*target shape|never.*target shape|cost heuristic.*not.*target shape|"
    r"drop.*target shape|forbid.*target shape|No target-shape|no target-shape"
)


def _narrow_integration_offenders(text: str) -> list[str]:
    offenders = []
    for i, line in enumerate(text.splitlines(), start=1):
        if "narrow integration" in line and "contract test" not in line:
            offenders.append(f"{i}: {line}")
    return offenders


@pytest.fixture(scope="module")
def advisor_text() -> str:
    return ADVISOR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def design_text() -> str:
    return DESIGN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cdarch_text() -> str:
    return CDARCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def smell_text() -> str:
    return SMELL.read_text(encoding="utf-8")


def test_advisor_narrow_integration_only_with_contract_test_gloss(
    advisor_text: str,
) -> None:
    assert not _narrow_integration_offenders(advisor_text)


def test_design_narrow_integration_only_with_contract_test_gloss(
    design_text: str,
) -> None:
    assert not _narrow_integration_offenders(design_text)


def test_cdarch_narrow_integration_only_with_contract_test_gloss(
    cdarch_text: str,
) -> None:
    assert not _narrow_integration_offenders(cdarch_text)


def test_smell_narrow_integration_only_with_contract_test_gloss(
    smell_text: str,
) -> None:
    assert not _narrow_integration_offenders(smell_text)


def test_advisor_target_shape_only_in_prohibiting_context(advisor_text: str) -> None:
    # The pyramid-is-a-cost-heuristic constraint mentions "target shape"
    # only to forbid it. Any other usage (a coaching recommendation toward
    # a silhouette) is a regression.
    offenders = [
        f"{i}: {line}"
        for i, line in enumerate(advisor_text.splitlines(), start=1)
        if "target shape" in line and not TARGET_SHAPE_ALLOWLIST.search(line)
    ]
    assert not offenders


def test_advisor_target_count_phrase_only_in_prohibiting_context(
    advisor_text: str,
) -> None:
    # Catches phrases like 'target test count(s) per layer', 'per-layer
    # target count', 'target count per layer'. The pyramid-is-a-cost-
    # heuristic constraint mentions them only to forbid them — a
    # prohibiting verb ("not", "no", "never", "do not", "forbid", "drop")
    # must appear on the same line as the trigger phrase.
    trigger_re = re.compile(
        r"target test \*?counts?\*? per layer|target count per layer|"
        r"per-layer target count|target counts per layer",
        re.IGNORECASE,
    )
    offenders = [
        f"{i}: {line}"
        for i, line in enumerate(advisor_text.splitlines(), start=1)
        if trigger_re.search(line)
        and not re.search(r"not|never|forbid|drop", line, re.IGNORECASE)
    ]
    assert not offenders


def test_advisor_encodes_pyramid_is_a_cost_heuristic_constraint(
    advisor_text: str,
) -> None:
    assert "cost heuristic" in advisor_text


def test_advisor_encodes_e2e_justification_gate(advisor_text: str) -> None:
    assert "E2E justification" in advisor_text


def test_advisor_encodes_minimum_cd_vocabulary_constraint(advisor_text: str) -> None:
    assert "MinimumCD" in advisor_text


def test_advisor_placement_table_uses_two_direction_why_this_layer(
    advisor_text: str,
) -> None:
    assert "Why this layer (not the one above or below)" in advisor_text


def test_design_forwards_e2e_justification_gate(design_text: str) -> None:
    assert "e2e justification" in design_text.lower()


def test_design_forbids_target_shape_rollups(design_text: str) -> None:
    assert "target shape" not in design_text.lower()


def test_cdarch_encodes_e2e_justification_gate(cdarch_text: str) -> None:
    assert "e2e justification" in cdarch_text.lower()


def test_cdarch_encodes_pyramid_is_a_cost_heuristic_constraint(
    cdarch_text: str,
) -> None:
    assert "cost heuristic" in cdarch_text.lower()


def test_dotnet_grpc_worked_example_exists() -> None:
    assert DOTNET_EXAMPLE.is_file()


def test_dotnet_grpc_worked_example_uses_minimum_cd_layer_names_and_gates_e2e() -> None:
    text = DOTNET_EXAMPLE.read_text(encoding="utf-8")
    assert "contract" in text.lower()
    assert "e2e justification" in text.lower()
