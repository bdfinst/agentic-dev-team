"""Unit tests for hooks/lib/metrics_query.py (#1169).

Covers:
  - load_stream(): line-by-line JSONL parse, malformed-line tolerance,
    non-dict-line tolerance, missing-file tolerance.
  - filter_entries(): each filter in isolation and composed with AND.
  - facet_count(): value->count breakdown, missing-field omission.
  - --type / --gate-outcome field-name fallback priority.
  - CLI end-to-end (query + facet modes).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_LIB_SCRIPT = _LIB_DIR / "metrics_query.py"

for _p in (_HOOKS_DIR, _LIB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import metrics_query  # type: ignore[import-not-found]


def _write_jsonl(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# load_stream()
# ---------------------------------------------------------------------------


def test_load_stream_parses_each_line(tmp_path: Path) -> None:
    log = tmp_path / "metrics" / "boundary-events.jsonl"
    _write_jsonl(
        log,
        [
            {"ts": "2026-01-01T00:00:00Z", "hook": "destructive_guard", "decision": "block"},
            {"ts": "2026-01-01T00:01:00Z", "hook": "verify_guard", "decision": "warn"},
        ],
    )
    entries = list(metrics_query.load_stream(log))
    assert len(entries) == 2
    assert entries[0]["decision"] == "block"
    assert entries[1]["decision"] == "warn"


def test_load_stream_skips_malformed_lines(tmp_path: Path) -> None:
    log = tmp_path / "metrics" / "stream.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        '{"a": 1}\n'
        "not json at all\n"
        '{"a": 2}\n'
        "\n"
        '"just a string"\n'
        "42\n",
        encoding="utf-8",
    )
    entries = list(metrics_query.load_stream(log))
    assert entries == [{"a": 1}, {"a": 2}]


def test_load_stream_missing_file_yields_nothing(tmp_path: Path) -> None:
    assert list(metrics_query.load_stream(tmp_path / "metrics" / "absent.jsonl")) == []


# ---------------------------------------------------------------------------
# filter_entries() — each filter in isolation, then composed
# ---------------------------------------------------------------------------

_SAMPLE = [
    {
        "ts": "2026-01-01T00:00:00Z",
        "hook": "destructive_guard",
        "decision": "block",
        "session_id": "sess-a",
    },
    {
        "ts": "2026-01-02T00:00:00Z",
        "hook": "verify_guard",
        "decision": "warn",
        "session_id": "sess-b",
    },
    {
        "ts": "2026-01-03T00:00:00Z",
        "hook": "destructive_guard",
        "decision": "bypass",
        "session_id": "sess-a",
    },
]


def test_filter_entries_no_filters_is_identity() -> None:
    assert list(metrics_query.filter_entries(_SAMPLE)) == _SAMPLE


def test_filter_entries_by_type_uses_hook_field() -> None:
    result = list(metrics_query.filter_entries(_SAMPLE, event_type="destructive_guard"))
    assert len(result) == 2
    assert all(e["hook"] == "destructive_guard" for e in result)


def test_filter_entries_by_session() -> None:
    result = list(metrics_query.filter_entries(_SAMPLE, session_id="sess-b"))
    assert len(result) == 1
    assert result[0]["decision"] == "warn"


def test_filter_entries_by_since_is_inclusive_lower_bound() -> None:
    result = list(metrics_query.filter_entries(_SAMPLE, since="2026-01-02T00:00:00Z"))
    assert len(result) == 2
    assert {e["decision"] for e in result} == {"warn", "bypass"}


def test_filter_entries_by_gate_outcome_uses_decision_field() -> None:
    result = list(metrics_query.filter_entries(_SAMPLE, gate_outcome="block"))
    assert len(result) == 1
    assert result[0]["session_id"] == "sess-a"


def test_filter_entries_composes_all_filters_with_and() -> None:
    result = list(
        metrics_query.filter_entries(
            _SAMPLE,
            event_type="destructive_guard",
            session_id="sess-a",
            since="2026-01-02T00:00:00Z",
            gate_outcome="bypass",
        )
    )
    assert len(result) == 1
    assert result[0]["decision"] == "bypass"

    no_match = list(
        metrics_query.filter_entries(
            _SAMPLE,
            event_type="destructive_guard",
            gate_outcome="warn",
        )
    )
    assert no_match == []


# ---------------------------------------------------------------------------
# field-name fallback priority
# ---------------------------------------------------------------------------


def test_type_fallback_tries_event_before_hook() -> None:
    entries = [{"event": "gate", "hook": "should-not-match"}]
    assert list(metrics_query.filter_entries(entries, event_type="gate")) == entries
    assert list(metrics_query.filter_entries(entries, event_type="should-not-match")) == []


def test_type_fallback_uses_hook_when_event_absent() -> None:
    entries = [{"hook": "mutation-testing-smoke-gate"}]
    assert (
        list(metrics_query.filter_entries(entries, event_type="mutation-testing-smoke-gate"))
        == entries
    )


def test_type_fallback_uses_workflow_when_others_absent() -> None:
    entries = [{"workflow": "ship", "new_state": "SPEC"}]
    assert list(metrics_query.filter_entries(entries, event_type="ship")) == entries


def test_gate_outcome_fallback_tries_decision_before_outcome() -> None:
    entries = [{"decision": "block", "outcome": "should-not-match"}]
    assert list(metrics_query.filter_entries(entries, gate_outcome="block")) == entries
    assert list(metrics_query.filter_entries(entries, gate_outcome="should-not-match")) == []


def test_gate_outcome_fallback_uses_outcome_when_decision_absent() -> None:
    entries = [{"outcome": "convergence_failure"}]
    assert (
        list(metrics_query.filter_entries(entries, gate_outcome="convergence_failure"))
        == entries
    )


def test_since_fallback_uses_timestamp_when_ts_absent() -> None:
    entries = [
        {"timestamp": "2026-01-01T00:00:00Z"},
        {"timestamp": "2026-01-03T00:00:00Z"},
    ]
    result = list(metrics_query.filter_entries(entries, since="2026-01-02T00:00:00Z"))
    assert result == [{"timestamp": "2026-01-03T00:00:00Z"}]


# ---------------------------------------------------------------------------
# facet_count()
# ---------------------------------------------------------------------------


def test_facet_count_breaks_down_by_value() -> None:
    counts = metrics_query.facet_count(_SAMPLE, "hook")
    assert counts == {"destructive_guard": 2, "verify_guard": 1}


def test_facet_count_omits_entries_missing_field() -> None:
    entries = [{"a": 1}, {"a": 2, "b": "x"}]
    counts = metrics_query.facet_count(entries, "b")
    assert counts == {"x": 1}


def test_facet_count_empty_entries_is_empty_dict() -> None:
    assert metrics_query.facet_count([], "hook") == {}


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_cli_query_filters_by_type_and_session(tmp_path: Path) -> None:
    log = tmp_path / "metrics" / "boundary-events.jsonl"
    _write_jsonl(log, _SAMPLE)
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "--cwd",
            str(tmp_path),
            "--stream",
            "boundary-events",
            "--type",
            "destructive_guard",
            "--session",
            "sess-a",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert all(e["hook"] == "destructive_guard" and e["session_id"] == "sess-a" for e in parsed)


def test_cli_facet_mode_prints_value_count_pairs(tmp_path: Path) -> None:
    log = tmp_path / "metrics" / "boundary-events.jsonl"
    _write_jsonl(log, _SAMPLE)
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "--cwd",
            str(tmp_path),
            "--stream",
            "boundary-events",
            "--facet",
            "hook",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    counts = dict(ln.split("\t") for ln in lines)
    assert counts == {"destructive_guard": "2", "verify_guard": "1"}


def test_cli_missing_stream_file_returns_no_matches(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "--cwd",
            str(tmp_path),
            "--stream",
            "absent-stream",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
