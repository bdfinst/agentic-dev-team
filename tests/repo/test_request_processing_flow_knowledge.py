"""Tests for the request-processing-flow knowledge file extraction.

Ported from tests/repo/request_processing_flow_knowledge_tests.bats (#673).
"""

from __future__ import annotations

from pathlib import Path

RPF = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "request-processing-flow.md"
)


def test_request_processing_flow_md_exists() -> None:
    assert RPF.is_file()


def test_request_processing_flow_md_contains_three_phase_workflow_section() -> None:
    assert "Three-Phase Workflow" in RPF.read_text()


def test_request_processing_flow_md_contains_multi_agent_coordination_section() -> None:
    assert "Sub-Agents as Context Isolation" in RPF.read_text()
