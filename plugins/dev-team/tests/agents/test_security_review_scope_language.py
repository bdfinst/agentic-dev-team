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
