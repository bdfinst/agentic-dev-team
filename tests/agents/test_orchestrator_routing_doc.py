"""Tests for agents/orchestrator.md + CLAUDE.md model/effort documentation.

ADR 0026 (epic #1284) retired the band-to-model resolver hook, its helper,
and knowledge/model-routing.json in favor of the native model:/effort:
frontmatter contract the harness resolves itself. This file asserts the
retired system's names are gone and the native contract is documented in
their place.

Ported from tests/agents/orchestrator_routing_doc_tests.bats (issue #675:
bats -> pytest); rewritten for #1288.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
CLAUDE_MD = REPO_ROOT / "plugins" / "dev-team" / "CLAUDE.md"


@pytest.fixture(scope="module")
def orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def test_orchestrator_no_static_model_routing_table_heading(orch_text: str) -> None:
    assert not re.search(r"^##.*Model Routing Table", orch_text, re.MULTILINE)


def test_orchestrator_contains_model_effort_resolution_section(orch_text: str) -> None:
    assert re.search(r"^##.*Model/Effort Resolution", orch_text, re.MULTILINE)


def test_orchestrator_no_longer_names_the_retired_resolver_hook(
    orch_text: str,
) -> None:
    assert "hooks/agent_model_resolve.py" not in orch_text


def test_orchestrator_no_longer_names_the_retired_resolver_helper(
    orch_text: str,
) -> None:
    assert "hooks/lib/model_resolve.py" not in orch_text


def test_orchestrator_no_longer_names_the_retired_routing_json_or_ladder(
    orch_text: str,
) -> None:
    assert "knowledge/model-routing.json" not in orch_text
    assert ".claude/model-ladder.json" not in orch_text


def test_orchestrator_names_the_native_model_and_effort_fields(
    orch_text: str,
) -> None:
    assert "`model:`" in orch_text
    assert "`effort:`" in orch_text


def test_orchestrator_inline_review_table_no_longer_encodes_tier_parens(
    orch_text: str,
) -> None:
    # The pre-rewrite table had cells like '(haiku)', '(sonnet)', '(opus)'
    # which embedded routing decisions in agent dispatch documentation.
    assert not re.search(r"\((haiku|sonnet|opus)\)", orch_text)


def test_orchestrator_no_pinned_model_snapshot_ids(orch_text: str) -> None:
    assert not re.search(r"claude-(haiku|sonnet|opus)-[0-9]", orch_text)


def test_claude_md_model_section_is_a_pointer_not_a_static_table(
    claude_md_text: str,
) -> None:
    # The pre-rewrite block contained a markdown table with three Model rows
    # (haiku/sonnet/opus). The rewrite reduces it to one paragraph pointing
    # at the native contract, with no resolver hook to name.
    assert not re.search(r"^\|.*\bhaiku\b.*\|", claude_md_text, re.MULTILINE)
    assert not re.search(r"^\|.*\bsonnet\b.*\|", claude_md_text, re.MULTILINE)
    assert not re.search(
        r"^\|.*\bopus\b.*\| \(opus tier\)", claude_md_text, re.MULTILINE
    )
    assert "hooks/agent_model_resolve.py" not in claude_md_text


def test_skills_registry_no_longer_contains_model_routing_check_row() -> None:
    # Skills Registry lives in knowledge/skills-registry.md.
    skills_reg = CLAUDE_MD.parent / "knowledge" / "skills-registry.md"
    text = skills_reg.read_text(encoding="utf-8")
    assert not re.search(r"\| `/model-routing-check`", text)


def test_claude_md_no_pinned_model_snapshot_ids(claude_md_text: str) -> None:
    assert not re.search(r"claude-(haiku|sonnet|opus)-[0-9]", claude_md_text)
