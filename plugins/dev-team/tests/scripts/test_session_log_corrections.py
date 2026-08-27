"""Unit tests for scripts/lib/session_log/corrections.py (issue #2013,
part of epic #2008).

Covers the deterministic classifier's three dimensions (what/component/
shape) branch by branch, including the two `WHAT_VALUES`/`SHAPE_VALUES`
the golden-corpus scenario in `test_session_report_golden.py` does not
reach ("other" and "narrowed-scope" — see that test's corpus comment for
the five it DOES reach end-to-end), and a dedicated privacy proof mirroring
`test_session_log_redact.py`'s style: the correction TEXT must never appear
in a `classify_correction()` result, only the closed-vocabulary labels.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import corrections

# ---------------------------------------------------------------------------
# is_review_agent_name
# ---------------------------------------------------------------------------


def test_is_review_agent_name_matches_dash_review_suffix():
    assert corrections.is_review_agent_name("correctness-review") is True


def test_is_review_agent_name_matches_dash_reviewer_suffix():
    assert corrections.is_review_agent_name("quality-reviewer") is True


def test_is_review_agent_name_matches_plan_review_prefix():
    assert corrections.is_review_agent_name("plan-review-acceptance") is True


def test_is_review_agent_name_false_for_non_review_agent():
    assert corrections.is_review_agent_name("software-engineer") is False


def test_is_review_agent_name_false_for_none():
    assert corrections.is_review_agent_name(None) is False


def test_is_review_agent_name_false_for_empty_string():
    assert corrections.is_review_agent_name("") is False


# ---------------------------------------------------------------------------
# observe_assistant_turn — the "what" dimension
# ---------------------------------------------------------------------------


def test_observe_assistant_turn_returns_none_for_non_assistant_record():
    assert corrections.observe_assistant_turn({"type": "user"}, "text") is None


def test_observe_assistant_turn_edit_tool_use_is_code_edit():
    content = [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/x.py"}}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "code-edit"}


def test_observe_assistant_turn_plan_skill_dispatch_is_plan():
    content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "dev-team:plan"}}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "plan"}


def test_observe_assistant_turn_non_plan_skill_dispatch_is_other():
    content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "dev-team:triage"}}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "other"}


def test_observe_assistant_turn_review_agent_dispatch_is_review_finding():
    content = [
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "dev-team:doc-review"}}
    ]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "review-finding"}


def test_observe_assistant_turn_non_review_agent_dispatch_is_other():
    content = [
        {
            "type": "tool_use",
            "name": "Agent",
            "input": {"subagent_type": "dev-team:software-engineer"},
        }
    ]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "other"}


def test_observe_assistant_turn_bash_is_tool_choice():
    content = [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "tool-choice"}


def test_observe_assistant_turn_read_tool_is_other():
    # Read isn't Edit/Skill/Agent/Bash -- a real tool call the classifier
    # has no dedicated bucket for, so it's the deterministic "other", not a
    # guess at one of the four named buckets.
    content = [{"type": "tool_use", "name": "Read", "input": {"file_path": "/x.py"}}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "other"}


def test_observe_assistant_turn_text_only_is_factual_claim():
    content = [{"type": "text", "text": "this should work"}]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "factual-claim"}


def test_observe_assistant_turn_no_content_is_other():
    turn = corrections.observe_assistant_turn({"type": "assistant"}, None)
    assert turn == {"what": "other"}


def test_observe_assistant_turn_code_edit_wins_over_other_candidates_in_same_turn():
    # code-edit is highest priority even when Bash/Skill/Agent appear in the
    # SAME turn (order-independent -- see module docstring).
    content = [
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/x.py"}},
    ]
    turn = corrections.observe_assistant_turn({"type": "assistant"}, content)
    assert turn == {"what": "code-edit"}


# ---------------------------------------------------------------------------
# classify_shape — the "shape" dimension
# ---------------------------------------------------------------------------


def test_classify_shape_reverted():
    assert corrections.classify_shape("please revert that change") == ("reverted", "high")


def test_classify_shape_not_what_asked():
    assert corrections.classify_shape("that's not what i asked for") == (
        "not-what-asked",
        "high",
    )


def test_classify_shape_flagged_wrong():
    assert corrections.classify_shape("that's wrong") == ("flagged-wrong", "high")


def test_classify_shape_narrowed_scope():
    assert corrections.classify_shape("just do the one file, not the rest") == (
        "narrowed-scope",
        "high",
    )


def test_classify_shape_redirected():
    assert corrections.classify_shape("actually, let's try something else") == (
        "redirected",
        "high",
    )


def test_classify_shape_bare_no_is_ambiguous_low_confidence():
    # "no" alone is a real CORRECTION_RE match (signals.detect_correction_turn
    # would flag this turn) but tells the shape classifier nothing on its
    # own -- the honest fallback, not a guess.
    assert corrections.classify_shape("no.") == ("ambiguous", "low")


def test_classify_shape_reverted_wins_over_flagged_wrong_priority():
    assert corrections.classify_shape("no, that's wrong, revert it") == ("reverted", "high")


# ---------------------------------------------------------------------------
# classify_correction — the full record, and the privacy contract
# ---------------------------------------------------------------------------


def test_classify_correction_main_loop_component_when_no_dispatch():
    result = corrections.classify_correction({"what": "code-edit"}, None, "revert that")
    assert result == {
        "what": "code-edit",
        "component": "main-loop",
        "shape": "reverted",
        "confidence": "high",
    }


def test_classify_correction_component_from_dispatch():
    result = corrections.classify_correction(
        {"what": "review-finding"}, ("agent", "doc-review"), "that's wrong"
    )
    assert result["component"] == "doc-review"
    assert result["what"] == "review-finding"


def test_classify_correction_what_defaults_to_other_with_no_turn_context():
    result = corrections.classify_correction({}, None, "no.")
    assert result["what"] == "other"


def test_classify_correction_none_turn_context_defaults_to_other():
    result = corrections.classify_correction(None, None, "no.")
    assert result["what"] == "other"


def test_classify_correction_never_leaks_correction_text():
    """Privacy contract (issue #2013 acceptance: "never emit correction
    text verbatim") -- only the four closed-vocabulary labels come back,
    regardless of what the correction text itself says."""
    sentinel_text = "SENTINEL_CORRECTION_TEXT_DO_NOT_LEAK: revert that"
    result = corrections.classify_correction({"what": "code-edit"}, None, sentinel_text)
    assert set(result) == {"what", "component", "shape", "confidence"}
    for value in result.values():
        assert "SENTINEL_CORRECTION_TEXT_DO_NOT_LEAK" not in str(value)


def test_all_returned_values_are_in_the_closed_vocabularies():
    result = corrections.classify_correction(
        {"what": "plan"}, ("skill", "plan"), "actually, do it differently"
    )
    assert result["what"] in corrections.WHAT_VALUES
    assert result["shape"] in corrections.SHAPE_VALUES
    assert result["confidence"] in ("high", "low")
