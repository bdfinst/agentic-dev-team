"""Tests for the skills-registry knowledge file extraction.

Ported from tests/repo/skills_registry_knowledge_tests.bats (issue #671).
"""

from __future__ import annotations

from pathlib import Path

SKILLS_REG = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "skills-registry.md"
)


def test_skills_registry_md_exists() -> None:
    assert SKILLS_REG.is_file()


def test_skills_registry_md_contains_the_build_command_with_its_file_path() -> None:
    assert "skills/build/SKILL.md" in SKILLS_REG.read_text()


def test_skills_registry_md_contains_the_test_improve_command() -> None:
    assert "skills/test-improve/SKILL.md" in SKILLS_REG.read_text()
