"""Pytest tests for csharp_stryker_net_slice_runner.py — first-class
slicing + configurable slice-level parallelism for Stryker.NET (#561).

Follows the same hermetic, monkeypatch-the-subprocess-boundary strategy as
tests/scripts/test_csharp_stryker_net_wrapper.py: no real ``dotnet``/
``dotnet-stryker`` invocation, no filesystem PATH shims.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

WRAPPER_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(WRAPPER_DIR))

import csharp_stryker_net_slice_runner as runner
import csharp_stryker_net_wrapper as wrapper


# =============================================================================
# load_slices_config — validation
# =============================================================================
class TestLoadSlicesConfig:
    def test_loads_valid_config(self, tmp_path):
        cfg = tmp_path / "mutation-slices.json"
        cfg.write_text(
            json.dumps(
                {
                    "slices": [
                        {"name": "validators", "mutate": "**/Validators/**/*.cs"},
                        {"name": "services", "mutate": "**/Services/**/*.cs"},
                    ]
                }
            )
        )
        slices = runner.load_slices_config(cfg)
        assert [s["name"] for s in slices] == ["validators", "services"]

    def test_accepts_reserved_667_fields(self, tmp_path):
        cfg = tmp_path / "mutation-slices.json"
        cfg.write_text(
            json.dumps(
                {
                    "slices": [
                        {
                            "name": "validators",
                            "mutate": "**/Validators/**/*.cs",
                            "kind": "logic",
                            "mutation-level": "Basic",
                            "exclude-converged": True,
                        }
                    ]
                }
            )
        )
        slices = runner.load_slices_config(cfg)
        assert slices[0]["kind"] == "logic"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            runner.load_slices_config(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path):
        cfg = tmp_path / "bad.json"
        cfg.write_text("{not json")
        with pytest.raises(ValueError, match="not valid JSON"):
            runner.load_slices_config(cfg)

    def test_empty_slices_array_raises(self, tmp_path):
        cfg = tmp_path / "empty.json"
        cfg.write_text(json.dumps({"slices": []}))
        with pytest.raises(ValueError, match="non-empty"):
            runner.load_slices_config(cfg)

    def test_missing_required_field_raises(self, tmp_path):
        cfg = tmp_path / "missing.json"
        cfg.write_text(json.dumps({"slices": [{"name": "validators"}]}))
        with pytest.raises(ValueError, match="missing required field"):
            runner.load_slices_config(cfg)

    def test_duplicate_name_raises(self, tmp_path):
        cfg = tmp_path / "dup.json"
        cfg.write_text(
            json.dumps(
                {
                    "slices": [
                        {"name": "a", "mutate": "**/A/**/*.cs"},
                        {"name": "a", "mutate": "**/B/**/*.cs"},
                    ]
                }
            )
        )
        with pytest.raises(ValueError, match="duplicate slice name"):
            runner.load_slices_config(cfg)


# =============================================================================
# resolve_slice_selection — --slice <name> / --slice all
# =============================================================================
class TestResolveSliceSelection:
    def setup_method(self):
        self.configured = [
            {"name": "validators", "mutate": "**/Validators/**/*.cs"},
            {"name": "services", "mutate": "**/Services/**/*.cs"},
        ]

    def test_all_returns_every_slice_in_order(self):
        assert runner.resolve_slice_selection(self.configured, "all") == self.configured

    def test_named_slice_returns_single_match(self):
        result = runner.resolve_slice_selection(self.configured, "services")
        assert len(result) == 1
        assert result[0]["name"] == "services"

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="no slice named"):
            runner.resolve_slice_selection(self.configured, "nope")


# =============================================================================
# Per-slice output layout + terminal-report detection (resume support)
# =============================================================================
class TestOutputLayout:
    def test_slice_report_path_shape(self, tmp_path):
        p = runner.slice_report_path(tmp_path, "validators")
        assert p == tmp_path / "slice-validators" / "reports" / "mutation-report.json"


class TestIsTerminalReport:
    def test_missing_file_is_not_terminal(self, tmp_path):
        assert runner.is_terminal_report(tmp_path / "nope.json") is False

    def test_invalid_json_is_not_terminal(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text("{truncated")
        assert runner.is_terminal_report(p) is False

    def test_empty_files_map_is_not_terminal(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(json.dumps({"files": {}}))
        assert runner.is_terminal_report(p) is False

    def test_populated_files_map_is_terminal(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(
            json.dumps({"files": {"src/Foo.cs": {"mutants": [{"status": "Killed"}]}}})
        )
        assert runner.is_terminal_report(p) is True

    def test_non_dict_json_is_not_terminal(self, tmp_path):
        p = tmp_path / "report.json"
        p.write_text(json.dumps([1, 2, 3]))
        assert runner.is_terminal_report(p) is False


class TestPartitionTerminalSlices:
    def test_skips_slices_with_terminal_report(self, tmp_path):
        slices = [
            {"name": "validators", "mutate": "x"},
            {"name": "services", "mutate": "y"},
        ]
        report = runner.slice_report_path(tmp_path, "validators")
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps({"files": {"a.cs": {"mutants": [{"status": "Killed"}]}}})
        )
        to_run, skipped = runner.partition_terminal_slices(
            slices, tmp_path, force=False
        )
        assert [s["name"] for s in to_run] == ["services"]
        assert [s["name"] for s in skipped] == ["validators"]

    def test_force_reruns_terminal_slices(self, tmp_path):
        slices = [{"name": "validators", "mutate": "x"}]
        report = runner.slice_report_path(tmp_path, "validators")
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps({"files": {"a.cs": {"mutants": [{"status": "Killed"}]}}})
        )
        to_run, skipped = runner.partition_terminal_slices(slices, tmp_path, force=True)
        assert [s["name"] for s in to_run] == ["validators"]
        assert skipped == []

    def test_non_terminal_report_is_not_skipped(self, tmp_path):
        slices = [{"name": "validators", "mutate": "x"}]
        report = runner.slice_report_path(tmp_path, "validators")
        report.parent.mkdir(parents=True)
        report.write_text("{crashed mid-write")
        to_run, skipped = runner.partition_terminal_slices(
            slices, tmp_path, force=False
        )
        assert [s["name"] for s in to_run] == ["validators"]
        assert skipped == []


# =============================================================================
# Total-worker resolution: --total-workers N|auto
# =============================================================================
class TestResolveTotalWorkers:
    def test_auto_is_max_2_cores_div_2(self):
        assert runner.resolve_total_workers("auto", 12) == 6
        assert runner.resolve_total_workers(None, 12) == 6

    def test_auto_floors_at_2_on_low_core_count(self):
        assert runner.resolve_total_workers("auto", 2) == 2
        assert runner.resolve_total_workers("auto", 1) == 2

    def test_auto_falls_back_when_cpu_count_is_none(self):
        assert runner.resolve_total_workers("auto", None) == 2

    def test_explicit_integer_is_used_verbatim(self):
        assert runner.resolve_total_workers("10", 12) == 10


class TestTotalWorkerCeilingCheck:
    def test_within_ceiling_is_allowed_silently(self):
        allowed, msg = runner.total_worker_ceiling_check(6, 12, force=False)
        assert allowed is True
        assert msg is None

    def test_over_ceiling_without_force_is_refused(self):
        allowed, msg = runner.total_worker_ceiling_check(20, 12, force=False)
        assert allowed is False
        assert "exceeds" in msg
        assert "--force" in msg

    def test_over_ceiling_with_force_is_allowed_with_warning(self):
        allowed, msg = runner.total_worker_ceiling_check(20, 12, force=True)
        assert allowed is True
        assert "warning" in msg
        assert "--force" in msg


# =============================================================================
# Worker allocation: --parallel-slices / --per-slice-concurrency hints
# =============================================================================
class TestResolveWorkerAllocation:
    def test_default_split_allocates_slices_first(self):
        # 6 total workers, 7 slices -> min(6,7)=6 parallel slices, remainder 1 each.
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, None, None, force=False
        )
        assert parallel == 6
        assert per_slice == 1
        assert msg is None

    def test_default_split_with_fewer_slices_than_workers(self):
        # 6 total workers, 2 slices -> 2 parallel slices, 3 per-slice each.
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 2, None, None, force=False
        )
        assert parallel == 2
        assert per_slice == 3

    def test_explicit_parallel_slices_only_derives_per_slice(self):
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, 3, None, force=False
        )
        assert parallel == 3
        assert per_slice == 2

    def test_explicit_per_slice_only_derives_parallel(self):
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, None, 2, force=False
        )
        assert parallel == 3
        assert per_slice == 2

    def test_both_explicit_within_ceiling_is_allowed(self):
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, 3, 2, force=False
        )
        assert (parallel, per_slice) == (3, 2)
        assert msg is None

    def test_both_explicit_over_ceiling_without_force_errors(self):
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, 6, 5, force=False
        )
        assert (parallel, per_slice) == (6, 5)
        assert "exceeds" in msg
        assert "error" in msg

    def test_both_explicit_over_ceiling_with_force_warns(self):
        parallel, per_slice, msg = runner.resolve_worker_allocation(
            6, 7, 6, 5, force=True
        )
        assert (parallel, per_slice) == (6, 5)
        assert "warning" in msg


# =============================================================================
# Per-slice Stryker config generation
# =============================================================================
class TestBuildSliceStrykerConfig:
    def test_defaults_coverage_analysis_to_per_test(self):
        cfg = runner.build_slice_stryker_config(
            {}, {"name": "x", "mutate": "**/X/**/*.cs"}
        )
        assert cfg["coverage-analysis"] == "perTest"
        assert cfg["mutate"] == ["**/X/**/*.cs"]

    def test_respects_existing_coverage_analysis_escape_hatch(self):
        cfg = runner.build_slice_stryker_config(
            {"coverage-analysis": "off"}, {"name": "x", "mutate": "**/X/**/*.cs"}
        )
        assert cfg["coverage-analysis"] == "off"

    def test_wraps_string_mutate_glob_in_a_list(self):
        cfg = runner.build_slice_stryker_config(
            {}, {"name": "x", "mutate": "**/X/**/*.cs"}
        )
        assert isinstance(cfg["mutate"], list)

    def test_preserves_base_config_keys(self):
        cfg = runner.build_slice_stryker_config(
            {"reporters": ["dots", "json"]}, {"name": "x", "mutate": "**/X/**/*.cs"}
        )
        assert cfg["reporters"] == ["dots", "json"]


class TestWriteSliceConfig:
    def test_writes_wrapped_stryker_config_shape(self, tmp_path):
        path = runner.write_slice_config(tmp_path, "validators", {"mutate": ["x"]})
        assert path == tmp_path / "slice-validators" / "stryker-config.json"
        data = json.loads(path.read_text())
        assert data == {"stryker-config": {"mutate": ["x"]}}


# =============================================================================
# Native report summarizing + aggregate roll-up
# =============================================================================
class TestSummarizeNativeReport:
    def test_counts_mutants_by_status(self):
        native = {
            "files": {
                "a.cs": {
                    "mutants": [
                        {"status": "Killed"},
                        {"status": "Killed"},
                        {"status": "Survived"},
                    ]
                },
                "b.cs": {"mutants": [{"status": "NoCoverage"}]},
            }
        }
        counts = runner.summarize_native_report(native)
        assert counts == {"Killed": 2, "Survived": 1, "NoCoverage": 1}

    def test_empty_report_yields_empty_counts(self):
        assert runner.summarize_native_report({"files": {}}) == {}


class TestAggregateSliceSummaries:
    def test_sums_totals_across_slices(self):
        summaries = {
            "validators": {"Killed": 10, "Survived": 2},
            "services": {"Killed": 5, "Survived": 1, "NoCoverage": 1},
        }
        agg = runner.aggregate_slice_summaries(summaries)
        assert agg["totals"] == {"Killed": 15, "Survived": 3, "NoCoverage": 1}
        assert agg["slices"] == summaries
        assert agg["schema_version"] == 1
        assert agg["tool"] == "stryker-net"

    def test_computes_honest_score(self):
        summaries = {"a": {"Killed": 8, "Survived": 2}}
        agg = runner.aggregate_slice_summaries(summaries)
        assert agg["honest_score"] == 80.0

    def test_honest_score_is_zero_when_no_mutants(self):
        agg = runner.aggregate_slice_summaries({})
        assert agg["honest_score"] == 0.0


class TestWriteAggregateReport:
    def test_writes_to_output_root(self, tmp_path):
        path = runner.write_aggregate_report(tmp_path, {"totals": {}})
        assert path == tmp_path / "aggregate-mutation-report.json"
        assert json.loads(path.read_text()) == {"totals": {}}


# =============================================================================
# Rolled-up progress reporting
# =============================================================================
class TestFormatProgressLine:
    def test_renders_positional_status_per_slice(self):
        order = ["a", "b", "c", "d"]
        states = {"a": "done", "b": "done", "c": "running", "d": "queued"}
        line = runner.format_progress_line(order, states)
        assert line == (
            "slice 1/4 done, slice 2/4 done, slice 3/4 running, slice 4/4 queued"
        )

    def test_defaults_to_queued_for_unknown_slice(self):
        line = runner.format_progress_line(["a"], {})
        assert line == "slice 1/1 queued"


# =============================================================================
# main() — end-to-end fleet orchestration
# =============================================================================
@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    root = tmp_path
    sln = root / "Foo.sln"
    sln.write_text("solution stub")
    monkeypatch.setenv("DOTNET_ROOT", str(root / "fake-dotnet-root"))
    monkeypatch.chdir(root)

    cfg = root / "mutation-slices.json"
    cfg.write_text(
        json.dumps(
            {
                "slices": [
                    {"name": "validators", "mutate": "**/Validators/**/*.cs"},
                    {"name": "services", "mutate": "**/Services/**/*.cs"},
                ]
            }
        )
    )

    class Ctx:
        pass

    ctx = Ctx()
    ctx.root = root
    ctx.sln = sln
    ctx.sln_hidden = Path(str(sln) + ".stryker-hidden")
    ctx.slices_config = cfg
    ctx.build_calls = []
    ctx.stryker_calls = []
    ctx.sln_present_during_stryker = []
    return ctx


def _install_fakes(monkeypatch, ctx, *, exit_code=0):
    def fake_build(project, cwd=None):
        ctx.build_calls.append(project)
        return 0

    def fake_run_stryker(stryker_bin, stryker_args, logfile):
        ctx.sln_present_during_stryker.append(ctx.sln.exists())
        ctx.stryker_calls.append(
            {
                "stryker_bin": stryker_bin,
                "stryker_args": list(stryker_args),
                "logfile": str(logfile),
            }
        )
        # Simulate a completed report for aggregate roll-up.
        logfile.parent.mkdir(parents=True, exist_ok=True)
        report_dir = logfile.parent / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "mutation-report.json").write_text(
            json.dumps({"files": {"a.cs": {"mutants": [{"status": "Killed"}]}}})
        )
        return exit_code

    monkeypatch.setattr(wrapper, "build_project", fake_build)
    monkeypatch.setattr(wrapper, "run_stryker", fake_run_stryker)
    # Critical: also stub out signal-handler installation, same precaution
    # taken in test_csharp_stryker_net_wrapper.py's _install_fakes(). Without
    # this, main() calls signal.signal(SIGINT, ...) which globally replaces
    # the process's SIGINT handler for the rest of the pytest session.
    monkeypatch.setattr(wrapper, "_install_signal_handlers", list)


def run_slice_runner(hermetic, *extra_args):
    args = [
        "--slices-config",
        str(hermetic.slices_config),
        "--sln",
        str(hermetic.sln),
        "--output-root",
        str(hermetic.root / "StrykerOutput"),
        "--stryker-bin",
        "fake-stryker-bin",
        *extra_args,
    ]
    return runner.main(args)


class TestMainSingleSlice:
    def test_runs_named_slice_and_restores_sln(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        rc = run_slice_runner(hermetic, "--slice", "validators")
        assert rc == 0
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()
        assert len(hermetic.stryker_calls) == 1

    def test_hides_sln_before_stryker_and_restores_after(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        run_slice_runner(hermetic, "--slice", "validators")
        assert hermetic.sln_present_during_stryker == [False]

    def test_unknown_slice_name_errors(self, hermetic, monkeypatch, capsys):
        _install_fakes(monkeypatch, hermetic)
        rc = run_slice_runner(hermetic, "--slice", "nope")
        assert rc == 2
        assert "no slice named" in capsys.readouterr().err
        assert hermetic.build_calls == []

    def test_writes_per_slice_report_path(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        run_slice_runner(hermetic, "--slice", "validators")
        report = (
            hermetic.root
            / "StrykerOutput"
            / "slice-validators"
            / "reports"
            / "mutation-report.json"
        )
        assert report.exists()


class TestMainAllSlices:
    def test_runs_all_slices_hiding_sln_once(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        assert rc == 0
        assert len(hermetic.stryker_calls) == 2
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()

    def test_aggregate_report_written(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        agg_path = hermetic.root / "StrykerOutput" / "aggregate-mutation-report.json"
        assert agg_path.exists()
        agg = json.loads(agg_path.read_text())
        assert agg["totals"] == {"Killed": 2}
        assert set(agg["slices"].keys()) == {"validators", "services"}

    def test_resume_skips_terminal_slices(self, hermetic, monkeypatch, capsys):
        _install_fakes(monkeypatch, hermetic)
        run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        hermetic.stryker_calls.clear()
        hermetic.build_calls.clear()
        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        assert rc == 0
        assert hermetic.stryker_calls == []
        out = capsys.readouterr().out
        assert "SKIPPED validators" in out
        assert "SKIPPED services" in out

    def test_force_reruns_terminal_slices(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        hermetic.stryker_calls.clear()
        rc = run_slice_runner(
            hermetic, "--slice", "all", "--total-workers", "2", "--force"
        )
        assert rc == 0
        assert len(hermetic.stryker_calls) == 2

    def test_refuses_over_ceiling_without_force(self, hermetic, monkeypatch, capsys):
        _install_fakes(monkeypatch, hermetic)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "20")
        assert rc == 2
        assert "exceeds" in capsys.readouterr().err
        assert hermetic.stryker_calls == []

    def test_allows_over_ceiling_with_force(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        rc = run_slice_runner(
            hermetic, "--slice", "all", "--total-workers", "20", "--force"
        )
        assert rc == 0
        assert len(hermetic.stryker_calls) == 2

    def test_stryker_nonzero_exit_propagates_and_still_restores_sln(
        self, hermetic, monkeypatch
    ):
        _install_fakes(monkeypatch, hermetic, exit_code=1)
        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")
        assert rc == 1
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()


# =============================================================================
# Signal handling (#732) — main() must install the same SIGINT/SIGTERM
# handlers the wrapper installs, so that Ctrl-C / a process-manager SIGTERM
# during the parallel fleet run terminates every in-flight slice's Stryker
# subprocess (tracked in wrapper._RUNNING_STRYKER_PROCS, shared across all
# ThreadPoolExecutor worker threads) instead of leaving them orphaned.
# =============================================================================
class TestMainSignalHandling:
    def test_installs_and_restores_signal_handlers_around_the_fleet_run(
        self, hermetic, monkeypatch
    ):
        install_calls = []
        restore_calls = []
        sentinel_previous = [("sentinel", None)]

        def fake_install():
            install_calls.append(1)
            return sentinel_previous

        def fake_restore(previous):
            restore_calls.append(previous)

        _install_fakes(monkeypatch, hermetic)
        # Override the no-op stub from _install_fakes with call-recording
        # spies so we can assert main() actually wires these in.
        monkeypatch.setattr(wrapper, "_install_signal_handlers", fake_install)
        monkeypatch.setattr(wrapper, "_restore_signal_handlers", fake_restore)

        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")

        assert rc == 0
        assert install_calls == [1]
        assert restore_calls == [sentinel_previous]

    def test_interrupt_during_fleet_run_returns_130_and_restores_sln(
        self, hermetic, monkeypatch
    ):
        """Simulates a KeyboardInterrupt escaping the fleet run — exactly
        what happens when the wrapper's real signal handler fires mid-run
        (it terminates every tracked Stryker subprocess, then raises
        KeyboardInterrupt). main() must catch it, still restore the fleet-
        level .sln, and return a conventional interrupted exit code — never
        let it propagate uncaught (which would skip the aggregate step in an
        uncontrolled way) and never hang waiting on the still-running slice.
        """
        call_count = {"n": 0}
        call_lock = threading.Lock()

        def fake_build(project, cwd=None):
            return 0

        def fake_run_stryker(stryker_bin, stryker_args, logfile):
            with call_lock:
                call_count["n"] += 1
                first = call_count["n"] == 1
            if first:
                raise KeyboardInterrupt("signal 2")
            return 0

        monkeypatch.setattr(wrapper, "build_project", fake_build)
        monkeypatch.setattr(wrapper, "run_stryker", fake_run_stryker)
        monkeypatch.setattr(wrapper, "_install_signal_handlers", list)
        monkeypatch.setattr(wrapper, "_restore_signal_handlers", lambda previous: None)

        rc = run_slice_runner(hermetic, "--slice", "all", "--total-workers", "2")

        assert rc == 130
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()
