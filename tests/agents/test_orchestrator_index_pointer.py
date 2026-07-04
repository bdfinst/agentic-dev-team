"""Spec §Agent consumer integration — Consumer usage pattern requirement.

The orchestrator's body must explain how to resolve a knowledge anchor into a
Read with offset/limit. This is the canonical onboarding for every agent that
reads index entries.

Ported from tests/agents/orchestrator_index_pointer_test.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
ARCH_DOC = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent-architecture.md"


def test_orchestrator_documents_index_offset_limit_read_flow() -> None:
    assert ORCH.is_file()
    text = ORCH.read_text(encoding="utf-8")
    assert "knowledge/index.json" in text
    assert "offset" in text
    assert "limit" in text


def test_agent_architecture_doc_cross_references_consumer_usage_pointer() -> None:
    assert ARCH_DOC.is_file()
    text = ARCH_DOC.read_text(encoding="utf-8")
    assert "knowledge/index.json" in text
