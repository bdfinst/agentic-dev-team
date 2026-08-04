"""Content checks for stryker-xunit-v2-shim/SKILL.md's read-before-edit
preamble and converged-state check (issue #1773).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "stryker-xunit-v2-shim"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_read_before_edit_list_names_all_three_artifacts_together() -> None:
    text = _text()
    for phrase in ("mutant-survivors report", "shim config", "step files"):
        assert phrase in text, f"read-before-edit list is missing {phrase!r}"

    idx1 = text.index("mutant-survivors report")
    idx2 = text.index("shim config")
    idx3 = text.index("step files")
    span_start = min(idx1, idx2, idx3)
    span_end = max(idx1, idx2, idx3)
    assert span_end - span_start < 500, (
        "the three read-before-edit items should be co-located in one list, "
        "not scattered across the file"
    )


def test_converged_state_skip_instruction_present() -> None:
    text = _text().lower()
    assert "converged-state" in text or "converged state" in text, (
        "missing a converged-state check instruction"
    )
    assert "skip re-editing" in text, (
        "missing the instruction to skip re-editing a file already at its target state"
    )
