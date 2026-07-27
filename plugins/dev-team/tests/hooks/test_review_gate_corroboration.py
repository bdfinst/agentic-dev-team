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
    assert result.read_failure_reason == "missing"


def test_evaluate_readable_empty_ledger_reason_is_none(tmp_path: Path) -> None:
    _write_ledger(tmp_path, [])
    result = rgc.evaluate(tmp_path, _ANCHOR, _WINDOW, _HASH)
    assert result.agents_in_window == frozenset()
    assert result.any_dispatch_ever is False
    assert result.read_failure_reason is None


def test_evaluate_stale_evidence_distinguishes_any_dispatch_ever(tmp_path: Path) -> None:
    """Dispatches happened, just outside the window — any_dispatch_ever is
    True even though agents_in_window is empty, letting the caller pick
    the "stale" message over "no dispatch evidence"."""
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
# mtime_to_iso()
# ---------------------------------------------------------------------------


def test_mtime_to_iso_matches_shared_ts_format() -> None:
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert rgc.mtime_to_iso(dt.timestamp()) == "2026-01-01T12:00:00Z"
