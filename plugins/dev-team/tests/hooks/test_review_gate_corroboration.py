"""Unit tests for hooks/lib/review_gate_corroboration.py (#1461).

Covers:
  - distinct_review_agent_dispatches(): in-window distinct-agent extraction,
    window exclusion, duplicate-dispatch dedup, missing/unreadable-ledger
    fail-closed behavior.
  - evaluate(): the fuller result — any_dispatch_ever (stale-vs-never
    distinction) and read_failure_reason (missing vs unreadable vs None).
  - mtime_to_iso(): epoch-float -> the shared %Y-%m-%dT%H:%M:%SZ format.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_LIB_DIR = _PLUGIN_DIR / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import review_gate_corroboration as rgc  # type: ignore[import-not-found]

_ANCHOR = "2026-01-01T12:00:00Z"  # before_ts
_WINDOW = 1800  # 30 minutes, matching the plan's pinned WINDOW_SECONDS
_HASH = "test-subject-hash-123"  # the gate's current review_gate_hash() value


def _write_ledger(tmp_path: Path, entries: list) -> None:
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _record(ts: str, agent: str, subject_hash: str = _HASH) -> dict:
    return {
        "ts": ts,
        "hook": "agent_dispatch_ledger",
        "tool": "Agent",
        "decision": "record",
        "matched_rule": agent,
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }


def _dispatch_failure(ts: str, agent: str, subject_hash: str = _HASH) -> dict:
    """Matches the shape `boundary_events.py`'s `--event dispatch-failure`
    CLI writes (#1763): hook="code-review", tool="Skill",
    decision="dispatch-failure", matched_rule=<agent name>."""
    return {
        "ts": ts,
        "hook": "code-review",
        "tool": "Skill",
        "decision": "dispatch-failure",
        "matched_rule": agent,
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }


# ---------------------------------------------------------------------------
# distinct_review_agent_dispatches() — in-window distinct extraction
# ---------------------------------------------------------------------------


def test_two_distinct_agents_in_window_both_returned(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:50:00Z", "security-review"),
            _record("2026-01-01T11:55:00Z", "structure-review"),
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review", "structure-review"}


def test_entries_outside_window_excluded(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:00:00Z", "security-review"),  # 1h before anchor, outside 30m window
            _record("2026-01-01T11:55:00Z", "structure-review"),  # inside window
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"structure-review"}


def test_duplicate_dispatches_of_same_agent_count_once(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:50:00Z", "security-review"),
            _record("2026-01-01T11:55:00Z", "security-review"),
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}


def test_missing_ledger_returns_empty_set(tmp_path: Path) -> None:
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == set()


def test_malformed_individual_lines_are_tolerated_not_fatal(tmp_path: Path) -> None:
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps(_record("2026-01-01T11:55:00Z", "security-review")) + "\n"
        "not json at all\n",
        encoding="utf-8",
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}


def test_boundary_at_exact_window_edge_is_inclusive(tmp_path: Path) -> None:
    # Exactly window_seconds before the anchor — inclusive per since/until semantics.
    _write_ledger(tmp_path, [_record("2026-01-01T11:30:00Z", "security-review")])
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}


def test_entry_at_anchor_timestamp_itself_is_included(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_record(_ANCHOR, "security-review")])
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}


def test_non_record_decision_from_same_hook_is_ignored(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [{"ts": "2026-01-01T11:55:00Z", "hook": "agent_dispatch_ledger", "decision": "warn", "matched_rule": "x"}],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == set()


def test_entries_from_other_hooks_are_ignored(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [{"ts": "2026-01-01T11:55:00Z", "hook": "destructive_guard", "decision": "warn", "matched_rule": "x"}],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == set()


# ---------------------------------------------------------------------------
# evaluate() — the fuller result (any_dispatch_ever, read_failure_reason)
# ---------------------------------------------------------------------------


def test_evaluate_missing_ledger_reason_is_missing(tmp_path: Path) -> None:
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is False
    assert result.same_subject_dispatch_ever is False
    assert result.read_failure_reason == "missing"


def test_evaluate_readable_empty_ledger_reason_is_none(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is False
    assert result.same_subject_dispatch_ever is False
    assert result.read_failure_reason is None


def test_evaluate_stale_evidence_distinguishes_any_dispatch_ever(tmp_path: Path) -> None:
    """Dispatches happened, just outside the window, for THIS SAME
    subject_hash — both any_dispatch_ever and same_subject_dispatch_ever are
    True even though agents_in_window is empty, letting the caller pick the
    "stale" message over "no dispatch evidence"."""
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T10:00:00Z", "security-review"),
            _record("2026-01-01T10:05:00Z", "structure-review"),
        ],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is True
    assert result.same_subject_dispatch_ever is True
    assert result.read_failure_reason is None


def test_evaluate_different_subject_in_window_is_not_same_subject_stale(
    tmp_path: Path,
) -> None:
    """#1461 second security re-review: a genuine, RECENT dispatch for a
    DIFFERENT subject_hash must set any_dispatch_ever True but
    same_subject_dispatch_ever False — the caller needs this distinction to
    avoid reporting "outside the window" (factually wrong; it's inside the
    window, just for unrelated content) for this case."""
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:55:00Z", "security-review", subject_hash="other-changeset"),
        ],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is True
    assert result.same_subject_dispatch_ever is False
    assert result.read_failure_reason is None


def test_evaluate_unreadable_ledger_reason_is_unreadable(tmp_path: Path) -> None:
    """Undecodable bytes (not valid UTF-8) make the whole file unreadable —
    distinct from tolerated malformed *individual* JSON lines within an
    otherwise-decodable file (see test_malformed_individual_lines_are_tolerated_not_fatal)."""
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"\xff\xfe\x00not valid utf-8\x80\x81")
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is False
    assert result.same_subject_dispatch_ever is False
    assert result.read_failure_reason == "unreadable"


# ---------------------------------------------------------------------------
# has_doc_only_exemption()
# ---------------------------------------------------------------------------


def _doc_only_exempt(ts: str, subject_hash: str = _HASH) -> dict:
    return {
        "ts": ts,
        "hook": "code-review",
        "tool": "Skill",
        "decision": "bypass",
        "matched_rule": "doc-only-review-exempt",
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }


def test_doc_only_exemption_inside_window_is_true(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_doc_only_exempt("2026-01-01T11:55:00Z")])
    assert rgc.has_doc_only_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is True


def test_doc_only_exemption_outside_window_is_false(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_doc_only_exempt("2026-01-01T10:00:00Z")])
    assert rgc.has_doc_only_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is False


def test_no_doc_only_exemption_is_false(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_record("2026-01-01T11:55:00Z", "security-review")])
    assert rgc.has_doc_only_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is False


def test_doc_only_exemption_missing_ledger_is_false(tmp_path: Path) -> None:
    assert rgc.has_doc_only_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is False


# ---------------------------------------------------------------------------
# has_single_agent_exemption()
# ---------------------------------------------------------------------------


def _single_agent_exempt(ts: str, subject_hash: str = _HASH) -> dict:
    return {
        "ts": ts,
        "hook": "code-review",
        "tool": "Skill",
        "decision": "bypass",
        "matched_rule": "single-agent-review-exempt",
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }


def test_single_agent_exemption_inside_window_is_true(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [_single_agent_exempt("2026-01-01T11:55:00Z")])
    assert rgc.has_single_agent_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is True


def test_single_agent_exemption_wrong_hash_is_false(tmp_path: Path) -> None:
    """#1461 security review: an exemption for a DIFFERENT changeset must not
    satisfy this one."""
    _write_ledger(
        tmp_path, [_single_agent_exempt("2026-01-01T11:55:00Z", subject_hash="other-hash")]
    )
    assert rgc.has_single_agent_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is False


def test_doc_only_exemption_is_not_confused_with_single_agent_exemption(
    tmp_path: Path,
) -> None:
    _write_ledger(tmp_path, [_doc_only_exempt("2026-01-01T11:55:00Z")])
    assert rgc.has_single_agent_exemption(tmp_path, _ANCHOR, _WINDOW, _HASH) is False


# ---------------------------------------------------------------------------
# subject_hash binding (#1461 security review) — closes the "review A,
# commit B" bypass a corroboration mechanism with no subject binding would
# have: any genuine review within the recency window, of ANY changeset,
# would otherwise satisfy the gate for an unrelated one.
# ---------------------------------------------------------------------------


def test_dispatches_for_a_different_subject_hash_do_not_count(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:50:00Z", "security-review", subject_hash="other-changeset"),
            _record("2026-01-01T11:55:00Z", "structure-review", subject_hash="other-changeset"),
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == set()


def test_mixed_subject_hashes_only_matching_ones_count(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:50:00Z", "security-review", subject_hash=_HASH),
            _record("2026-01-01T11:55:00Z", "structure-review", subject_hash="other-changeset"),
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}


# Note: the "different subject_hash in window" scenario is covered by
# test_evaluate_different_subject_in_window_is_not_same_subject_stale above,
# which also asserts the same_subject_dispatch_ever distinction added in a
# later security re-review round.


def test_event_missing_subject_hash_field_entirely_does_not_count(tmp_path: Path) -> None:
    """An event written before this field existed (or by some other bug)
    must never match — only an explicit, equal subject_hash counts."""
    stale_shape = {
        "ts": "2026-01-01T11:55:00Z",
        "hook": "agent_dispatch_ledger",
        "tool": "Agent",
        "decision": "record",
        "matched_rule": "security-review",
        "plugin_version": "0.0.0",
    }
    _write_ledger(tmp_path, [stale_shape])
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == set()


# ---------------------------------------------------------------------------
# Registry re-validation (#1461 security review) — defense in depth: even a
# ledger entry with the right hash, right hook, right timing must still name
# a REAL registered review agent, re-checked against the live registry at
# read time (not just trusted from the write side).
# ---------------------------------------------------------------------------


def test_unregistered_agent_name_is_excluded_even_with_correct_hash(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _record("2026-01-01T11:50:00Z", "security-review"),
            _record("2026-01-01T11:55:00Z", "totally-fake-review"),
        ],
    )
    result = rgc.distinct_review_agent_dispatches(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result == {"security-review"}
    assert "totally-fake-review" not in result


# ---------------------------------------------------------------------------
# dispatch_failure_agents (#1763) — unbounded-by-window negative evidence,
# with supersession by a later "record" for the same agent+hash.
# ---------------------------------------------------------------------------


def test_dispatch_failure_event_is_detected_for_matching_hash_and_agent(
    tmp_path: Path,
) -> None:
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_later_record_supersedes_earlier_dispatch_failure_regardless_of_window(
    tmp_path: Path,
) -> None:
    """Both events are outside the 30-minute window relative to the anchor —
    supersession must still apply, since `dispatch_failure_agents` is
    unbounded by `window_seconds` (unlike `agents_in_window`)."""
    _write_ledger(
        tmp_path,
        [
            _dispatch_failure("2026-01-01T09:00:00Z", "security-review"),
            _record("2026-01-01T09:30:00Z", "security-review"),
        ],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset()


def test_dispatch_failure_older_than_window_with_no_supersession_still_counts(
    tmp_path: Path,
) -> None:
    """Direct proof of the unbounded-by-window behavior: a dispatch-failure
    event 2 hours before the anchor (well outside the 30-minute window),
    with no later superseding "record" for the same agent+hash, still
    counts as negative evidence."""
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T10:00:00Z", "security-review")])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})
    # And it is genuinely outside the window that bounds agents_in_window.
    assert result.agents_in_window == frozenset()


def test_dispatch_failure_for_different_subject_hash_is_not_counted(
    tmp_path: Path,
) -> None:
    _write_ledger(
        tmp_path,
        [_dispatch_failure("2026-01-01T11:55:00Z", "security-review", subject_hash="other-hash")],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset()


def test_unregistered_agent_name_excluded_from_dispatch_failure_agents(
    tmp_path: Path,
) -> None:
    _write_ledger(
        tmp_path,
        [
            _dispatch_failure("2026-01-01T11:55:00Z", "security-review"),
            _dispatch_failure("2026-01-01T11:56:00Z", "totally-fake-review"),
        ],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})
    assert "totally-fake-review" not in result.dispatch_failure_agents


def test_missing_ledger_fails_closed_for_dispatch_failure_agents(tmp_path: Path) -> None:
    """A missing ledger means "cannot prove no dispatch failure exists" —
    treated the same as "a failure exists" (non-empty), never as an
    empty/all-clear set."""
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE
    assert result.dispatch_failure_agents != frozenset()


def test_unreadable_ledger_fails_closed_for_dispatch_failure_agents(tmp_path: Path) -> None:
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"\xff\xfe\x00not valid utf-8\x80\x81")
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE
    assert result.dispatch_failure_agents != frozenset()


def test_registry_read_failure_fails_closed_for_dispatch_failure_agents_not_open(
    tmp_path: Path, monkeypatch
) -> None:
    """A broken registry read must never collapse to an empty
    dispatch_failure_agents set — that would read as "provably no dispatch
    failures" (an all-clear) when it actually means "cannot tell". This is
    the opposite-of-agents_in_window direction: narrowing agents_in_window
    via an empty registered set is safe; narrowing dispatch_failure_agents
    the same way would WIDEN the gate instead (#1763 security/correctness
    review) — a ledger read failure already exercises the sentinel above;
    this exercises the DISTINCT registry-read-failure path."""
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    monkeypatch.setattr(rgc, "_registered_agents", lambda: None)
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE
    assert result.dispatch_failure_agents != frozenset()
    # Positive evidence still fails closed the OLD (safe) way: narrowed to
    # empty, never widened.
    assert result.agents_in_window == frozenset()


def test_registered_agents_returns_none_for_a_real_missing_agents_dir(
    tmp_path: Path, monkeypatch
) -> None:
    """#1763 correctness/security review (both reviewers independently found
    this): the REAL failure mode — a missing/unreadable `agents/` directory
    — must be checked explicitly, because `Path.glob()` never raises for it;
    an earlier version of this fix only handled an exception, which this
    real path never throws, so it silently returned an empty frozenset
    instead of None. Exercises the actual function, not a monkeypatched
    stand-in for it."""
    missing = tmp_path / "no-such-agents-dir"
    monkeypatch.setattr(rgc, "_agents_dir", lambda: missing)
    assert rgc._registered_agents() is None


def test_registered_agents_returns_none_for_zero_registered_files(
    tmp_path: Path, monkeypatch
) -> None:
    """An `agents/` directory that exists but contains zero `*-review.md`
    files is a broken install, never a legitimate empty registry — must
    also report None, not an empty frozenset."""
    empty_dir = tmp_path / "agents"
    empty_dir.mkdir()
    monkeypatch.setattr(rgc, "_agents_dir", lambda: empty_dir)
    assert rgc._registered_agents() is None


def test_missing_real_agents_dir_fails_closed_end_to_end(
    tmp_path: Path, monkeypatch
) -> None:
    """End-to-end: a real (unmocked) missing agents/ directory must still
    produce the fail-closed sentinel through evaluate(), not just through
    the internal _registered_agents() unit above."""
    missing = tmp_path / "no-such-agents-dir"
    monkeypatch.setattr(rgc, "_agents_dir", lambda: missing)
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE


def test_registry_read_failure_fails_closed_for_normalized_dispatch_failure_agents(
    tmp_path: Path, monkeypatch
) -> None:
    _write_ledger(
        tmp_path,
        [_dispatch_failure_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash")],
    )
    monkeypatch.setattr(rgc, "_registered_agents", lambda: None)
    _agents, dispatch_failure_agents = rgc.distinct_normalized_dispatches(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash"
    )
    assert dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE


def test_dispatch_failure_entry_with_timestamp_field_instead_of_ts_is_not_dropped(
    tmp_path: Path,
) -> None:
    """Every shipped emitter stamps `ts`, but this module's OTHER reads
    (`filter_entries`) resolve via metrics_query's `ts`/`timestamp`
    fallback — the dispatch-failure timeline must use the same resolution,
    not a bare `entry.get("ts")`, or a `timestamp`-keyed entry (a hand-edited
    or foreign-stream ledger) silently vanishes from negative evidence."""
    entry = _dispatch_failure("2026-01-01T11:55:00Z", "security-review")
    entry["timestamp"] = entry.pop("ts")
    _write_ledger(tmp_path, [entry])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_ts_less_dispatch_failure_is_never_superseded_by_a_ts_bearing_record(
    tmp_path: Path,
) -> None:
    """#1763 correctness review: a ts-less failure must default to the
    MAXIMUM sort key (never superseded), not the minimum — an earlier draft
    used `ts or ""` for both entry kinds, which let ANY ts-bearing record
    silently supersede a ts-less failure, exactly backwards from the
    "ordered last, never superseded" guarantee this function documents."""
    entry = _dispatch_failure("2026-01-01T11:55:00Z", "security-review")
    del entry["ts"]  # no usable ts at all, not even under the "timestamp" alias
    _write_ledger(
        tmp_path,
        [entry, _record("2026-01-01T11:56:00Z", "security-review")],  # later, real ts
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_ts_less_record_never_supersedes_a_real_dispatch_failure(tmp_path: Path) -> None:
    """The opposite default direction from the case above: a ts-less RECORD
    must never supersede a real, ts-bearing failure — the safe default for
    positive evidence we cannot chronologically place."""
    record_entry = _record("2026-01-01T11:56:00Z", "security-review")
    del record_entry["ts"]
    _write_ledger(
        tmp_path,
        [_dispatch_failure("2026-01-01T11:55:00Z", "security-review"), record_entry],
    )
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_non_string_ts_value_is_skipped_not_a_crash(tmp_path: Path) -> None:
    """#1763 correctness review: a corrupt line with a non-str ts (e.g. a
    hand-edited or foreign-stream ledger with a raw int/float timestamp)
    must degrade to "no usable ts", never raise — mixing an int and a str
    in the same sort comparison would crash the whole read, making one
    corrupt line fatal against this module's own "never fatal" promise."""
    entry = _dispatch_failure("2026-01-01T11:55:00Z", "security-review")
    entry["ts"] = 1767225600  # raw int, not a string
    _write_ledger(tmp_path, [entry])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


