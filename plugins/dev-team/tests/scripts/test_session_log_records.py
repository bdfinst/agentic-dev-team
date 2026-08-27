"""Unit tests for scripts/lib/session_log/records.py (#2042, epic #2040).

Covers the JSONL iteration helper, the slimming helper, and — the acceptance
criterion this file exists to satisfy — the null-handling contract for
reading a transcript's `usage` block: a genuinely-MISSING field and a
PRESENT-but-`null` field must resolve identically. Exercised both as direct
unit tests and against the golden corpus's own missing-key/null-value
fixture records (`tests/fixtures/session_log/projects/...`), the same
records `tests/scripts/test_session_report_golden.py` locks the two
extractors' end-to-end output against.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import records

CORPUS_MAIN_TRANSCRIPT = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "session_log"
    / "projects"
    / "-tmp-golden-project"
    / "99999999-8888-7777-6666-555555555555.jsonl"
)


# ---------------------------------------------------------------------------
# usage_field / usage_fields: the null-handling contract
# ---------------------------------------------------------------------------


def test_usage_field_missing_key_reads_as_zero():
    assert records.usage_field({}, "cache_creation_input_tokens") == 0


def test_usage_field_present_null_reads_as_zero():
    assert (
        records.usage_field({"cache_creation_input_tokens": None}, "cache_creation_input_tokens")
        == 0
    )


def test_usage_field_missing_and_null_are_identical():
    missing = records.usage_field({}, "cache_read_input_tokens")
    present_null = records.usage_field({"cache_read_input_tokens": None}, "cache_read_input_tokens")
    assert missing == present_null == 0


def test_usage_field_real_value_passes_through():
    assert records.usage_field({"input_tokens": 42}, "input_tokens") == 42


def test_usage_fields_covers_all_four_with_mixed_missing_and_null():
    usage = {
        "input_tokens": 5,
        "output_tokens": None,
        # cache_creation_input_tokens omitted entirely
        "cache_read_input_tokens": 3,
    }
    assert records.usage_fields(usage) == {
        "input_tokens": 5,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 3,
    }


# ---------------------------------------------------------------------------
# usage_of: message.usage / record.usage resolution, including the corpus's
# own missing-key and explicit-null records.
# ---------------------------------------------------------------------------


def test_usage_of_prefers_message_usage():
    rec = {"message": {"usage": {"input_tokens": 1}}, "usage": {"input_tokens": 999}}
    assert records.usage_of(rec) == {"input_tokens": 1}


def test_usage_of_falls_back_to_top_level_usage():
    rec = {"message": {}, "usage": {"input_tokens": 1}}
    assert records.usage_of(rec) == {"input_tokens": 1}


def test_usage_of_missing_key_resolves_to_none():
    rec = {"message": {"content": [{"type": "text", "text": "thinking"}]}}
    assert records.usage_of(rec) is None


def test_usage_of_explicit_null_resolves_to_none():
    rec = {"message": {"usage": None}}
    assert records.usage_of(rec) is None


def test_usage_of_against_corpus_missing_and_null_records():
    lines = [
        json.loads(line)
        for line in CORPUS_MAIN_TRANSCRIPT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # record 2 (index 1): no `usage` key on the message at all
    assert "usage" not in lines[1]["message"]
    assert records.usage_of(lines[1]) is None
    # record 3 (index 2): usage explicitly null
    assert lines[2]["message"]["usage"] is None
    assert records.usage_of(lines[2]) is None
    # record 1 (index 0): a real usage block resolves through unchanged
    assert records.usage_of(lines[0]) == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 10,
    }


# ---------------------------------------------------------------------------
# iter_file_records
# ---------------------------------------------------------------------------


def test_iter_file_records_yields_every_decodable_line(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"a": 1}\nnot json\n\n{"a": 2}\n')
    assert list(records.iter_file_records(p)) == [{"a": 1}, {"a": 2}]


def test_iter_file_records_missing_file_yields_nothing(tmp_path):
    assert list(records.iter_file_records(tmp_path / "does-not-exist.jsonl")) == []


def test_iter_file_records_against_corpus():
    recs = list(records.iter_file_records(CORPUS_MAIN_TRANSCRIPT))
    assert len(recs) == 8


# ---------------------------------------------------------------------------
# slim_by_name
# ---------------------------------------------------------------------------


def test_slim_by_name_sorts_outer_and_inner_keys():
    mapping = {"z-model": {"b": 1, "a": 2}, "a-model": {"y": 1, "x": 2}}
    result = records.slim_by_name(mapping)
    assert list(result.keys()) == ["a-model", "z-model"]
    assert list(result["a-model"].keys()) == ["x", "y"]
    assert list(result["z-model"].keys()) == ["a", "b"]
