"""Content guard for agent-eval/SKILL.md's test-review Phase 0 pre-phase
wiring (#2169 follow-up, noted in plans/2164-abort-countable-tiered.md's
Risks section as "Correction to the above").

`/agent-eval`'s unit-tier dispatch passes only the fixture file to a review
agent (constraint 3) -- but `test-review`'s Phase 0 mechanical pre-phase
(`agents/test-review.md` -> Protocol) needs its `test_review_mechanics.py`
result supplied as caller context, since the agent has no Bash tool and
never runs the script itself. Without a dispatch site inside `/agent-eval`
itself, an eval run can never exercise Phase 0's `mechanicalFail` gating --
only Phase 1/2's judgment, unaffected by Phase 0. This test pins that the
dispatch site stays present, so a future SKILL.md edit can't silently drop
it the same way the first `/code-review` step 2b wiring attempt did (see
`test_code_review_test_review_mechanics_pre_pass_marker.py`).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-eval" / "SKILL.md"

_STEP3_MARKER = "### 3. Run agents against fixtures"
_NEXT_STEP_MARKER = "### 4. Grade each result"


def _step3_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert _STEP3_MARKER in text, "Step 3 heading not found"
    return text.split(_STEP3_MARKER, 1)[1].split(_NEXT_STEP_MARKER, 1)[0]


def test_step3_invokes_test_review_mechanics_script() -> None:
    section = _step3_section()
    assert "test_review_mechanics.py" in section, (
        "agent-eval SKILL.md no longer names test_review_mechanics.py -- "
        "test-review's Phase 0 would have no dispatch site during /agent-eval"
    )


def test_step3_gates_the_pre_phase_on_test_review_only() -> None:
    section = _step3_section()
    pre_phase = section.split("test_review_mechanics.py", 1)[0][-400:]
    assert "test-review" in pre_phase, (
        "the pre-phase block should be scoped to the test-review agent, "
        "not run unconditionally for every fixture/agent pair"
    )


def test_step3_default_dispatch_appends_phase0_result_for_test_review() -> None:
    section = _step3_section()
    assert "detected by static analysis, do not re-derive" in section
    assert "cite verbatim" in section


def test_constraint_3_documents_the_test_review_exception() -> None:
    text = SKILL.read_text(encoding="utf-8")
    constraints = text.split("## Orchestrator constraints", 1)[1].split("## Parse Arguments", 1)[0]
    assert "test_review_mechanics.py" in constraints
    assert "test-review" in constraints


def test_allowed_tools_permits_test_review_mechanics_invocation() -> None:
    text = SKILL.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    assert "test_review_mechanics.py" in frontmatter, (
        "allowed-tools frontmatter must permit invoking test_review_mechanics.py "
        "or the Step 3 pre-phase call is blocked at the tool-permission layer"
    )