# ---------------------------------------------------------------------------
# distinct_normalized_dispatches() — new (agents_in_window,
# dispatch_failure_agents) 2-tuple return (#1763).
# ---------------------------------------------------------------------------


def _record_normalized(ts: str, agent: str, subject_hash_normalized: str) -> dict:
    return {
        "ts": ts,
        "hook": "agent_dispatch_ledger",
        "tool": "Agent",
        "decision": "record",
        "matched_rule": agent,
        "plugin_version": "0.0.0",
        "subject_hash_normalized": subject_hash_normalized,
    }


def _dispatch_failure_normalized(ts: str, agent: str, subject_hash_normalized: str) -> dict:
    """Matches the shape `boundary_events.py`'s `--event dispatch-failure`
    CLI writes when given `--subject-hash-normalized` (#1763)."""
    return {
        "ts": ts,
        "hook": "code-review",
        "tool": "Skill",
        "decision": "dispatch-failure",
        "matched_rule": agent,
        "plugin_version": "0.0.0",
        "subject_hash_normalized": subject_hash_normalized,
    }


def test_distinct_normalized_dispatches_detects_a_real_dispatch_failure(
    tmp_path: Path,
) -> None:
    """Direct proof the normalized read path surfaces genuine data, not
    only the read-failure sentinel — closing the stale "Known gap" this
    function's docstring used to claim (#1763 correctness review)."""
    _write_ledger(
        tmp_path,
        [_dispatch_failure_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash-1")],
    )
    _agents, dispatch_failure_agents = rgc.distinct_normalized_dispatches(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1"
    )
    assert dispatch_failure_agents == frozenset({"security-review"})


def test_distinct_normalized_dispatches_supersession(tmp_path: Path) -> None:
    _write_ledger(
        tmp_path,
        [
            _dispatch_failure_normalized("2026-01-01T09:00:00Z", "security-review", "norm-hash-1"),
            _record_normalized("2026-01-01T09:30:00Z", "security-review", "norm-hash-1"),
        ],
    )
    _agents, dispatch_failure_agents = rgc.distinct_normalized_dispatches(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1"
    )
    assert dispatch_failure_agents == frozenset()


def test_distinct_normalized_dispatches_returns_two_tuple_of_frozensets(
    tmp_path: Path,
) -> None:
    _write_ledger(
        tmp_path, [_record_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash-1")]
    )
    result = rgc.distinct_normalized_dispatches(tmp_path, _ANCHOR, _WINDOW, "norm-hash-1")
    assert result == (frozenset({"security-review"}), frozenset())
    assert isinstance(result, tuple)
    assert isinstance(result[0], frozenset)
    assert isinstance(result[1], frozenset)


def test_distinct_normalized_dispatches_missing_ledger_fails_closed(tmp_path: Path) -> None:
    result = rgc.distinct_normalized_dispatches(tmp_path, _ANCHOR, _WINDOW, "norm-hash-1")
    assert result == (frozenset(), rgc._UNPROVABLE_DISPATCH_FAILURE)


def test_distinct_normalized_dispatches_empty_hash_fails_closed_on_negative_evidence(
    tmp_path: Path,
) -> None:
    """#1763 security review: an unbindable query (empty normalized hash)
    cannot prove absence of failure — the negative-evidence element must be
    the fail-closed sentinel, never an all-clear empty set, matching the
    read-failure branch's own posture."""
    _write_ledger(
        tmp_path, [_record_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash-1")]
    )
    result = rgc.distinct_normalized_dispatches(tmp_path, _ANCHOR, _WINDOW, "")
    assert result == (frozenset(), rgc._UNPROVABLE_DISPATCH_FAILURE)


# ---------------------------------------------------------------------------
# evaluate_cosmetic_carry_forward() — single-read-pass evidence for the
# normalized-hash binding plus every raw-hash binding (#1836 perf fix and
# the security/correctness findings raised against its first draft: no
# ledger/registry read-count regression, and the sentinel must never mix
# into a union with real agent names).
# ---------------------------------------------------------------------------


def test_evaluate_cosmetic_carry_forward_missing_ledger_fails_closed(tmp_path: Path) -> None:
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", ("raw-a", "raw-b")
    )
    assert result == (frozenset(), "missing", rgc._UNPROVABLE_DISPATCH_FAILURE)


def test_evaluate_cosmetic_carry_forward_unreadable_ledger_fails_closed(
    tmp_path: Path,
) -> None:
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"\xff\xfe\x00not valid utf-8\x80\x81")
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", ("raw-a",)
    )
    assert result.read_failure_reason == "unreadable"
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE


