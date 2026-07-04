"""Contract for the Reqnroll BDD entry in the .NET test stack profile
(epic #443, issue #438).

Ported from tests/knowledge/dotnet_profile_reqnroll_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "test-stack-profiles"
    / "dotnet.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return PROFILE.read_text(encoding="utf-8")


def test_dotnet_profile_names_reqnroll_as_bdd_runner(text: str) -> None:
    assert "reqnroll" in text.lower()


def test_dotnet_profile_bdd_entry_references_bdd_value_guide(text: str) -> None:
    assert "bdd-value-guide.md" in text


def test_dotnet_profile_cross_references_bdd_frameworks(text: str) -> None:
    assert "bdd-frameworks.md" in text


def test_dotnet_profile_prefers_reqnroll_over_specflow_with_license_rationale(
    text: str,
) -> None:
    assert "reqnroll" in text.lower()
    assert re.search(r"SpecFlow", text, re.IGNORECASE)
    assert re.search(r"MIT|license|licen", text, re.IGNORECASE)


def test_dotnet_profile_preserves_existing_tools(text: str) -> None:
    assert "xUnit" in text
    assert "WebApplicationFactory" in text
    assert "Testcontainers-dotnet" in text
    assert "PactNet" in text
    assert "Playwright" in text
