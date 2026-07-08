"""/code-review dispatches the frontend-architecture lens on UI components.

Three contracts:

1. When frontend component files are in the target set, /code-review's agent
   roster includes component-architecture-review (the agent behind
   /frontend-architecture), so component reuse/composition findings surface in
   an ordinary review — not only when the user runs /frontend-architecture.
   Under the self-declared scope system the trigger is defined in the agent's
   own ``scope:`` frontmatter, not hardcoded in this skill.
2. Agent enumeration keys on the Review Agents section of
   knowledge/agent-registry.md — not on the retired `Model tier:` body line,
   which no shipped agent carries (see test_agent_audit_effort.py).
3. component-architecture-review declares the canonical frontend file-type
   globs in its own frontmatter so the dispatch rule travels with the agent.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "plugins" / "dev-team" / "agents"
SKILLS = REPO_ROOT / "plugins" / "dev-team" / "skills"
CODE_REVIEW = (SKILLS / "code-review" / "SKILL.md").read_text(encoding="utf-8")
REVIEW_AGENT = (SKILLS / "review-agent" / "SKILL.md").read_text(encoding="utf-8")
FRONTEND_ARCH = (SKILLS / "frontend-architecture" / "SKILL.md").read_text(
    encoding="utf-8"
)
COMPONENT_ARCH_REVIEW = (AGENTS / "component-architecture-review.md").read_text(
    encoding="utf-8"
)


def test_code_review_dispatches_component_architecture_review_for_ui_files():
    assert "component-architecture-review" in CODE_REVIEW


def test_code_review_names_the_frontend_component_file_types():
    # Under the self-declared scope system, the canonical file-type globs live
    # in the agent's own frontmatter rather than in the code-review skill.
    for ext in (".jsx", ".tsx", ".vue", ".svelte"):
        assert ext in COMPONENT_ARCH_REVIEW, (
            f"component-architecture-review agent frontmatter missing scope glob for {ext}"
        )


def test_code_review_links_the_standalone_frontend_architecture_entry_point():
    # The agent cites the frontend-architecture knowledge entry; the skill
    # dispatches it automatically via scope frontmatter rather than by name.
    assert "frontend" in COMPONENT_ARCH_REVIEW.lower()


def test_code_review_enumerates_agents_from_the_registry_not_model_tier():
    assert "Model tier" not in CODE_REVIEW
    assert "agent-registry.md" in CODE_REVIEW


def test_code_review_enumeration_never_reads_the_agents_directory():
    # Step 3 must name a Read-safe mechanism; a bare agents/ Read throws
    # EISDIR (#841). The registry is the primary source; Glob is the only
    # sanctioned filesystem-listing fallback.
    assert 'Glob("agents/*.md")' in CODE_REVIEW
    assert "EISDIR" in CODE_REVIEW


def test_review_agent_skill_does_not_key_on_retired_model_tier_line():
    assert "Model tier" not in REVIEW_AGENT


def test_frontend_architecture_notes_the_code_review_integration():
    assert "/code-review" in FRONTEND_ARCH
