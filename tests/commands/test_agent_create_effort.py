"""Tests for /agent-create and /agent-add — agents are authored in the effort
vocabulary (effort: low|medium|high), not the retired model/tier scheme.
Invalid bands are rejected with a legacy-token mapping.

Ported from tests/commands/agent_create_effort_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CREATE = (
    REPO_ROOT / "plugins" / "marketplace-dev" / "skills" / "agent-create" / "SKILL.md"
)
ADD = REPO_ROOT / "plugins" / "marketplace-dev" / "skills" / "agent-add" / "SKILL.md"


@pytest.fixture(scope="module")
def create_text() -> str:
    return CREATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def add_text() -> str:
    return ADD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# /agent-create authors effort bands
# ---------------------------------------------------------------------------


def test_agent_create_frontmatter_template_declares_effort_not_model(
    create_text: str,
) -> None:
    assert re.search(r"^effort: <band>", create_text, re.MULTILINE)
    # The frontmatter template no longer emits a model: line.
    assert not re.search(r"^model: <model>", create_text, re.MULTILINE)


def test_agent_create_documents_effort_flag(create_text: str) -> None:
    assert re.search(r"--effort", create_text)


def test_agent_create_lists_low_medium_high_as_valid_bands(create_text: str) -> None:
    assert "low" in create_text
    assert "medium" in create_text
    assert "high" in create_text


def test_agent_create_rejection_maps_legacy_token_to_band(create_text: str) -> None:
    # The rejection guidance maps legacy tokens → bands (e.g. frontier → high).
    assert re.search(r"frontier.*high", create_text, re.IGNORECASE)
    assert re.search(r"(small|haiku).*low", create_text, re.IGNORECASE)
    assert re.search(r"(mid|sonnet).*medium", create_text, re.IGNORECASE)


def test_agent_create_defaults_review_low_team_medium(create_text: str) -> None:
    assert re.search(r"effort.*\blow\b.*\bmedium\b", create_text)


def test_agent_create_body_template_omits_effort_line(create_text: str) -> None:
    # Single source of truth: effort lives in the frontmatter template only
    # (see the frontmatter test above). The body skeleton must not restate
    # it as an `Effort: <low|medium|high>` line, and must not use the
    # retired Model tier.
    assert not re.search(r"Effort: <low\|medium\|high>", create_text)
    assert "Model tier:" not in create_text


# ---------------------------------------------------------------------------
# /agent-add authors effort bands
# ---------------------------------------------------------------------------


def test_agent_add_documents_effort_flag_and_drops_tier(add_text: str) -> None:
    assert re.search(r"--effort low\|medium\|high", add_text)
    assert "--tier" not in add_text
