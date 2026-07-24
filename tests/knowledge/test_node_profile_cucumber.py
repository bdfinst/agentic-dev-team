"""Contract for the Cucumber.js BDD entry in the Node.js test stack
profile (epic #443, issue #439).

Ported from tests/knowledge/node_profile_cucumber_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

PROFILE = (
    REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "test-stack-profiles" / "node.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return PROFILE.read_text(encoding="utf-8")


def test_node_profile_names_cucumber_js_as_bdd_runner(text: str) -> None:
    assert re.search(r"Cucumber\.js", text, re.IGNORECASE)


def test_node_profile_bdd_entry_references_bdd_value_guide(text: str) -> None:
    assert "bdd-value-guide.md" in text


def test_node_profile_cross_references_bdd_frameworks(text: str) -> None:
    assert "bdd-frameworks.md" in text


def test_node_profile_clarifies_cucumber_and_vitest_jest_complementary(
    text: str,
) -> None:
    assert re.search(
        r"complement|not mutually exclusive|alongside|not.*alternativ",
        text,
        re.IGNORECASE,
    )


def test_node_profile_preserves_existing_tools(text: str) -> None:
    assert re.search(r"Vitest|Jest", text)
    assert "supertest" in text
    assert "MSW" in text
    assert "Pact" in text
    assert "Playwright" in text
