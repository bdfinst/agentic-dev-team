"""The gherkin-quality-critic agent is a new, narrowly-scoped adversarial
reviewer for freshly-derived/authored Gherkin (dispatched by
`/gherkin-derive` and `/gherkin-public`, never directly by the user or by
`/code-review`'s Scope-based roster). Asserts the fleet-wide required
frontmatter, that its output schema has no `verdict` field (findings are
report input, not a pass/fail gate), and that it stays scoped to exactly the
two checks the issue names — not duplicating `plan-review-acceptance`'s
plan-specific step-traceability/BDD-style checks.

Also asserts the shared dispatch/aggregation procedure doc documents the
dispatch mechanism, the aggregation key, failure handling, and the
zero-findings report state.

The agent's own name deliberately does not end in `-review.md` — see
`plugins/dev-team/tests/scripts/test_check_review_agent_mcp_tools.py`'s
`agents/*-review.md` glob, which mandates a five-MCP-tool grant this agent's
narrow Read/Grep/Glob-only design does not carry. `plan-review-*` escapes the
same glob the same way.
"""

from __future__ import annotations

import re

from _plugin_dirs import frontmatter_and_body, frontmatter_field

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "gherkin-quality-critic.md"
DISPATCH_DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "gherkin-quality-review-dispatch.md"
)
REGISTRY = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"


def _dispatch_doc_text() -> str:
    return DISPATCH_DOC.read_text(encoding="utf-8")


def _line_containing(text: str, marker: str) -> str:
    """Return the single line of text containing marker, for a targeted
    substring/regex check without burying intent behind chained splits."""
    for line in text.splitlines():
        if marker in line:
            return line
    return ""


def test_agent_file_exists() -> None:
    assert AGENT.is_file()


def test_declares_fleet_wide_required_frontmatter() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "name") == "gherkin-quality-critic"
    assert frontmatter_field(fm, "model") == "sonnet"
    assert frontmatter_field(fm, "effort") == "high"
    assert frontmatter_field(fm, "color") == "cyan"
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
    assert '"reviewer": "gherkin-quality-critic"' in body
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


def test_dispatch_doc_exists() -> None:
    assert DISPATCH_DOC.is_file()


def test_dispatch_doc_documents_parallel_dispatch() -> None:
    text = _dispatch_doc_text()
    assert re.search(r"two.*independent instances", text, re.IGNORECASE)
    assert re.search(r"parallel", text, re.IGNORECASE)


def test_dispatch_doc_documents_aggregation_key() -> None:
    text = _dispatch_doc_text()
    assert re.search(r"\(feature_file, title\)", text)


def test_dispatch_doc_documents_failure_handling() -> None:
    text = _dispatch_doc_text()
    assert re.search(r"treat that instance.*as empty", text, re.IGNORECASE)
    # The combined both-instances-failed fallback message is its own,
    # separately-asserted contract — a single-instance failure and a
    # both-failed run report different text, so both must be locked in.
    assert re.search(
        r"Both\s+review\s+instances\s+failed\s+to\s+return\s+usable\s+output\s+—"
        r"\s+no\s+Gherkin\s+quality\s+findings\s+available\s+for\s+this\s+run\.",
        text,
    )


def test_dispatch_doc_documents_zero_findings_state() -> None:
    text = _dispatch_doc_text()
    assert re.search(r"always print", text, re.IGNORECASE)
    assert "None — both instances raised no findings." in text


def test_dispatch_doc_notes_title_matching_is_best_effort() -> None:
    """The (feature_file, title) fold depends on both independently-
    dispatched instances wording the same real finding's title identically.
    That is a documented, accepted best-effort mitigation (verbatim-heading
    wording), not a guarantee — record the expectation so a future edit to
    the matching key has a citable baseline for what "good enough" means."""
    text = _dispatch_doc_text()
    assert re.search(r"verbatim", text, re.IGNORECASE)


def test_registered_as_team_agent_not_review_agent() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    assert "gherkin-quality-critic" in text
    team_agents_section = text.split("## Team Agents", 1)[1].split(
        "## Review Agents", 1
    )[0]
    review_agents_section = text.split("## Review Agents", 1)[1]
    assert "gherkin-quality-critic" in team_agents_section
    assert "gherkin-quality-critic" not in review_agents_section
    registry_row = _line_containing(team_agents_section, "gherkin-quality-critic")
    assert registry_row, "no registry row names gherkin-quality-critic"
    assert "never directly" in registry_row
