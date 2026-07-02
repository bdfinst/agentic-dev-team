"""Tests for agents/session-analysis.md schema compliance additions.

Ported from tests/agents/session_analysis_schema_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "session-analysis.md"


@pytest.fixture(scope="module")
def text() -> str:
    return AGENT.read_text(encoding="utf-8")


def test_has_json_output_schema_with_status_field(text: str) -> None:
    assert '"status": "pass|warn|fail|skip"' in text


def test_has_severity_definitions_covering_error_warning_suggestion(
    text: str,
) -> None:
    assert "Severity:" in text
    assert "error" in text
    assert "warning" in text
    assert "suggestion" in text


def test_has_skip_section(text: str) -> None:
    assert "## Skip" in text


def test_has_context_needs_full_file_line(text: str) -> None:
    assert "Context needs: full-file" in text
