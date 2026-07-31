"""Content guards for the long-run waiting/scheduling contract doc.

The doc exists because a scheduled wake-up armed without its replay
instruction fails validation and schedules *nothing* — the backstop the
skill thought it armed never fires. These checks pin the parts of the
contract an agent has to read to avoid that call, and pin the pointers
from the skills that tell an agent to wait on a long-running job.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
DOC = PLUGIN / "knowledge" / "long-run-waiting.md"

# Every skill whose instructions can lead an agent to arm a timer for work
# that outlives a turn must point at the contract.
REFERRING_SKILLS = (
    "long-eval",
    "mutation-testing",
    "stryker-xunit-v2-shim",
    "ci-debugging",
    "ship",
)


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists():
    assert DOC.is_file(), f"missing knowledge doc: {DOC}"


def test_doc_states_prompt_is_required_to_arm():
    """The failing call shape is the whole reason the doc exists."""
    text = _doc_text()
    assert "`prompt` is required when `stop` is not true." in text, (
        "the doc must quote the exact validation error verbatim so an agent "
        "that hit it can match the message to this contract"
    )
    assert "**required**" in text, "prompt/reason must be marked required"


def test_doc_states_a_failed_arm_schedules_nothing():
    """The expensive part isn't the error — it's the timer that never armed."""
    text = _doc_text().lower()
    assert "no timer is armed" in text
    assert "never fires" in text


def test_doc_states_the_stop_only_call_shape():
    """Standing down is `stop: true` alone — not a reason-only call."""
    text = _doc_text()
    assert "`stop: true` alone" in text
    assert "takes **no other fields**" in text


def test_doc_forbids_sleep_loops():
    text = _doc_text().lower()
    assert "sleep" in text, "the doc must rule out foreground sleep loops"


def test_doc_requires_self_re_arming_prompts_to_carry_a_terminal_condition():
    text = _doc_text().lower()
    assert "terminal condition" in text


def test_referring_skills_point_at_the_doc():
    for skill in REFERRING_SKILLS:
        skill_md = PLUGIN / "skills" / skill / "SKILL.md"
        assert skill_md.is_file(), f"missing skill: {skill_md}"
        assert "knowledge/long-run-waiting.md" in skill_md.read_text(
            encoding="utf-8"
        ), (
            f"{skill}/SKILL.md tells an agent to wait on long-running work but "
            "does not point at knowledge/long-run-waiting.md"
        )


def test_doc_lists_the_skills_that_reference_it():
    """Keep the doc's own 'who reads this' list honest with the pointers."""
    text = _doc_text()
    for skill in REFERRING_SKILLS:
        assert f"`/{skill}`" in text, (
            f"knowledge/long-run-waiting.md does not list /{skill} among the "
            "skills that reference it"
        )
