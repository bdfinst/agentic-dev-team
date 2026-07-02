"""Tests for plugins/dev-team/CLAUDE.md size + pointer discipline.

Ported from tests/repo/claude_md_size_tests.bats (#673).
"""

from __future__ import annotations

import re
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "CLAUDE.md"


def test_claude_md_is_under_5000_characters() -> None:
    text = CLAUDE.read_text()
    assert len(text) < 5001, f"CLAUDE.md is {len(text)} chars, must be under 5001"


def test_claude_md_references_skills_registry() -> None:
    assert "knowledge/skills-registry.md" in CLAUDE.read_text()


def test_claude_md_references_request_processing_flow() -> None:
    assert "knowledge/request-processing-flow.md" in CLAUDE.read_text()


def test_claude_md_does_not_contain_full_skills_registry_table() -> None:
    # The full table has 45+ rows; if the pointer replaced it, only 2 rows max.
    count = len(re.findall(r"\| `/", CLAUDE.read_text()))
    assert count <= 2
