"""Issue #835 — code-review's allowed-tools must grant Write.

The skill body creates NEW files (correction prompts under corrections/,
the .review-passed gate marker, metrics/override-audit.jsonl). Edit can only
modify existing files, so without Write in the frontmatter allowed-tools the
orchestrator cannot persist any of them and hallucinates a successful save.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, frontmatter, grep

CODE_REVIEW = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")


def test_code_review_allows_write_for_corrections_and_gate_file():
    fm = frontmatter(CODE_REVIEW)
    assert grep(r"\bWrite\b", fm), (
        "code-review writes corrections/, .review-passed, override-audit.jsonl "
        "— Write must be in allowed-tools"
    )
