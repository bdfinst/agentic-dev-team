"""Unit tests for skills/code-review/scripts/contract_failure_report.py (#1998).

Joins `contract-failures.jsonl` (written by `validate_review_output.py`)
against `agent_dispatch_ledger.py`'s deterministic `boundary-events.jsonl`
"record" rows to compute a real per-agent failure *rate* — not just a raw
count — via the shared `hooks/lib/review_dispatch_ledger.py` reader also
used by `review_value_coverage.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import contract_failure_report as cfr

_SCRIPT_PATH = _SCRIPTS_DIR / "contract_failure_report.py"


def ledger(*agents):
    return [
        {"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": agent}
        for agent in agents
    ]


def failures(*rows):
    """``rows`` is a list of (agent, shape) pairs."""
    return [{"agent": agent, "shape": shape} for agent, shape in rows]


class TestDispatchCounts:
    def test_only_ledger_hook_record_decisions_count(self):
        rows = ledger("concurrency-review") + [
            {"hook": "tdd_guard", "decision": "warn", "matched_rule": "no-test"}
        ]
        assert cfr.dispatch_counts(rows) == {"concurrency-review": 1}

    def test_rows_without_an_agent_name_are_skipped(self):
        rows = [{"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": "  "}]
        assert cfr.dispatch_counts(rows) == {}


class TestFailureCounts:
    def test_counts_and_shape_breakdown_per_agent(self):
        rows = failures(
            ("concurrency-review", "not-json"),
            ("concurrency-review", "not-json"),
            ("concurrency-review", "truncated"),
            ("doc-review", "empty"),
        )
        counts, shapes = cfr.failure_counts(rows)
        assert counts == {"concurrency-review": 3, "doc-review": 1}
        assert shapes["concurrency-review"] == {"not-json": 2, "truncated": 1}
        assert shapes["doc-review"] == {"empty": 1}

    def test_rows_without_an_agent_name_are_skipped(self):
        rows = [{"shape": "empty"}]
        counts, shapes = cfr.failure_counts(rows)
        assert counts == {}
        assert shapes == {}


class TestBuildReport:
    def test_rate_is_failures_over_dispatches(self):
        report = cfr.build_report(
            failures(("concurrency-review", "not-json")),
            ledger("concurrency-review", "concurrency-review"),
        )
        assert report["per_agent"]["concurrency-review"]["dispatches"] == 2
        assert report["per_agent"]["concurrency-review"]["failures"] == 1
        assert report["per_agent"]["concurrency-review"]["rate"] == pytest.approx(0.5)

    def test_agent_with_no_dispatch_records_has_a_none_rate(self):
        """A failure logged for an agent the ledger never recorded a dispatch
        for (e.g. an older plugin version) must not divide by zero or be
        silently dropped from the report."""
        report = cfr.build_report(failures(("ghost-review", "empty")), [])
        assert report["per_agent"]["ghost-review"]["dispatches"] == 0
        assert report["per_agent"]["ghost-review"]["failures"] == 1
        assert report["per_agent"]["ghost-review"]["rate"] is None

    def test_agent_with_dispatches_but_no_failures_has_zero_rate(self):
        report = cfr.build_report([], ledger("structure-review"))
        assert report["per_agent"]["structure-review"]["rate"] == 0

    def test_totals_aggregate_across_agents(self):
        report = cfr.build_report(
            failures(("a-review", "empty"), ("b-review", "truncated")),
            ledger("a-review", "a-review", "b-review", "b-review"),
        )
        assert report["totals"] == {"dispatches": 4, "failures": 2, "rate": pytest.approx(0.5)}

    def test_no_data_at_all_yields_empty_report(self):
        report = cfr.build_report([], [])
        assert report == {
            "totals": {"dispatches": 0, "failures": 0, "rate": None},
            "per_agent": {},
        }


class TestReadJsonl:
    def test_malformed_lines_are_skipped_but_counted(self, tmp_path):
        path = tmp_path / "stream.jsonl"
        path.write_text('{"agent": "a"}\nnot json\n{"agent": "b"}\n', encoding="utf-8")
        rows, malformed = cfr.read_jsonl(path)
        assert rows == [{"agent": "a"}, {"agent": "b"}]
        assert malformed == 1

    def test_missing_file_yields_empty_rows_and_zero_malformed(self, tmp_path):
        rows, malformed = cfr.read_jsonl(tmp_path / "missing.jsonl")
        assert rows == []
        assert malformed == 0


class TestCli:
    def test_json_output_reflects_the_two_streams(self, tmp_path):
        metrics = tmp_path / ".claude" / "metrics"
        metrics.mkdir(parents=True)
        (metrics / "contract-failures.jsonl").write_text(
            json.dumps({"agent": "concurrency-review", "shape": "not-json"}) + "\n",
            encoding="utf-8",
        )
        (metrics / "boundary-events.jsonl").write_text(
            "\n".join(
                json.dumps(row)
                for row in ledger("concurrency-review", "concurrency-review")
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--cwd", str(tmp_path), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        assert report["per_agent"]["concurrency-review"]["rate"] == pytest.approx(0.5)

    def test_text_output_reports_na_when_no_dispatches_recorded(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--cwd", str(tmp_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "n/a" in result.stdout


class TestReadOnlyMigration:
    def test_legacy_metrics_file_is_not_migrated_by_a_read_only_report(self, tmp_path):
        """`_resolve()` must pass `migrate=False` — a mere report run must
        never relocate a legacy top-level `metrics/` file into
        `.claude/metrics/`, which `artifact_paths.resolve_file`'s writer
        default (`migrate=True`) would otherwise do as a read path's side
        effect (a live telemetry writer could be mid-append when the
        migration runs)."""
        legacy_dir = tmp_path / "metrics"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "boundary-events.jsonl"
        legacy_file.write_text(
            json.dumps({"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": "x"}) + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--cwd", str(tmp_path), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )

        assert legacy_file.exists(), "a read-only report must never migrate a legacy metrics file"
        assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()