def test_evaluate_cosmetic_carry_forward_registry_failure_is_pure_sentinel_not_mixed(
    tmp_path: Path, monkeypatch
) -> None:
    """A registry-read failure must make the WHOLE result the sentinel —
    never mixed with the real agents_in_window a positive normalized-hash
    dispatch would otherwise contribute."""
    _write_ledger(
        tmp_path, [_record_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash-1")]
    )
    monkeypatch.setattr(rgc, "_registered_agents", lambda: None)
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", ("raw-a",)
    )
    assert result.read_failure_reason is None
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE


def test_evaluate_cosmetic_carry_forward_falsy_normalized_hash_never_mixes_sentinel_with_real_raw_failure(
    tmp_path: Path,
) -> None:
    """#1836 security/correctness review regression test: a falsy
    `subject_hash_normalized` contributes the unprovable sentinel for its
    own slot, but a genuine raw-hash dispatch-failure elsewhere must not get
    unioned WITH that sentinel into a mixed set — the caller's `==` sentinel
    check in `pre_commit_review.py` cannot detect a mixed set, and
    `_dispatch_failure_message` would render the sentinel string as if it
    were a real agent name. The whole result must be EXACTLY the sentinel."""
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    result = rgc.evaluate_cosmetic_carry_forward(tmp_path, _ANCHOR, _WINDOW, "", (_HASH,))
    assert result.agents_in_window == frozenset()
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE
    assert "security-review" not in result.dispatch_failure_agents


