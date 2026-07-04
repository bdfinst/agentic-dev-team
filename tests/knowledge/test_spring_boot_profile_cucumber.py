"""Contract for the Cucumber-JVM BDD entry in the Spring Boot test stack
profile (epic #443, issue #440).

Ported from tests/knowledge/spring_boot_profile_cucumber_tests.bats
(issue #675: bats -> pytest).
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
    / "spring-boot.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return PROFILE.read_text(encoding="utf-8")


def test_spring_profile_names_cucumber_jvm_as_bdd_runner(text: str) -> None:
    assert re.search(r"Cucumber-JVM", text, re.IGNORECASE)


def test_spring_profile_bdd_entry_references_bdd_value_guide(text: str) -> None:
    assert "bdd-value-guide.md" in text


def test_spring_profile_cross_references_bdd_frameworks(text: str) -> None:
    assert "bdd-frameworks.md" in text


def test_spring_profile_names_both_maven_and_gradle_wiring(text: str) -> None:
    assert re.search(r"Maven", text, re.IGNORECASE)
    assert re.search(r"Gradle", text, re.IGNORECASE)


def test_spring_profile_notes_cucumber_junit_platform_engine_wiring(
    text: str,
) -> None:
    assert "cucumber-junit-platform-engine" in text


def test_spring_profile_preserves_existing_tools(text: str) -> None:
    assert "JUnit 5" in text
    assert "SpringBootTest" in text
    assert "Testcontainers" in text
    assert re.search(r"Pact|Spring Cloud Contract", text)
