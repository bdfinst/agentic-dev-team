"""Tests for /agent-create and /agent-add — agents are authored with the
native Claude Code sub-agent contract (model:/effort:), not the retired
effort-band-only scheme (ADR 0026 supersedes ADR 0008). model/effort are
never silently defaulted — a value is suggested and the user confirms it.

Ported from tests/commands/agent_create_effort_tests.bats (issue #675:
bats -> pytest); rewritten for epic #1284's native-contract migration
(issue #1289).
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
# /agent-create authors the native model:/effort: contract
# ---------------------------------------------------------------------------


def test_agent_create_frontmatter_template_declares_model_and_effort(
    create_text: str,
) -> None:
    assert re.search(r"^model: <alias\|full-id\|inherit>", create_text, re.MULTILINE)
    assert re.search(r"^effort: <level>", create_text, re.MULTILINE)


def test_agent_create_documents_model_and_effort_flags(create_text: str) -> None:
    assert re.search(r"--model", create_text)
    assert re.search(r"--effort", create_text)


def test_agent_create_lists_native_model_and_effort_enums(create_text: str) -> None:
    for value in ("sonnet", "opus", "haiku", "fable", "inherit"):
        assert value in create_text
    for value in ("low", "medium", "high", "xhigh", "max"):
        assert value in create_text


def test_agent_create_documents_optional_native_fields(create_text: str) -> None:
    for flag in (
        "--memory",
        "--isolation",
        "--color",
        "--max-turns",
        "--background",
        "--skills",
    ):
        assert flag in create_text, f"{flag} not documented"


def test_agent_create_rejection_validates_against_contract(create_text: str) -> None:
    assert "agent-contract.json" in create_text
    assert re.search(
        r"invalid.*--model.*--effort|invalid.*--effort.*--model",
        create_text,
        re.IGNORECASE,
    )


def test_agent_create_never_silently_defaults_model_or_effort(create_text: str) -> None:
    # model/effort are suggested, then confirmed — never applied silently.
    assert re.search(r"never.*silently default|not.*silently default", create_text, re.IGNORECASE)
    assert re.search(r"Suggested model.*effort", create_text)
    assert re.search(r"accept\? *\(yes/change\)", create_text)


def test_agent_create_suggestion_matches_type_defaults(create_text: str) -> None:
    # The suggested (not forced-default) values still follow review->haiku,
    # team->sonnet, both->high.
    assert re.search(r"review.*haiku", create_text, re.IGNORECASE)
    assert re.search(r"team.*sonnet", create_text, re.IGNORECASE)
    assert re.search(r"suggest.*high", create_text, re.IGNORECASE)


def test_agent_create_explicit_flag_skips_the_confirmation_prompt(
    create_text: str,
) -> None:
    assert re.search(r"explicitly in Step 1", create_text)
    assert re.search(r"already a\s*\n?\s*decision", create_text, re.IGNORECASE)


def test_agent_create_tools_default_stays_silent(create_text: str) -> None:
    assert re.search(r"tools.*keeps its silent default", create_text, re.IGNORECASE)


def test_agent_create_optional_native_fields_have_no_forced_default(
    create_text: str,
) -> None:
    assert re.search(r"no forced default", create_text, re.IGNORECASE)


def test_agent_create_body_template_omits_effort_line(create_text: str) -> None:
    # Single source of truth: model/effort live in the frontmatter template
    # only. The body skeleton must not restate either as a body-level line.
    assert not re.search(r"Effort: <low\|medium\|high>", create_text)
    assert "Model tier:" not in create_text


# ---------------------------------------------------------------------------
# /agent-add authors the native contract and drops the retired --tier flag
# ---------------------------------------------------------------------------


def test_agent_add_documents_model_and_effort_flags(add_text: str) -> None:
    assert re.search(r"--model sonnet\|opus\|haiku\|fable\|inherit", add_text)
    assert re.search(r"--effort low\|medium\|high\|xhigh\|max", add_text)
    assert "--tier" not in add_text


def test_agent_add_documents_optional_native_fields(add_text: str) -> None:
    for flag in (
        "--memory",
        "--isolation",
        "--color",
        "--max-turns",
        "--background",
        "--skills",
    ):
        assert flag in add_text, f"{flag} not documented"
