"""#225 — /issues-from-plan must create a spec parent + slice children with
DAG-derived dependency links, and handle a missing spec and partial failure.
Documentation gate.

Ported from tests/commands/issues_from_plan_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "issues-from-plan" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_exists() -> None:
    assert SKILL.is_file()


def test_derives_dependency_links_from_dag_not_file_order(text: str) -> None:
    assert "issue-deps.sh" in text
    assert "not file order" in text.lower()


def test_creates_parent_issue_from_spec(text: str) -> None:
    assert "parent" in text.lower()
    assert "spec" in text.lower()


def test_creates_slice_children_linked_to_parent(text: str) -> None:
    assert "Part of #" in text


def test_reports_missing_spec_and_creates_no_parent(text: str) -> None:
    assert "no associated spec" in text.lower()
    assert "create no parent" in text.lower()


def test_handles_partial_creation_failure_without_orphaned_state(
    text: str,
) -> None:
    assert "partial-failure" in text.lower()
    assert "were created" in text.lower()
