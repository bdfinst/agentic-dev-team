"""Content contract for the per-language BDD wire-in reference (epic #443,
issue #436). One section per language with the minimal steps to install
and run a BDD runner.

Ported from tests/knowledge/bdd_frameworks_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

REF = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "test-stack-profiles"
    / "bdd-frameworks.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return REF.read_text(encoding="utf-8")


def test_bdd_frameworks_md_exists() -> None:
    assert REF.is_file()


def test_covers_all_four_languages_five_sections(text: str) -> None:
    assert re.search(r"Cucumber\.js", text, re.IGNORECASE)  # JS/TS
    assert re.search(r"Cucumber-JVM", text, re.IGNORECASE)  # Java
    assert re.search(r"\bMaven\b", text, re.IGNORECASE)
    assert re.search(r"\bGradle\b", text, re.IGNORECASE)
    assert re.search(r"Reqnroll", text, re.IGNORECASE)  # C#
    assert re.search(r"Godog", text, re.IGNORECASE)  # Go


def test_csharp_uses_reqnroll_not_specflow(text: str) -> None:
    assert "reqnroll" in text.lower()
    # SpecFlow may be named only to say 'use Reqnroll instead'; must not be
    # the recommendation.
    assert not re.search(
        r"use SpecFlow|recommend SpecFlow|SpecFlow\.xUnit", text, re.IGNORECASE
    )


def test_each_language_documents_install_command(text: str) -> None:
    assert re.search(r"npm install .*@cucumber/cucumber", text)
    assert "cucumber-junit-platform-engine" in text
    assert "dotnet add package Reqnroll" in text
    assert re.search(r"go get .*godog", text)


def test_documents_directory_layout(text: str) -> None:
    assert "features/" in text
    assert re.search(
        r"step.def|step_definitions|support/|src/test/resources/features",
        text,
        re.IGNORECASE,
    )


def test_documents_per_language_pending_step_stub_shape(text: str) -> None:
    assert "this.pending()" in text  # Cucumber.js
    assert "PendingException" in text  # Cucumber-JVM
    assert "StepIsPending()" in text  # Reqnroll
    assert "godog.ErrPending" in text  # Godog


def test_documents_how_to_run_and_ci_junit_xml_note(text: str) -> None:
    assert re.search(r"run", text, re.IGNORECASE)
    assert re.search(r"JUnit XML|junit|CI", text, re.IGNORECASE)
