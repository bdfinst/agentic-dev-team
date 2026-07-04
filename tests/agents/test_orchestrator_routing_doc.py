"""Tests for agents/orchestrator.md + CLAUDE.md routing-doc rewrite.

Covers the registry cross-reference and the registry pointer.

Ported from tests/agents/orchestrator_routing_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
CLAUDE_MD = REPO_ROOT / "plugins" / "dev-team" / "CLAUDE.md"
ROUTING_JSON = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "model-routing.json"


@pytest.fixture(scope="module")
def orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def test_orchestrator_no_static_model_routing_table_heading(orch_text: str) -> None:
    assert not re.search(r"^##.*Model Routing Table", orch_text, re.MULTILINE)


def test_orchestrator_contains_resolution_procedure_section(orch_text: str) -> None:
    assert re.search(r"^##.*Resolution Procedure", orch_text, re.MULTILINE)


def test_orchestrator_resolution_procedure_names_resolver_hook(
    orch_text: str,
) -> None:
    assert "hooks/agent_model_resolve.py" in orch_text


def test_orchestrator_resolution_procedure_names_resolver_helper(
    orch_text: str,
) -> None:
    assert "hooks/lib/model_resolve.py" in orch_text


def test_orchestrator_resolution_procedure_names_routing_json_and_ladder(
    orch_text: str,
) -> None:
    assert "knowledge/model-routing.json" in orch_text
    assert ".claude/model-ladder.json" in orch_text


def test_orchestrator_resolution_procedure_describes_effort_bands(
    orch_text: str,
) -> None:
    assert re.search(
        r"effort:? *(band|low\|medium\|high|low, medium, high)", orch_text
    ) or re.search(r"effort band", orch_text, re.IGNORECASE)


def test_orchestrator_inline_review_table_no_longer_encodes_tier_parens(
    orch_text: str,
) -> None:
    # The pre-rewrite table had cells like '(haiku)', '(sonnet)', '(opus)'
    # which embedded routing decisions in agent dispatch documentation. The
    # rewrite removes those parens; routing decisions live in routing.json.
    assert not re.search(r"\((haiku|sonnet|opus)\)", orch_text)


def test_orchestrator_no_pinned_model_snapshot_ids(orch_text: str) -> None:
    assert not re.search(r"claude-(haiku|sonnet|opus)-[0-9]", orch_text)


def test_claude_md_model_routing_section_is_pointer_not_static_table(
    claude_md_text: str,
) -> None:
    # The pre-rewrite block contained a markdown table with three Model rows
    # (haiku/sonnet/opus). The rewrite reduces it to one paragraph pointing
    # at the resolver hook + helper + docs.
    assert not re.search(r"^\|.*\bhaiku\b.*\|", claude_md_text, re.MULTILINE)
    assert not re.search(r"^\|.*\bsonnet\b.*\|", claude_md_text, re.MULTILINE)
    assert not re.search(
        r"^\|.*\bopus\b.*\| \(opus tier\)", claude_md_text, re.MULTILINE
    )
    assert "hooks/agent_model_resolve.py" in claude_md_text


def test_skills_registry_contains_model_routing_check_row() -> None:
    # Skills Registry moved to knowledge/skills-registry.md in the CLAUDE.md
    # size reduction.
    skills_reg = CLAUDE_MD.parent / "knowledge" / "skills-registry.md"
    text = skills_reg.read_text(encoding="utf-8")
    assert re.search(r"\| `/model-routing-check`", text)


def test_claude_md_no_pinned_model_snapshot_ids(claude_md_text: str) -> None:
    assert not re.search(r"claude-(haiku|sonnet|opus)-[0-9]", claude_md_text)
