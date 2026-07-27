"""Contract for eval fixtures that grade test-smell-review output. Each
fixture MUST require the appropriate remedy-family slug via mustMention so
verdict.py:40 (which concatenates issue.message + summary and scans for
mustMention keywords in prose) actually enforces the family cite (#534).

Mapping is derived from knowledge/test-smells.md:
  Assertion Roulette      → result-verification (Expected Object / Custom Assertion)
  Mystery Guest           → fixture-construction (Creation Method / Minimal Fixture)
  Overspecified Mocks     → result-verification (state verification, not behavior)
                            — plan originally proposed test-organization; Step 2.1
                            confirmed the smell's remedy row in test-smells.md
                            lives in result-verification.md's state-vs-behavior
                            section, so we cite that family instead.
  Clean Doubles (control) → no smell → no family cite added

Ported from tests/knowledge/test_smell_review_eval_fixtures_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import json

from _repo_root import REPO_ROOT

EVALS = REPO_ROOT / "evals" / "expected"

FAMILY_SLUGS = (
    "fixture-construction",
    "result-verification",
    "test-organization",
    "test-refactoring",
)


def _must_mention(fixture: str) -> list:
    data = json.loads((EVALS / fixture).read_text(encoding="utf-8"))
    return data["agents"]["test-smell-review"]["mustMention"]


def _require_must_mention(fixture: str, *keywords: str) -> None:
    must_mention = _must_mention(fixture)
    for kw in keywords:
        assert kw in must_mention, f"{fixture}: missing mustMention {kw!r}"


def test_assertion_roulette_fixture_requires_result_verification() -> None:
    _require_must_mention("test-assertion-roulette.test.json", "result-verification")


def test_mystery_guest_fixture_requires_fixture_construction() -> None:
    _require_must_mention("test-mystery-guest.test.json", "fixture-construction")


def test_overspecified_mocks_fixture_requires_result_verification() -> None:
    _require_must_mention("test-overspecified-mocks.test.json", "result-verification")


def test_clean_doubles_fixture_must_not_add_remedy_family_must_mention() -> None:
    # Control fixture — expects no smell, so no family cite should be
    # required.
    must_mention = _must_mention("test-clean-doubles.test.json")
    for family in FAMILY_SLUGS:
        assert family not in must_mention, f"unexpected mustMention: {family}"


def test_internal_collaborator_mock_fixture_requires_component_test_patterns_citation() -> (
    None
):
    # Mocking an internal/same-component collaborator is a boundary-selection
    # misuse, not one of the four remedyFamily slugs — its citation contract
    # points at component-test-patterns.md instead.
    _require_must_mention(
        "test-internal-collaborator-mock.test.json", "component-test-patterns"
    )
