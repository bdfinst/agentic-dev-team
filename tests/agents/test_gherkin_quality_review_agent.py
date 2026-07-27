"""Issue #1452 — the gherkin-quality-review agent is a new, narrowly-scoped
adversarial reviewer for freshly-derived/authored Gherkin (dispatched by
`/gherkin-derive` and `/gherkin-public`, never directly by the user or by
`/code-review`'s Scope-based roster). Asserts the fleet-wide required
frontmatter, that its output schema has no `verdict` field (findings are
report input, not a pass/fail gate), and that it stays scoped to exactly the
two checks the issue names — not duplicating `plan-review-acceptance`'s
plan-specific step-traceability/BDD-style checks.

Also asserts the shared dispatch/aggregation procedure doc (Slice 1, Step 1.3)
exists and documents the dispatch mechanism, the aggregation key, failure
handling, and the zero-findings report state.
"""

from __future__ import annotations

from _plugin_dirs import frontmatter_and_body, frontmatter_field

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "gherkin-quality-review.md"
DISPATCH_DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "gherkin-quality-review-dispatch.md"
)
REGISTRY = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"


def test_agent_file_exists() -> None:
    assert AGENT.is_file()


def test_declares_fleet_wide_required_frontmatter() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "name") == "gherkin-quality-review"
    assert frontmatter_field(fm, "model") == "sonnet"
    assert frontmatter_field(fm, "effort") == "high"
    assert frontmatter_field(fm, "color") == "green"
    tools = frontmatter_field(fm, "tools")
    assert "Read" in tools and "Grep" in tools and "Glob" in tools
    assert "Write" not in tools
    assert "Edit" not in tools
    assert "Agent" not in tools


def test_description_has_no_colon() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    description = frontmatter_field(fm, "description")
    assert ":" not in description


def test_declares_context_needs() -> None:
    _, body = frontmatter_and_body(AGENT)
    assert "Context needs: artifact-stream" in body


def test_output_schema_has_gaps_and_balance_issues_but_no_verdict() -> None:
    _, body = frontmatter_and_body(AGENT)
    assert '"reviewer": "gherkin-quality-review"' in body
    assert '"gaps"' in body
    assert '"balance_issues"' in body
    assert '"verdict"' not in body


def test_each_finding_cites_feature_file_and_title() -> None:
    _, body = frontmatter_and_body(AGENT)
    assert '"feature_file"' in body
    assert '"title"' in body


def test_scope_excludes_plan_specific_checks() -> None:
    """This agent has no plan context — step traceability, BDD determinism/
    isolation checks, and scenario-provenance review stay
    plan-review-acceptance's job (its own body owns "Step Traceability")."""
    _, body = frontmatter_and_body(AGENT)
    assert "Step Traceability" not in body


def test_dispatch_doc_exists_and_documents_the_four_mechanics() -> None:
    assert DISPATCH_DOC.is_file()
    text = DISPATCH_DOC.read_text(encoding="utf-8")
    assert "Agent" in text and "parallel" in text.lower()
    assert "feature_file" in text and "title" in text.lower()
    assert "fail" in text.lower()
    assert "zero" in text.lower() or "none" in text.lower()


def test_registered_as_team_agent_not_review_agent() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    assert "gherkin-quality-review" in text
    team_agents_section = text.split("## Team Agents", 1)[1].split(
        "## Review Agents", 1
    )[0]
    review_agents_section = text.split("## Review Agents", 1)[1]
    assert "gherkin-quality-review" in team_agents_section
    assert "gherkin-quality-review" not in review_agents_section
    assert (
        "never directly"
        in team_agents_section.split("gherkin-quality-review", 1)[1].split("\n", 1)[0]
    )
