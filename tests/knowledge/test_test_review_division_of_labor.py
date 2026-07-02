"""Content contract for knowledge/test-review-division-of-labor.md,
covering BOTH agent pairs:

  1. test-review ↔ test-smell-review (pre-existing)
  2. test-smell-review ↔ test-design-advisor (added for #534)

Owner-assignment correctness (which agent owns which column) is a
semantic property; the assertions below verify structural presence only.
Semantic correctness is verified by plan-review reading, not by grep.

Ported from tests/knowledge/test_review_division_of_labor_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "test-review-division-of-labor.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_test_review_division_of_labor_md_exists() -> None:
    assert DOC.is_file()


# --- Pre-existing pair (regression guards) ---


def test_pre_existing_the_two_roles_section_survives(text: str) -> None:
    assert "## The two roles" in text


def test_pre_existing_shared_signals_section_survives(text: str) -> None:
    assert "## Shared signals — who reports when both run" in text


def test_pre_existing_the_rule_in_one_line_section_survives(text: str) -> None:
    assert "## The rule in one line" in text


# --- New pair: test-smell-review ↔ test-design-advisor (#534) ---


def test_smell_review_advisor_remedy_division_section_heading_exists(
    text: str,
) -> None:
    assert "## test-smell-review ↔ test-design-advisor — remedy division" in text


def test_remedy_division_section_documents_smell_name_location_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Smell name.*location", text)


def test_remedy_division_section_documents_severity_confidence_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Severity.*confidence", text, re.IGNORECASE)


def test_remedy_division_section_documents_remedy_family_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Remedy family", text, re.IGNORECASE)


def test_remedy_division_section_documents_specific_remedy_pattern_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Specific remedy pattern", text, re.IGNORECASE)


def test_remedy_division_section_documents_refactor_sequence_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Refactor sequence", text, re.IGNORECASE)


def test_remedy_division_section_documents_forward_design_placement_column(
    text: str,
) -> None:
    assert re.search(r"\|\s*Forward-design placement", text, re.IGNORECASE)


def test_remedy_division_section_states_under_test_design_rule(text: str) -> None:
    assert re.search(
        r"under.*/test-design.*advisor.*owns|advisor.*owns.*remedy.*pattern",
        text,
        re.IGNORECASE,
    )


def test_remedy_division_section_states_solo_invocation_rule(text: str) -> None:
    # The rule spans several lines: "runs solo... it fills the whole row" —
    # check both phrases exist in the file (the doc-lint gate suffices for
    # adjacency).
    assert re.search(r"\bruns solo\b", text, re.IGNORECASE)
    assert re.search(r"fills the whole row", text, re.IGNORECASE)
