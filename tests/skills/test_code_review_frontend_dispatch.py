"""/code-review dispatches the frontend-architecture lens on UI components.

Two contracts:

1. When frontend component files are in the target set, /code-review's agent
   roster includes component-architecture-review (the agent behind
   /frontend-architecture), so component reuse/composition findings surface in
   an ordinary review — not only when the user runs /frontend-architecture.
2. Agent enumeration keys on the Review Agents section of
   knowledge/agent-registry.md — not on the retired `Model tier:` body line,
   which no shipped agent carries (see test_agent_audit_effort.py).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "plugins" / "dev-team" / "skills"
CODE_REVIEW = (SKILLS / "code-review" / "SKILL.md").read_text(encoding="utf-8")
REVIEW_AGENT = (SKILLS / "review-agent" / "SKILL.md").read_text(encoding="utf-8")
FRONTEND_ARCH = (SKILLS / "frontend-architecture" / "SKILL.md").read_text(
    encoding="utf-8"
)


def test_code_review_dispatches_component_architecture_review_for_ui_files():
    assert "component-architecture-review" in CODE_REVIEW


def test_code_review_names_the_frontend_component_file_types():
    for ext in (".jsx", ".tsx", ".vue", ".svelte"):
        assert ext in CODE_REVIEW, f"frontend dispatch rule missing {ext}"


def test_code_review_links_the_standalone_frontend_architecture_entry_point():
    assert "/frontend-architecture" in CODE_REVIEW


def test_code_review_enumerates_agents_from_the_registry_not_model_tier():
    assert "Model tier" not in CODE_REVIEW
    assert "agent-registry.md" in CODE_REVIEW


def test_review_agent_skill_does_not_key_on_retired_model_tier_line():
    assert "Model tier" not in REVIEW_AGENT


def test_frontend_architecture_notes_the_code_review_integration():
    assert "/code-review" in FRONTEND_ARCH
