"""Contract for the test-smell-review agent's remedyFamily addition (#534).

Each of R2.2.a - R2.2.g in the plan maps to one test below.

Ported from tests/agents/test_smell_review_remedy_family_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-smell-review.md"


@pytest.fixture(scope="module")
def text() -> str:
    return AGENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(text: str) -> str:
    return text.replace("\n", " ")


def test_r2_2_a_schema_property_remedy_family_documented(text: str) -> None:
    # Find the "issues" JSON schema block and ensure remedyFamily appears in it.
    assert '"remedyFamily"' in text


def test_r2_2_b_allowed_remedy_family_values_named(text: str) -> None:
    assert "fixture-construction" in text
    assert "result-verification" in text
    assert "test-organization" in text
    assert "test-refactoring" in text
    # 'null' must also be explicitly documented as a valid value
    assert re.search(
        r"remedyFamily.*null|null.*remedyFamily|null.*when.*no.*family|"
        r"null.*for.*smell",
        text,
        re.IGNORECASE,
    )


def test_r2_2_c_both_remedy_family_and_suggested_fix_always_populated(
    text: str,
) -> None:
    assert re.search(
        r"both.*remedyFamily.*suggestedFix.*always populated|"
        r"always populated.*remedyFamily.*suggestedFix|"
        r"both fields.*always populated|both.*fields are always populated",
        text,
        re.IGNORECASE,
    )


def test_r2_2_d_suggested_fix_always_specific_pattern_not_family_slug(
    flat: str,
) -> None:
    # The AC11 guard: solo /code-review still gets a pattern-level
    # suggestedFix.
    assert re.search(r"suggestedFix.*specific.*(remedy )?pattern", flat, re.IGNORECASE)
    assert re.search(r"not.*family slug|not a family slug", flat, re.IGNORECASE)
    assert re.search(r"regardless of invocation", flat, re.IGNORECASE)


def test_r2_2_e_family_slug_must_appear_verbatim_in_message(text: str) -> None:
    # The grader-alignment guard: verdict.py:40 scans message+summary only.
    assert re.search(
        r"family slug.*verbatim.*message|verbatim.*message.*family slug|"
        r"slug.*must appear.*message|slug.*appear.*in.*message",
        text,
        re.IGNORECASE,
    )
    # Must call out that suggestedFix is NOT the field the grader scans.
    assert re.search(
        r"not.*suggestedFix|suggestedFix.*not.*scanned|verdict\.py|"
        r"grader.*scans.*message",
        text,
        re.IGNORECASE,
    )


def test_r2_2_f_scope_references_division_of_labor_section(text: str) -> None:
    assert "test-smell-review ↔ test-design-advisor — remedy division" in text


def test_r2_2_g_smell_to_family_mapping_table_exists(text: str) -> None:
    # The Detect (or nearby) section must include a mapping so the agent can
    # populate remedyFamily deterministically. At minimum the three non-null
    # mappings we've validated must appear near each other.
    assert re.search(r"smell.*family|family.*smell", text, re.IGNORECASE)
    # Sanity: at least two of the four family slugs appear inside a table row.
    assert re.search(
        r"\|.*(fixture-construction|result-verification|test-organization|"
        r"test-refactoring)",
        text,
    )