def test_evaluate_cosmetic_carry_forward_falsy_raw_hash_fails_closed_not_silently_skipped(
    tmp_path: Path,
) -> None:
    """#1836 correctness/security review: a falsy raw hash cannot bind any
    evidence, so it cannot prove the ABSENCE of a dispatch failure either —
    silently SKIPPING it would read as an all-clear it never earned. Must
    make the whole result unprovable, not a no-op."""
    _write_ledger(
        tmp_path, [_record_normalized("2026-01-01T11:55:00Z", "security-review", "norm-hash-1")]
    )
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", ("", "raw-b")
    )
    assert result.dispatch_failure_agents == rgc._UNPROVABLE_DISPATCH_FAILURE


def test_evaluate_cosmetic_carry_forward_dispatch_failure_bound_only_to_second_raw_hash(
    tmp_path: Path,
) -> None:
    """Closes the fail-open gap test-review flagged: a dispatch-failure
    recorded against ONLY the second raw hash (modeling `current_hash` when
    `stored_raw` carries no evidence) must still surface — not just the
    first raw hash checked."""
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", ("unrelated-raw-hash", _HASH)
    )
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_evaluate_cosmetic_carry_forward_duplicate_raw_hashes_counted_once(
    tmp_path: Path,
) -> None:
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review")])
    once = rgc.evaluate_cosmetic_carry_forward(tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", (_HASH,))
    twice = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", (_HASH, _HASH)
    )
    assert once.dispatch_failure_agents == twice.dispatch_failure_agents == frozenset(
        {"security-review"}
    )


