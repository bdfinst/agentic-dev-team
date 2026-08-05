"""Content check for gherkin-derive/SKILL.md's batched shared-context-file
edit guidance (issue #1775).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "gherkin-derive" / "SKILL.md"


def test_batching_instruction_present() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Batch shared context-file edits" in text, (
        "gherkin-derive/SKILL.md is missing explicit guidance to batch shared "
        "acceptance-test-context-file additions into one edit pass"
    )
    assert "one edit pass" in text, (
        "batching guidance must state the additions land in one edit pass, "
        "not one edit per step definition"
    )
