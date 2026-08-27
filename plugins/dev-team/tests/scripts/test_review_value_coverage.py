"""Unit tests for skills/code-review/scripts/review_value_coverage.py (#2019).

The module exists because `review-value.jsonl` is collected by agent
instruction rather than by mechanism, so its rows over-represent rounds that
found something — #1512 measured ~100% "found something" across a 10-record
sample and nearly pruned lenses on it.

What these tests protect is the *refusal*: the check must decline to certify a
sample that cannot answer the question, and it must decline for the right
reason. A validity gate that returns `usable` on thin, skewed, or
under-collected data is worse than no gate — it launders the artifact into a
decision. So every failing verdict is pinned individually, and the boundaries
either side of each threshold are pinned too.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import review_value_coverage as rvc


def ledger(*agents):
    """Deterministic dispatch rows, one per agent name given."""
    return [
        {
            "hook": "agent_dispatch_ledger",
            "decision": "record",
            "tool": "Agent",
            "matched_rule": agent,
        }
        for agent in agents
    ]


def value_rows(n, *, outcome="fixed", agents=("correctness-review",)):
    return [
        {"agents_run": list(agents), "outcome": outcome, "source": "code-review"}
        for _ in range(n)
    ]


class TestLedgerDenominator:
    def test_only_dispatch_records_count(self):
        """The ledger stream is shared — guards write to it too. Counting a
        `tdd_guard` warn as a review dispatch would inflate the denominator and
        make collection look worse than it is."""
        rows = ledger("correctness-review") + [
            {"hook": "tdd_guard", "decision": "warn", "matched_rule": "no-test"},
            {"hook": "pre_tool_guard", "decision": "block", "matched_rule": "x"},
        ]
        assert rvc.dispatch_counts(rows) == {"correctness-review": 1}

    def test_non_record_decisions_from_the_ledger_hook_are_excluded(self):
        rows = [
            {
                "hook": "agent_dispatch_ledger",
                "decision": "warn",
                "matched_rule": "correctness-review",
            }
        ]
        assert rvc.dispatch_counts(rows) == {}

    def test_rows_without_an_agent_name_are_skipped(self):
        rows = [
            {"hook": "agent_dispatch_ledger", "decision": "record"},
            {"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": ""},
            {"hook": "agent_dispatch_ledger", "decision": "record", "matched_rule": "  "},
        ]
        assert rvc.dispatch_counts(rows) == {}

    def test_agent_names_are_counted_per_dispatch(self):
        rows = ledger("correctness-review", "correctness-review", "doc-review")
        assert rvc.dispatch_counts(rows) == {
            "correctness-review": 2,
            "doc-review": 1,
        }


class TestNoopShare:
    def test_skipped_rounds_are_excluded_from_the_denominator(self):
        """A `skipped` backstop did not run, so it is neither a finding nor a
        quiet round. Counting it as "not a no-op" would depress the very ratio
        the bias check reads, making a skewed sample look worse than it is —
        and counting it as a no-op would make one look better."""
        rows = value_rows(1, outcome="no-op") + value_rows(3, outcome="skipped")
        assert rvc.noop_share(rows) == 1.0

    def test_all_skipped_yields_none_rather_than_zero(self):
        """Zero would read as "no quiet rounds ever logged" and trip the bias
        verdict. Nothing ran, so the ratio is undefined, not zero."""
        assert rvc.noop_share(value_rows(3, outcome="skipped")) is None

    def test_share_is_computed_over_run_rounds(self):
        rows = value_rows(1, outcome="no-op") + value_rows(3, outcome="fixed")
        assert rvc.noop_share(rows) == pytest.approx(0.25)

    def test_rows_without_an_outcome_are_ignored(self):
        assert rvc.noop_share([{"agents_run": ["x"]}]) is None


class TestVerdicts:
    def test_no_rows_against_real_dispatches_is_no_data(self):
        report = rvc.assess([], ledger("correctness-review", "doc-review"))
        assert report["verdict"] == "no-data"
        assert report["usable_for_pruning"] is False
        assert "0 logged" in report["reasons"][0]

    def test_undercollected_outranks_thinness(self):
        """Both conditions hold; the verdict must name the one that cannot be
        fixed by waiting. More rows do not repair a biased selection."""
        report = rvc.assess(value_rows(1), ledger(*(["correctness-review"] * 10)))
        assert report["verdict"] == "undercollected"
        assert any("coverage" in r for r in report["reasons"])
        assert any("row floor" in r for r in report["reasons"])

    def test_well_covered_but_thin_sample_is_insufficient(self):
        report = rvc.assess(value_rows(10), ledger(*(["correctness-review"] * 10)))
        assert report["verdict"] == "insufficient"

    def test_large_well_covered_sample_with_no_quiet_rounds_is_biased(self):
        """#1512's exact shape at scale: plenty of rows, every one of them a
        find. That is the artifact, not a perfect panel."""
        n = rvc.MIN_ROWS
        report = rvc.assess(
            value_rows(n, outcome="fixed"),
            ledger(*(["correctness-review"] * n)),
        )
        assert report["verdict"] == "biased"
        assert any("no-op share" in r for r in report["reasons"])

    def test_a_healthy_looking_sample_with_no_ledger_is_unverifiable(self):
        """Regression: `assess` skipped the coverage branch when there was no
        denominator, so a sample that is thick and well-balanced but whose
        collection completeness is unknowable returned `usable`. That made the
        check incapable of failing on #1512's own data, which predates the
        ledger hook — a gate that cannot fail on the case it was built for."""
        rows = value_rows(90, outcome="fixed") + value_rows(40, outcome="no-op")
        report = rvc.assess(rows, [])
        assert report["verdict"] == "unverifiable"
        assert report["usable_for_pruning"] is False
        assert any("cannot be verified" in r for r in report["reasons"])

    def test_a_healthy_sample_is_usable(self):
        rows = value_rows(80, outcome="fixed") + value_rows(40, outcome="no-op")
        report = rvc.assess(rows, ledger(*(["correctness-review"] * 130)))
        assert report["verdict"] == "usable"
        assert report["usable_for_pruning"] is True
        assert report["reasons"] == []


class TestThresholdBoundaries:
    """Each floor is an inequality someone will later tune. Pin both sides so a
    change to a constant cannot silently flip a verdict."""

    def test_coverage_exactly_at_the_floor_passes(self):
        rows = (
            value_rows(rvc.MIN_ROWS - 20, outcome="fixed")
            + value_rows(20, outcome="no-op")
        )
        dispatch_total = int(len(rows) / rvc.MIN_COVERAGE)
        report = rvc.assess(rows, ledger(*(["correctness-review"] * dispatch_total)))
        assert report["totals"]["coverage"] == pytest.approx(rvc.MIN_COVERAGE)
        assert report["verdict"] == "usable"

    def test_coverage_just_below_the_floor_fails(self):
        rows = value_rows(rvc.MIN_ROWS)
        dispatch_total = int(len(rows) / rvc.MIN_COVERAGE) + 1
        report = rvc.assess(rows, ledger(*(["correctness-review"] * dispatch_total)))
        assert report["verdict"] == "undercollected"

    def test_row_count_exactly_at_the_floor_is_not_insufficient(self):
        rows = (
            value_rows(rvc.MIN_ROWS - 10, outcome="fixed")
            + value_rows(10, outcome="no-op")
        )
        report = rvc.assess(rows, ledger(*(["correctness-review"] * rvc.MIN_ROWS)))
        assert report["verdict"] == "usable"

    def test_one_row_below_the_floor_is_insufficient(self):
        rows = (
            value_rows(rvc.MIN_ROWS - 11, outcome="fixed")
            + value_rows(10, outcome="no-op")
        )
        report = rvc.assess(rows, ledger(*(["correctness-review"] * rvc.MIN_ROWS)))
        assert report["verdict"] == "insufficient"


class TestMalformedLinesAreCountedNotSwallowed:
    def test_unparseable_lines_are_reported(self, tmp_path):
        """Silently dropping unreadable telemetry is the same class of defect
        this module exists to surface, so the count must reach the report."""
        metrics = tmp_path / ".claude" / "metrics"
        metrics.mkdir(parents=True)
        (metrics / rvc.VALUE_STREAM).write_text(
            '{"agents_run":["a"],"outcome":"no-op"}\nnot json\n[1,2]\n',
            encoding="utf-8",
        )
        (metrics / rvc.LEDGER_STREAM).write_text("{oops\n", encoding="utf-8")
        report = rvc.run(tmp_path)
        assert report["malformed_lines"][rvc.VALUE_STREAM] == 2
        assert report["malformed_lines"][rvc.LEDGER_STREAM] == 1

    def test_missing_files_do_not_raise(self, tmp_path):
        report = rvc.run(tmp_path)
        assert report["verdict"] == "no-data"
        assert report["totals"]["dispatches"] == 0


class TestPerLensReconciliation:
    def test_a_lens_dispatched_but_never_logged_shows_zero_coverage(self):
        report = rvc.assess(
            value_rows(2, agents=("correctness-review",)),
            ledger("correctness-review", "doc-review", "doc-review"),
        )
        per_lens = report["per_lens"]
        assert per_lens["doc-review"] == {
            "dispatches": 2,
            "logged": 0,
            "coverage": 0.0,
        }
        assert per_lens["correctness-review"]["logged"] == 2

    def test_a_lens_logged_without_a_ledger_record_reports_none_coverage(self):
        """Coverage is undefined, not infinite, when the denominator is zero —
        an older plugin version predates the ledger hook."""
        report = rvc.assess(value_rows(1, agents=("ghost-review",)), [])
        assert report["per_lens"]["ghost-review"]["coverage"] is None


class TestCli:
    def _run(self, cwd, *args):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "review_value_coverage.py"),
             "--cwd", str(cwd), *args],
            capture_output=True, text=True, timeout=60, check=False,
        )

    def test_strict_exits_nonzero_on_an_unusable_sample(self, tmp_path):
        result = self._run(tmp_path, "--strict")
        assert result.returncode == 1

    def test_default_mode_is_informational(self, tmp_path):
        result = self._run(tmp_path)
        assert result.returncode == 0
        assert "NO-DATA" in result.stdout

    def test_json_output_is_parseable(self, tmp_path):
        result = self._run(tmp_path, "--json")
        assert result.returncode == 0
        assert json.loads(result.stdout)["verdict"] == "no-data"

    def test_strict_exits_zero_on_a_usable_sample(self, tmp_path):
        """The gate must be capable of passing, or it is not a gate."""
        metrics = tmp_path / ".claude" / "metrics"
        metrics.mkdir(parents=True)
        rows = value_rows(90, outcome="fixed") + value_rows(40, outcome="no-op")
        metrics.joinpath(rvc.VALUE_STREAM).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        metrics.joinpath(rvc.LEDGER_STREAM).write_text(
            "".join(json.dumps(r) + "\n" for r in ledger(*(["correctness-review"] * 140))),
            encoding="utf-8",
        )
        result = self._run(tmp_path, "--strict")
        assert result.returncode == 0, result.stdout + result.stderr


class TestReadOnlyMigration:
    def test_legacy_metrics_file_is_not_migrated_by_a_read_only_report(self, tmp_path):
        """#2059: `_resolve()` must pass `migrate=False`, matching
        `contract_failure_report.py`'s own `_resolve()` — a mere report run
        must never relocate a legacy top-level `metrics/` file into
        `.claude/metrics/`, which `resolve_stream`'s writer default
        (`migrate=True`) would otherwise do as a read path's side effect."""
        legacy_dir = tmp_path / "metrics"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / rvc.VALUE_STREAM
        legacy_file.write_text(
            json.dumps({"agents_run": ["x"], "outcome": "no-op", "source": "code-review"}) + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "review_value_coverage.py"),
             "--cwd", str(tmp_path), "--json"],
            capture_output=True, text=True, timeout=60, check=True,
        )

        assert legacy_file.exists(), "a read-only report must never migrate a legacy metrics file"
        assert not (tmp_path / ".claude" / "metrics" / rvc.VALUE_STREAM).exists()