def test_evaluate_cosmetic_carry_forward_bare_str_raw_hash_is_not_iterated_as_characters(
    tmp_path: Path,
) -> None:
    """A bare `str` passed as `raw_hashes` (the natural mistake for a caller
    with only one raw hash) must be treated as ONE hash, never iterated
    character-by-character — the latter would silently match nothing and
    produce a false all-clear."""
    _write_ledger(tmp_path, [_dispatch_failure("2026-01-01T11:55:00Z", "security-review", _HASH)])
    result = rgc.evaluate_cosmetic_carry_forward(tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", _HASH)
    assert result.dispatch_failure_agents == frozenset({"security-review"})


def test_evaluate_cosmetic_carry_forward_positive_evidence_only_from_normalized_binding(
    tmp_path: Path,
) -> None:
    """A dispatch recorded only under a raw hash (never the normalized
    hash) must never contribute to `agents_in_window` — positive evidence
    stays scoped to the single normalized-hash binding."""
    _write_ledger(tmp_path, [_record("2026-01-01T11:55:00Z", "security-review", _HASH)])
    result = rgc.evaluate_cosmetic_carry_forward(
        tmp_path, _ANCHOR, _WINDOW, "norm-hash-1", (_HASH,)
    )
    assert result.agents_in_window == frozenset()


def test_evaluate_cosmetic_carry_forward_reads_ledger_exactly_once(
    tmp_path: Path, monkeypatch
) -> None:
    """#1836 perf fix: one `_read_ledger` call must answer the
    normalized-hash query AND every raw-hash binding, not one read per
    binding. State-based assertions on the returned evidence can't observe
    this by construction — this spy is the only thing that pins the
    property the rewrite exists for."""
    _write_ledger(tmp_path, [_record_normalized("2026-01-01T11:55:00Z", "security-review", "n1")])
    calls = []
    real_read_ledger = rgc._read_ledger

    def _spy(cwd):
        calls.append(cwd)
        return real_read_ledger(cwd)

    monkeypatch.setattr(rgc, "_read_ledger", _spy)
    rgc.evaluate_cosmetic_carry_forward(tmp_path, _ANCHOR, _WINDOW, "n1", ("raw-a", "raw-b"))
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# mtime_to_iso()
# ---------------------------------------------------------------------------


def test_mtime_to_iso_matches_shared_ts_format() -> None:
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert rgc.mtime_to_iso(dt.timestamp()) == "2026-01-01T12:00:00Z"
