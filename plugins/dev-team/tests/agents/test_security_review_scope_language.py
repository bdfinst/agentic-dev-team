"""Content checks for security-review.md's `## Non-Goals` section and its
confidence-gating instruction (issue #1772).

`## Non-Goals` folds the prior `## Ignore` section's content rather than
leaving both headings standing. The confidence-gating instruction reuses
this repo's existing `high/medium/none` enum
(`knowledge/review-agent-output-contract.md`) — a low-certainty finding maps
to `confidence: none`, never a new "low" tier.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "security-review.md"


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def test_non_goals_heading_has_at_least_three_bullets() -> None:
    text = _text()
    assert "## Non-Goals" in text, (
        "security-review.md is missing a '## Non-Goals' heading"
    )
    section = text.split("## Non-Goals", 1)[1].split("\n## ", 1)[0]
    bullets = [line for line in section.splitlines() if line.strip().startswith("- ")]
    assert len(bullets) >= 3, (
        f"'## Non-Goals' section has {len(bullets)} bullet(s); expected at least 3"
    )


def test_old_ignore_heading_is_folded_away() -> None:
    text = _text()
    assert "## Ignore" not in text, (
        "the prior '## Ignore' section should be folded into '## Non-Goals', "
        "not left standing alongside it"
    )


def test_confidence_none_co_located_with_low_certainty_framing() -> None:
    text = _text()
    idx = text.find("confidence: none")
    assert idx != -1, "expected the literal instruction text 'confidence: none'"
    window = text[max(0, idx - 400) : idx + 400]
    assert "low-certainty" in window or "low certainty" in window, (
        "'confidence: none' should be co-located with low-certainty finding framing"
    )


def _scope_section() -> str:
    text = _text()
    marker = "## Scope — files always in scope"
    assert marker in text, f"security-review.md is missing the '{marker}' heading"
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_always_in_scope_files_are_diff_gated_for_ordinary_runs() -> None:
    """Issue #1809: 'always in scope' must mean no file-type exemption from
    review, not an unconditional full-repo scan on every run. For an
    ordinary diff-scoped run, the CI/CD-workflow/Dockerfile/infra-manifest
    classes are examined only when they appear in the diff under review."""
    section = _scope_section()
    assert "no file-type exemption" in section, (
        "'files always in scope' should be reframed as 'no file-type "
        "exemption', not an unconditional full-repo scan"
    )
    assert "not an unconditional full-repo scan" in section, (
        "the Scope section should explicitly disclaim unconditional "
        "full-repo scanning on every run"
    )
    assert "diff" in section, (
        "the Scope section should tie ordinary-run examination of these "
        "file classes to the diff under review"
    )


def test_whole_repo_phase_1b_invocation_unaffected_by_diff_gating() -> None:
    """The whole-repo `security-assessment` Phase 1b invocation has no diff
    at all, so the ordinary-run diff-gating language must not narrow it —
    it is a separate mode, not a carve-out exception to the diff-gated
    rule."""
    text = _text()
    assert "## Trigger context" in text
    trigger_section = text.split("## Trigger context", 1)[1].split("\n## ", 1)[0]
    assert "security-assessment" in trigger_section
    assert "Phase 1b" in trigger_section
    assert "no diff at all" in trigger_section, (
        "Trigger context should state the Phase 1b invocation has no diff "
        "at all, so diff-gating doesn't narrow it"
    )

    scope_section = _scope_section()
    assert "whole-repo" in scope_section or "whole repository" in scope_section, (
        "the Scope section should name the whole-repo Phase 1b mode as "
        "outside diff-gating by construction, not exempt it as a carve-out"
    )


def test_non_goals_out_of_diff_bullet_remains_unqualified() -> None:
    """The Non-Goals bullet excluding pre-existing out-of-diff vulnerabilities
    must stay absolute — no carve-out qualifiers added to its own text."""
    text = _text()
    assert "## Non-Goals" in text
    section = text.split("## Non-Goals", 1)[1].split("\n## ", 1)[0]
    bullet_line = next(
        line
        for line in section.splitlines()
        if "out-of-diff scope creep" in line
    )
    assert bullet_line.strip() == (
        "- Flag pre-existing vulnerabilities outside the diff under review "
        "(out-of-diff scope creep)"
    ), (
        "the out-of-diff Non-Goals bullet must remain absolute/unqualified "
        f"in its own text; got: {bullet_line!r}"
    )
