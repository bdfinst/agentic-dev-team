"""Content checks for farley-score/SKILL.md's clarified scoring criteria and
worked example (issue #1776) — high correction-to-invocation ratio was caused
by ambiguous scoring logic and an unclear expected output shape.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "farley-score" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_scoring_anchors_section_present() -> None:
    text = _text()
    assert "### Scoring anchors — score from evidence, not intuition" in text, (
        "farley-score/SKILL.md is missing the scoring-anchors clarification "
        "for the 8-property rubric"
    )
    assert "A score with no citation is a guess" in text, (
        "scoring anchors section must state that every score needs a citation"
    )


def test_first_property_unknown_fallback_rule_present() -> None:
    text = _text()
    assert "mark the property `Unknown`" in text, (
        "farley-score/SKILL.md is missing the explicit fallback rule for "
        "scoring 'First' when commit history is unavailable"
    )
    assert "never substitute a default (e.g. 5) for missing evidence" in text, (
        "the Unknown fallback rule must forbid substituting a default score"
    )


def test_weighting_clarification_present() -> None:
    text = _text()
    assert "never multiply by 10 or present it as a percentage" in text, (
        "farley-score/SKILL.md is missing the weighting clarification that "
        "the Farley Score is a 1-10 scale, not a percentage"
    )


def test_worked_example_section_present() -> None:
    text = _text()
    assert "## Worked Example" in text, (
        "farley-score/SKILL.md is missing a Worked Example section"
    )
    assert "### Correct scoring output" in text, (
        "Worked Example must contain a correct scoring output subsection"
    )
    assert (
        "### Incorrect / ambiguous scoring output (avoid this)" in text
    ), "Worked Example must contrast a correct output against an incorrect/ambiguous one"


def test_worked_example_shows_verifiable_arithmetic() -> None:
    text = _text()
    assert "77.5 / 9.0 = **8.6 (Good)**" in text, (
        "the correct worked example must show the full weighted-sum arithmetic "
        "so the score is independently verifiable"
    )


def test_worked_example_names_incorrect_output_defects() -> None:
    text = _text()
    assert "No per-property breakdown." in text, (
        "the incorrect example must name the missing per-property breakdown as a defect"
    )
    assert "`Weakest Property` left blank." in text, (
        "the incorrect example must name the blank Weakest Property field as a defect"
    )
    assert "No arithmetic shown." in text, (
        "the incorrect example must name the missing arithmetic as a defect"
    )
