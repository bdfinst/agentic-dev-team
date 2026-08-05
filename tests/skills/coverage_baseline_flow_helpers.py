"""Shared flow-simulation helpers for the coverage-baseline multi-project
discovery integration tests (issue #1759, Slice 4):
test_coverage_baseline_dotnet_discovery.py,
test_coverage_baseline_js_discovery.py,
test_coverage_baseline_no_regression_single_project.py, and
test_coverage_baseline_discovery_boundaries.py.

`coverage-baseline`'s multi-project discovery flow is SKILL.md prose (Step
1a), not a single runnable script — there is nothing to import and call
end-to-end. This module implements that documented order exactly once,
calling the REAL Slice 1-3 functions (`coverage_config.load_or_bootstrap`,
`needs_accounting`, `drift_check`, `weighted_merge`), so every integration
test in this directory exercises the same flow the SKILL.md describes
rather than four independently-drifting simulations. See
`plugins/dev-team/skills/coverage-baseline/SKILL.md` Step 1a and
`plugins/dev-team/skills/coverage-baseline/references/multi-project-discovery.md`
for the documented order this mirrors.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from skill_doc_helpers import PLUGIN_ROOT

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd
from coverage_config import (
    atomic_write_json,
    drift_check,
    load_or_bootstrap,
    needs_accounting,
)
from coverage_flow_shared import merge_included_reports

# The exact zero-real-test-project message template documented in
# SKILL.md Step 1a / references/multi-project-discovery.md Step 2.
# `{kind}` is "solution" for .NET, "workspace" for JS/TS, "multi-module build"
# for Java (#1765).
ZERO_REAL_TEST_MESSAGE_TEMPLATE = (
    "Coverage capture stopped: no real test project was discovered in this "
    "{kind} — cannot establish a coverage floor. If this repo has test "
    "projects, verify they reference Microsoft.NET.Test.Sdk (for .NET), use "
    "jest/vitest/mocha+nyc/c8 (for JS/TS), or declare a JUnit/TestNG "
    "dependency alongside a src/test/java|kotlin directory (for Java) so "
    "discovery can recognize them; otherwise there is no coverage floor to "
    "capture."
)

# Step 3's pre-existing, unedited "Run coverage" failure wording — the
# generic coverage-run-failure banner text every hard-failure block in Step
# 1a must stay textually distinct from.
GENERIC_COVERAGE_RUN_FAILURE_PHRASES = (
    "Surface the first error.",
    "Do NOT write a baseline. The floor must be a true measurement.",
)


def zero_real_test_message(kind: str) -> str:
    return ZERO_REAL_TEST_MESSAGE_TEMPLATE.format(kind=kind)


@contextlib.contextmanager
def stub_dotnet(project_paths):
    """Stub `dotnet sln list` to report `project_paths`, without invoking a
    real `dotnet` CLI. Shared here (issue #1759 Slice 4 review) after this
    exact context manager was independently duplicated across
    test_coverage_baseline_dotnet_discovery.py,
    test_coverage_baseline_no_regression_single_project.py, and inline in
    test_coverage_baseline_discovery_boundaries.py."""
    stdout = "Project(s)\n----------\n" + "\n".join(project_paths) + "\n"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
    with (
        patch.object(cdd.shutil, "which", return_value="/usr/bin/dotnet"),
        patch.object(cdd.subprocess, "run", return_value=completed),
    ):
        yield


@dataclass
class BaselineFlowResult:
    stopped: bool
    message: str | None = None
    notice: str | None = None
    config: dict | None = None
    merged: dict | None = None
    baseline_written: bool = False


def run_baseline_flow(
    discovered: list,
    config_path: Path,
    now_iso: str,
    kind: str,
    project_reports_by_path: dict | None = None,
    *,
    baseline_path: Path,
) -> BaselineFlowResult:
    """Simulate coverage-baseline's Step 1a documented flow, calling the
    real Slice 1-3 functions in the exact documented order:

    1. Zero-real-test-project check (no config touched on this path).
    2. `load_or_bootstrap` (bootstraps `coverage-config.json` if absent).
    3. `drift_check` — hard failure stops the flow before any baseline
       write.
    4. `weighted_merge` over the included projects' reports (only when
       `project_reports_by_path` is supplied — tests that don't reach this
       step omit it and get `merged=None`).
    5. On success (no hard failure), persist `{"line_pct", "branch_pct"}` to
       `baseline_path` via `coverage_config.atomic_write_json` and set
       `result.baseline_written = True`. Any failure path above (zero-real-
       test, hard-failure) returns before this step — `baseline_path` is
       never touched and `baseline_written` stays `False`.

    `discovered` must already be a real `discover_*`-shaped list (never
    `DISCOVERY_NOT_APPLICABLE`/`discovery_error` — callers check that
    signal via the real discovery function before calling this). Passing a
    signal dict instead raises `ValueError` immediately rather than being
    silently misread as "zero real test projects".
    """
    if isinstance(discovered, dict):
        raise ValueError(  # noqa: TRY004 — matches production's documented ValueError contract for this misuse
            "run_baseline_flow expects a real discover_*-shaped list; check "
            "the discovery signal before calling this"
        )

    if not any(needs_accounting(entry["classification"]) for entry in discovered):
        return BaselineFlowResult(
            stopped=True, message=zero_real_test_message(kind)
        )

    config, notice = load_or_bootstrap(config_path, discovered, now_iso)

    drift = drift_check(config, discovered)
    if drift["hard_failure"]:
        return BaselineFlowResult(
            stopped=True,
            message=drift["hard_failure_message"],
            notice=notice,
            config=config,
        )

    merged = None
    if project_reports_by_path is not None:
        merged = merge_included_reports(
            config["included"], discovered, project_reports_by_path
        )

    atomic_write_json(
        baseline_path,
        {
            "line_pct": merged["line_pct"] if merged is not None else None,
            "branch_pct": merged["branch_pct"] if merged is not None else None,
        },
    )

    return BaselineFlowResult(
        stopped=False,
        notice=notice,
        config=config,
        merged=merged,
        baseline_written=True,
    )
