"""Referential-integrity sensor for the approach-contract knowledge file.

decision-defaults.md is only useful if the discovery/classification surfaces
reference it, so this keeps the file present and wired in.

Ported from tests/repo/decision_defaults_refs_test.bats (#673).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
KNOWLEDGE = PLUGIN / "knowledge" / "decision-defaults.md"


def test_decision_defaults_md_exists() -> None:
    assert KNOWLEDGE.is_file()


def test_orchestrator_references_decision_defaults() -> None:
    assert (
        "knowledge/decision-defaults.md"
        in (PLUGIN / "agents" / "orchestrator.md").read_text()
    )


def test_product_manager_references_decision_defaults() -> None:
    assert (
        "knowledge/decision-defaults.md"
        in (PLUGIN / "agents" / "product-manager.md").read_text()
    )


def test_plan_skill_references_decision_defaults() -> None:
    assert (
        "knowledge/decision-defaults.md"
        in (PLUGIN / "skills" / "plan" / "SKILL.md").read_text()
    )


def test_decision_defaults_registered_in_agent_registry() -> None:
    assert (
        "knowledge/decision-defaults.md"
        in (PLUGIN / "knowledge" / "agent-registry.md").read_text()
    )


def test_context_loading_protocol_has_step_0() -> None:
    assert (
        "Step 0"
        in (PLUGIN / "skills" / "context-loading-protocol" / "SKILL.md").read_text()
    )


def test_pr_skill_enables_auto_merge_by_default() -> None:
    assert "gh pr merge --auto" in (PLUGIN / "skills" / "pr" / "SKILL.md").read_text()


def test_ship_skill_exists_and_registered() -> None:
    assert (PLUGIN / "skills" / "ship" / "SKILL.md").is_file()
    # Skills Registry moved to knowledge/skills-registry.md; CLAUDE.md now has a
    # pointer.
    assert "`/ship`" in (PLUGIN / "knowledge" / "skills-registry.md").read_text()
