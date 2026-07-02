"""Verifies that plugins/dev-team/agents/test-smell-review.md is wired for
stack-aware reference loading per plans/stack-aware-reference-loading.md
(Slice 1, issue #524).

Pattern source: plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62.

Ported from tests/bats/stack-aware-test-smell-review.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _stack_aware_helpers import BANNED_TOKENS_RE, body_only

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-smell-review.md"


@pytest.fixture(scope="module")
def text() -> str:
    return TARGET.read_text(encoding="utf-8")


def test_names_test_stack_profiles_as_load_on_match_knowledge_source(
    text: str,
) -> None:
    assert text.count("test-stack-profiles") >= 1


def test_cross_references_test_design_advisor_as_pattern_source(
    text: str,
) -> None:
    assert text.count("test-design-advisor") >= 1


def test_lists_all_six_manifest_tokens_for_stack_detection(text: str) -> None:
    assert "package.json" in text
    assert re.search(r"\.csproj", text)
    assert re.search(r"pom\.xml|build\.gradle", text)
    assert "go.mod" in text
    assert re.search(r"pyproject\.toml|requirements\.txt", text)
    assert "htmx" in text


def test_documents_missing_profile_fallback_phrase(text: str) -> None:
    assert text.count("name the missing profile") >= 1


def test_body_contains_no_language_specific_tokens(text: str) -> None:
    stripped = body_only(text)
    assert not BANNED_TOKENS_RE.search(stripped)
