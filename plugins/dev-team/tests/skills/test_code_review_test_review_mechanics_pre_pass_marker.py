"""Content guard for code-review/SKILL.md step 2b's test-review mechanical
pre-phase (#2169 Step 2.3, arch-review + correctness-review finding #1).

`test_review_mechanics.py` (Step 2.2) is only useful if something actually
invokes it. `agents/test-review.md`'s Protocol Phase 0 expects the *caller*
dispatching test-review to run it per file and supply the result as
context -- since no `*-review.md` agent has a Bash tool, the dispatch site
has to live in the orchestrating skill, not the agent file. `/code-review`
step 2b is the established pattern for exactly this kind of pre-pass
(`repo_invariants.py` #1608, `internal_double_detector.py` #2130) -- this
test pins that `test_review_mechanics.py` is named in that same step 2b
location, so a future SKILL.md edit can't silently drop the only place this
script is ever invoked.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "SKILL.md"

_MARKER = "### 2b. Static analysis pre-pass"


def _step_2b_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert _MARKER in text, "step 2b heading not found"
    section = text.split(_MARKER, 1)[1].split("\n### ", 1)[0]
    return section


def test_step_2b_invokes_test_review_mechanics_script() -> None:
    section = _step_2b_section()
    assert "test_review_mechanics.py" in section, (
        "code-review SKILL.md step 2b no longer names test_review_mechanics.py "
        "-- test-review's Phase 0 mechanical pre-phase would have no dispatch site"
    )


def test_step_2b_test_review_pre_pass_is_alongside_the_other_two_pre_passes() -> None:
    section = _step_2b_section()
    assert "repo_invariants.py" in section
    assert "internal_double_detector.py" in section
    assert "test_review_mechanics.py" in section


def test_step_2b_test_review_pre_pass_cites_its_issue_and_envelope() -> None:
    section = _step_2b_section()
    assert "**Test-review mechanical pre-phase (#2169).**" in section
    pre_pass = " ".join(section.split("Test-review mechanical pre-phase", 1)[1].split())
    assert "detected by static analysis" in pre_pass
