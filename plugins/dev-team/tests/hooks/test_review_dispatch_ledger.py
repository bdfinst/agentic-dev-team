"""Unit tests for hooks/lib/review_dispatch_ledger.py (#1998).

Extracted from `review_value_coverage.py` and `contract_failure_report.py`,
which both hand-rolled an identical `read_jsonl()` + `dispatch_counts()` pair
over `boundary-events.jsonl`'s `hook == "agent_dispatch_ledger"` / `decision
== "record"` rows before this module existed. Covers the predicate itself
plus the `migrate=False` read-only resolution default.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import review_dispatch_ledger as rdl  # type: ignore[import-not-found]


def ledger(*agents):
    return [
        {"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": agent}
        for agent in agents
    ]


class TestDispatchCounts:
    def test_only_ledger_hook_record_decisions_count(self):
        rows = ledger("concurrency-review") + [
            {"hook": "tdd_guard", "decision": "warn", "matched_rule": "no-test"}
        ]
        assert rdl.dispatch_counts(rows) == {"concurrency-review": 1}

    def test_rows_without_an_agent_name_are_skipped(self):
        rows = [{"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": "  "}]
        assert rdl.dispatch_counts(rows) == {}

    def test_non_record_decision_is_excluded(self):
        rows = [{"hook": "agent_dispatch_ledger", "decision": "attempt", "matched_rule": "doc-review"}]
        assert rdl.dispatch_counts(rows) == {}

    def test_counts_accumulate_across_repeated_dispatches(self):
        rows = ledger("doc-review", "doc-review", "doc-review")
        assert rdl.dispatch_counts(rows) == {"doc-review": 3}


class TestReadJsonl:
    def test_malformed_lines_are_skipped_but_counted(self, tmp_path):
        path = tmp_path / "stream.jsonl"
        path.write_text('{"agent": "a"}\nnot json\n{"agent": "b"}\n', encoding="utf-8")
        rows, malformed = rdl.read_jsonl(path)
        assert rows == [{"agent": "a"}, {"agent": "b"}]
        assert malformed == 1

    def test_missing_file_yields_empty_rows_and_zero_malformed(self, tmp_path):
        rows, malformed = rdl.read_jsonl(tmp_path / "missing.jsonl")
        assert rows == []
        assert malformed == 0

    def test_non_dict_json_lines_are_counted_as_malformed(self, tmp_path):
        path = tmp_path / "stream.jsonl"
        path.write_text('["not", "a", "dict"]\n{"agent": "a"}\n', encoding="utf-8")
        rows, malformed = rdl.read_jsonl(path)
        assert rows == [{"agent": "a"}]
        assert malformed == 1


class TestResolveStream:
    def test_default_migrate_false_never_migrates_a_legacy_file(self, tmp_path):
        legacy_dir = tmp_path / "metrics"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "boundary-events.jsonl"
        legacy_file.write_text("", encoding="utf-8")

        path = rdl.resolve_stream("metrics", "boundary-events.jsonl", tmp_path)

        assert path == tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
        assert not path.exists()
        assert legacy_file.exists()

    def test_migrate_true_is_available_for_a_writer(self, tmp_path):
        legacy_dir = tmp_path / "metrics"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "some-stream.jsonl"
        legacy_file.write_text("row\n", encoding="utf-8")

        path = rdl.resolve_stream("metrics", "some-stream.jsonl", tmp_path, migrate=True)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == "row\n"
