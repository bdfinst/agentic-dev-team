"""Content contract for the BDD value-decision guide (epic #443, issue
#435). A reusable rubric for when BDD/Gherkin adds value vs. ceremony
overhead.

Ported from tests/knowledge/bdd_value_guide_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "references"
    / "bdd-value-guide.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_bdd_value_guide_md_exists() -> None:
    assert GUIDE.is_file()


def test_rubric_covers_all_five_decision_questions(text: str) -> None:
    # Five yes/no signals: stakeholders, business-domain, collaborative
    # authoring, living-documentation, existing Gherkin.
    assert "stakeholder" in text.lower()
    assert "business domain" in text.lower()
    assert re.search(r"three.amigos|collaborative", text, re.IGNORECASE)
    assert re.search(r"living.documentation", text, re.IGNORECASE)
    assert "existing gherkin" in text.lower()


def test_recommendation_mapping_defines_all_three_binding_modes(text: str) -> None:
    assert "bdd-runner" in text
    assert "xunit-with-annotations" in text
    # the third mode is plain xunit / none
    assert re.search(r"`none`|\bnone\b", text)


def test_recommendation_mapping_is_score_banded(text: str) -> None:
    assert re.search(r"≥ ?3|>= ?3|3\+ yes", text)
    assert re.search(r"1.2 yes|1.{0,3}2", text)
    assert re.search(r"0 yes", text)


def test_guide_has_overkill_and_worth_it_sections(text: str) -> None:
    assert re.search(r"overkill|almost always overkill", text, re.IGNORECASE)
    assert re.search(r"worth it|almost always worth", text, re.IGNORECASE)


def test_overkill_guidance_names_concrete_cases(text: str) -> None:
    assert re.search(r"utilit|data mapper|infrastructure adapter", text, re.IGNORECASE)
    assert re.search(r"spike|prototype|short-lived", text, re.IGNORECASE)


def test_worth_it_guidance_names_concrete_cases(text: str) -> None:
    assert re.search(r"regulated|payments|healthcare|compliance", text, re.IGNORECASE)
    assert re.search(r"shared.language|misaligned", text, re.IGNORECASE)
