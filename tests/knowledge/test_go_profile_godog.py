"""Contract for the Godog BDD entry in the Go test stack profile (epic
#443, issue #437).

Ported from tests/knowledge/go_profile_godog_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = (
    REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "test-stack-profiles" / "go.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return PROFILE.read_text(encoding="utf-8")


def test_go_profile_names_godog_as_bdd_runner(text: str) -> None:
    assert "godog" in text.lower()


def test_go_profile_bdd_entry_references_bdd_value_guide(text: str) -> None:
    assert "bdd-value-guide.md" in text


def test_go_profile_cross_references_bdd_frameworks_for_install(text: str) -> None:
    assert "bdd-frameworks.md" in text


def test_go_profile_notes_godog_runs_inside_go_test_via_testsuite(
    text: str,
) -> None:
    assert re.search(r"godog\.TestSuite|inside .*go test|go test", text, re.IGNORECASE)


def test_go_profile_preserves_existing_tools(text: str) -> None:
    assert "httptest" in text
    assert "Testcontainers-go" in text
    assert "Pact-go" in text
    assert "testing" in text
