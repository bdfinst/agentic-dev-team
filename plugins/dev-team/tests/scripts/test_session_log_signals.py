"""Unit tests for scripts/lib/session_log/signals.py (#2044, epic #2040).

Covers the 7 per-record accumulator functions and the agent-bucket
machinery (context_tokens/context_per_dispatch, #2029) unified from the two
forked extractors — see the module's own docstring for the full
per-function reconciliation table and the deliberate golden-output changes
this slice makes.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import signals

# ---------------------------------------------------------------------------
# agent-bucket machinery
# ---------------------------------------------------------------------------


def test_new_agent_bucket_shape():
    bucket = signals.new_agent_bucket()
    assert bucket == {
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "messages": 0,
        "dispatches": 0,
    }


def test_finalize_agent_buckets_computes_context_tokens():
    by_agent_type = {
        "main": {
            "input_tokens": 100,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 10,
            "output_tokens": 50,
            "messages": 1,
            "dispatches": 0,
        }
    }
    out = signals.finalize_agent_buckets(by_agent_type)
    assert out["main"]["context_tokens"] == 130  # input + cache_creation + cache_read
    # no dispatch -> per-dispatch figure must read as absent, not 0 (a
    # never-dispatched agent must not rank as the cheapest in a table).
    assert out["main"]["context_per_dispatch"] is None


def test_finalize_agent_buckets_context_per_dispatch_divides_by_dispatches():
    by_agent_type = {
        "correctness-review": {
            "input_tokens": 60,
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 5,
            "output_tokens": 30,
            "messages": 1,
            "dispatches": 1,
        }
    }
    out = signals.finalize_agent_buckets(by_agent_type)
    assert out["correctness-review"]["context_tokens"] == 70
    assert out["correctness-review"]["context_per_dispatch"] == 70


def test_merge_agent_buckets_sums_raw_fields():
    dest: dict = {}
    signals.merge_agent_buckets(dest, {"main": {**signals.new_agent_bucket(), "messages": 2}})
    signals.merge_agent_buckets(dest, {"main": {**signals.new_agent_bucket(), "messages": 3}})
    assert dest["main"]["messages"] == 5


def test_merge_agent_buckets_preserves_pre_2010_int_digest_at_zero():
    # A digest written before the bucket shape existed carries an int (a
    # message count). Merging it as tokens must not silently corrupt the
    # total.
    dest: dict = {}
    signals.merge_agent_buckets(dest, {"main": 3})
    assert dest["main"] == signals.new_agent_bucket()


# ---------------------------------------------------------------------------
# accumulate_token_signals — the shared core (no cost, no skill)
# ---------------------------------------------------------------------------


def test_accumulate_token_signals_sums_into_totals_and_by_model():
    tokens_total = Counter()
    by_model: dict = defaultdict(Counter)
    usage_fields = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 10,
    }
    signals.accumulate_token_signals(usage_fields, "claude-sonnet-5", tokens_total, by_model)
    assert tokens_total["input_tokens"] == 100
    assert by_model["claude-sonnet-5"]["input_tokens"] == 100


def test_accumulate_token_signals_no_model_skips_by_model():
    tokens_total = Counter()
    by_model: dict = defaultdict(Counter)
    signals.accumulate_token_signals(
        {"input_tokens": 5, "output_tokens": 0, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0},
        None,
        tokens_total,
        by_model,
    )
    assert tokens_total["input_tokens"] == 5
    assert by_model == {}


# ---------------------------------------------------------------------------
# accumulate_skill_agent_signals
# ---------------------------------------------------------------------------


def test_accumulate_skill_agent_signals_counts_skill_dispatch():
    skills_invoked = Counter()
    agent_dispatches = Counter()
    active = {"skill": None, "agent": None}
    content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "dev-team:plan"}}]
    signals.accumulate_skill_agent_signals(None, content, skills_invoked, agent_dispatches, active)
    assert skills_invoked["plan"] == 1
    assert active["skill"] == "plan"


def test_accumulate_skill_agent_signals_counts_agent_dispatch():
    skills_invoked = Counter()
    agent_dispatches = Counter()
    active = {"skill": None, "agent": None}
    content = [{"type": "tool_use", "name": "Agent", "input": {"subagent_type": "dev-team:correctness-review"}}]
    signals.accumulate_skill_agent_signals(None, content, skills_invoked, agent_dispatches, active)
    assert agent_dispatches["correctness-review"] == 1
    assert active["agent"] == "correctness-review"


def test_accumulate_skill_agent_signals_last_tracks_the_single_most_recent_dispatch():
    # #2013: active["last"] collapses the two independently-sticky
    # skill/agent pointers into ONE (kind, name) answer -- whichever was
    # dispatched most recently -- for session_log.corrections' single
    # "component" field.
    skills_invoked = Counter()
    agent_dispatches = Counter()
    active = {"skill": None, "agent": None}
    skill_content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "dev-team:plan"}}]
    signals.accumulate_skill_agent_signals(
        None, skill_content, skills_invoked, agent_dispatches, active
    )
    assert active["last"] == ("skill", "plan")

    agent_content = [
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "dev-team:doc-review"}}
    ]
    signals.accumulate_skill_agent_signals(
        None, agent_content, skills_invoked, agent_dispatches, active
    )
    # Both skill/agent pointers stay sticky independently (unchanged
    # behavior), but "last" moved to the MORE RECENT agent dispatch.
    assert active["skill"] == "plan"
    assert active["last"] == ("agent", "doc-review")


def test_accumulate_skill_agent_signals_last_absent_before_any_dispatch():
    skills_invoked = Counter()
    agent_dispatches = Counter()
    active = {"skill": None, "agent": None}
    signals.accumulate_skill_agent_signals(None, None, skills_invoked, agent_dispatches, active)
    assert "last" not in active


def test_accumulate_skill_agent_signals_legacy_skill_fallback():
    skills_invoked = Counter()
    agent_dispatches = Counter()
    active = {"skill": None, "agent": None}
    signals.accumulate_skill_agent_signals("legacy-skill", None, skills_invoked, agent_dispatches, active)
    assert skills_invoked["legacy-skill"] == 1


# ---------------------------------------------------------------------------
# track_tool_call / classify_tool_result — the isinstance(bid, str) guard
# ---------------------------------------------------------------------------


def test_track_tool_call_records_pending_tool():
    pending_tool: dict = {}
    tool_calls = Counter()
    signals.track_tool_call({"name": "Read", "id": "call1"}, pending_tool, tool_calls)
    assert tool_calls["Read"] == 1
    assert pending_tool["call1"] == "Read"


def test_track_tool_call_ignores_non_string_id():
    # The guarded form (the maintainer extractor's, kept as canonical): a
    # non-string id is never used as a dict key, unlike a bare `if bid:`.
    pending_tool: dict = {}
    tool_calls = Counter()
    signals.track_tool_call({"name": "Read", "id": 12345}, pending_tool, tool_calls)
    assert tool_calls["Read"] == 1
    assert pending_tool == {}


def test_classify_tool_result_counts_error_by_tool():
    pending_tool = {"call1": "Edit"}
    tool_errors = Counter()
    error_counts = Counter()
    signals.classify_tool_result(
        {"is_error": True, "tool_use_id": "call1", "content": "old_string not found"},
        pending_tool,
        tool_errors,
        error_counts,
    )
    assert tool_errors["Edit"] == 1
    assert error_counts["failed_edits"] == 1


def test_classify_tool_result_ignores_non_string_tool_use_id():
    pending_tool = {"call1": "Edit"}
    tool_errors = Counter()
    error_counts = Counter()
    signals.classify_tool_result(
        {"is_error": True, "tool_use_id": ["not", "a", "string"], "content": ""},
        pending_tool,
        tool_errors,
        error_counts,
    )
    assert tool_errors["?"] == 1


def test_classify_tool_result_detects_permission_denial():
    pending_tool: dict = {}
    tool_errors = Counter()
    error_counts = Counter()
    signals.classify_tool_result(
        {"is_error": True, "tool_use_id": "x", "content": "Permission denied"},
        pending_tool,
        tool_errors,
        error_counts,
    )
    assert error_counts["permission_denials"] == 1


# ---------------------------------------------------------------------------
# track_edit / track_bash / new_thread — the flat per-thread simplification
# ---------------------------------------------------------------------------


def test_track_edit_counts_per_file_basename():
    thread = signals.new_thread()
    edits_per_file = Counter()
    signals.track_edit(
        {"name": "Edit", "input": {"file_path": "/repo/src/foo.py"}}, edits_per_file, thread
    )
    assert edits_per_file["foo.py"] == 1
    assert thread["edited_since_verify"] is True


def test_track_bash_detects_repeated_verify_run():
    thread = signals.new_thread()
    bash_signal_counts = Counter()
    block = {"name": "Bash", "input": {"command": "npm test"}}
    signals.track_bash(block, bash_signal_counts, thread)
    signals.track_bash(block, bash_signal_counts, thread)
    assert bash_signal_counts["repeated_verify_runs"] == 1


def test_track_bash_edit_between_verify_runs_resets_the_streak():
    thread = signals.new_thread()
    edits_per_file = Counter()
    bash_signal_counts = Counter()
    verify_block = {"name": "Bash", "input": {"command": "npm test"}}
    edit_block = {"name": "Edit", "input": {"file_path": "/repo/x.py"}}
    signals.track_bash(verify_block, bash_signal_counts, thread)
    signals.track_edit(edit_block, edits_per_file, thread)
    signals.track_bash(verify_block, bash_signal_counts, thread)
    assert bash_signal_counts["repeated_verify_runs"] == 0


def test_track_bash_detects_commit_and_bypass():
    thread = signals.new_thread()
    bash_signal_counts = Counter()
    signals.track_bash(
        {"name": "Bash", "input": {"command": "git commit --no-verify -m x"}},
        bash_signal_counts,
        thread,
    )
    assert bash_signal_counts["commit_attempts"] == 1
    assert bash_signal_counts["commit_bypasses"] == 1


def test_sibling_agents_sharing_a_thread_do_not_cross_contaminate():
    """The #1991 regression the old sid-keying existed to prevent: two
    'sibling' threads (each freshly created via new_thread(), as extract()
    does per file) must not see each other's verify-loop state, proving the
    flat per-thread dict is safe WITHOUT sid-keying as long as it's reset
    per file — see signals.py's module docstring."""
    bash_signal_counts = Counter()
    verify_block = {"name": "Bash", "input": {"command": "git diff --cached"}}
    for _ in range(3):
        thread = signals.new_thread()  # fresh per "file", like extract()
        signals.track_bash(verify_block, bash_signal_counts, thread)
    assert bash_signal_counts["repeated_verify_runs"] == 0


# ---------------------------------------------------------------------------
# detect_correction_turn
# ---------------------------------------------------------------------------


def test_detect_correction_turn_true_for_correction_keyword():
    rec = {"type": "user"}
    content = [{"type": "text", "text": "no, that's wrong"}]
    assert signals.detect_correction_turn(rec, content) is True


def test_detect_correction_turn_false_for_tool_result_envelope():
    rec = {"type": "user"}
    content = [{"type": "tool_result", "content": "no matches found"}]
    assert signals.detect_correction_turn(rec, content) is False


def test_detect_correction_turn_false_for_non_user_record():
    rec = {"type": "assistant"}
    assert signals.detect_correction_turn(rec, "no") is False
