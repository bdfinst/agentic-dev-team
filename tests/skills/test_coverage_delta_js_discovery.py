"""Coverage for coverage-delta/SKILL.md Step 2/2a/5's JS/TS path (issue
#1759, Slice 5 review follow-up): mirrors
test_coverage_delta_discovery_rederivation.py's .NET integration coverage
(merge, unaccounted, stale-exclusion, basis-notice) but drives the REAL
`coverage_discovery_js.discover_js_packages` -> `drift_check` ->
`weighted_merge` chain against a synthesized JS/TS workspace fixture,
mirroring test_coverage_baseline_js_discovery.py's package.json fixture
helpers for the JS/TS side of the same feature.

Before this file, every coverage-delta integration test drove only
`coverage_discovery_dotnet` — Slice 4 (coverage-baseline) had full
dual-stack parity (dotnet + js discovery test files); Slice 5 (coverage-delta)
did not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from coverage_delta_flow_helpers import (
    COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES,
    run_delta_flow,
)
from skill_doc_helpers import PLUGIN_ROOT

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_js as cdj

# ---------------------------------------------------------------------------
# package.json fixture helpers (mirroring test_coverage_baseline_js_discovery.py
# and plugins/dev-team/tests/scripts/test_coverage_discovery_js.py)
# ---------------------------------------------------------------------------


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def pkg(root: Path, data: dict) -> None:
    write(root / "package.json", data)


TEST_PKG = {
    "name": "test-pkg",
    "scripts": {"test": "jest"},
    "devDependencies": {"jest": "^29"},
}


# ---------------------------------------------------------------------------
# Integration: merge scenario — two real test packages of differing size,
# merged via run_delta_flow and persisted to a delta file.
# ---------------------------------------------------------------------------


def test_js_merge_scenario_produces_weighted_merged_percentage(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "b", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps({"included": ["packages/a", "packages/b"], "excluded": []}),
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    discovered = cdj.discover_js_packages(tmp_path)
    reports = {
        "packages/a": {
            "covered_statements": 10,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        },
        "packages/b": {
            "covered_statements": 500,
            "total_statements": 1000,
            "covered_branches": 0,
            "total_branches": 0,
        },
    }

    delta_path = tmp_path / "coverage-delta.json"
    result = run_delta_flow(
        discovered, config_path, baseline, reports, delta_path=delta_path
    )

    assert result.stopped is False
    assert result.merged["line_pct"] == pytest.approx(50.5, abs=0.01)
    assert result.delta_written is True
    assert delta_path.is_file()


# ---------------------------------------------------------------------------
# Integration: unaccounted package hard-fails without the generic banner.
# ---------------------------------------------------------------------------


def test_js_unaccounted_package_hard_fails_without_generic_banner_text(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "c", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps({"included": ["packages/a"], "excluded": []}), encoding="utf-8"
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    discovered = cdj.discover_js_packages(tmp_path)
    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is True
    assert "packages/c" in result.hard_failure_message
    assert result.hard_failure_message.startswith("Coverage capture stopped:")
    for phrase in COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES:
        assert phrase not in result.hard_failure_message
    assert result.delta_written is False


# ---------------------------------------------------------------------------
# Integration: discovery never reuses a frozen list — a package present only
# on the second call hard-fails even though the first call succeeded. JS/TS
# equivalent of
# test_coverage_delta_discovery_rederivation.py::test_second_call_hard_fails_on_a_newly_unaccounted_project
# — Slice 5's defining behavior ("never a frozen list") had no JS/TS test.
# ---------------------------------------------------------------------------


def test_js_second_call_hard_fails_on_a_newly_unaccounted_package(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps({"included": ["packages/a"], "excluded": []}), encoding="utf-8"
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    # First call: only packages/a exists on disk — matches config, succeeds.
    discovered_1 = cdj.discover_js_packages(tmp_path)
    result_1 = run_delta_flow(
        discovered_1,
        config_path,
        baseline,
        {
            "packages/a": {
                "covered_statements": 10,
                "total_statements": 10,
                "covered_branches": 0,
                "total_branches": 0,
            }
        },
    )
    assert result_1.stopped is False

    # Second call: packages/b now exists on disk too — never in config's
    # included/excluded — hard-fails even though nothing about the config
    # or the coverage tool changed between calls.
    pkg(tmp_path / "packages" / "b", TEST_PKG)
    discovered_2 = cdj.discover_js_packages(tmp_path)
    result_2 = run_delta_flow(discovered_2, config_path, baseline)

    assert result_2.stopped is True
    assert "packages/b" in result_2.hard_failure_message
    assert result_2.hard_failure_message.startswith("Coverage capture stopped:")
    for phrase in COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES:
        assert phrase not in result_2.hard_failure_message
    assert result_2.delta_written is False


# ---------------------------------------------------------------------------
# Integration: a stale exclusion surfaces as a specific, non-blocking
# warning and the run still completes.
# ---------------------------------------------------------------------------


def test_js_stale_exclusion_is_nonblocking_and_run_still_completes(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps(
            {
                "included": ["packages/a"],
                "excluded": [
                    {"path": "packages/b", "reason": "removed in a prior cleanup"}
                ],
            }
        ),
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    # packages/b no longer exists at all — a stale exclusion.
    discovered = cdj.discover_js_packages(tmp_path)
    delta_path = tmp_path / "coverage-delta.json"
    result = run_delta_flow(
        discovered,
        config_path,
        baseline,
        {
            "packages/a": {
                "covered_statements": 5,
                "total_statements": 10,
                "covered_branches": 0,
                "total_branches": 0,
            }
        },
        delta_path=delta_path,
    )

    assert result.stopped is False
    assert result.stale_warning_message is not None
    assert "packages/b" in result.stale_warning_message
    assert "removed in a prior cleanup" in result.stale_warning_message
    assert result.delta_written is True
    assert delta_path.is_file()


# ---------------------------------------------------------------------------
# Integration: measurement-basis notice appears/disappears per
# measurement_basis_notice's own contract, called through the documented
# flow rather than re-derived comparison logic.
# ---------------------------------------------------------------------------


def test_js_basis_notice_appears_when_baseline_predates_bootstrap(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps(
            {
                "included": ["packages/a"],
                "excluded": [],
                "bootstrapped_at": "2026-08-04T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    discovered = cdj.discover_js_packages(tmp_path)
    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is False
    assert result.basis_notice is not None
    assert "predates multi-project discovery" in result.basis_notice
    assert "bootstrapped 2026-08-04T12:00:00Z" in result.basis_notice


def test_js_basis_notice_absent_once_a_fresh_baseline_is_captured(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps(
            {
                "included": ["packages/a"],
                "excluded": [],
                "bootstrapped_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    discovered = cdj.discover_js_packages(tmp_path)
    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is False
    assert result.basis_notice is None
