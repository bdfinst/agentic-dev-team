"""Shared flow-simulation helpers for the coverage-delta multi-project
re-derivation integration tests (issue #1759, Slice 5):
test_coverage_delta_discovery_rederivation.py and
test_coverage_delta_incident_reproduction.py.

`coverage-delta`'s multi-project re-derivation flow is SKILL.md prose (Step
2/2a and Step 5), not a single runnable script. This module implements that
documented order exactly once, calling the REAL Slice 1-3 functions
(`coverage_config.drift_check`, `weighted_merge`, `measurement_basis_notice`)
— reading an existing `coverage-config.json`/`baseline-coverage.json` rather
than bootstrapping (coverage-delta assumes a prior `/coverage-baseline` run
already created both) — mirroring
`tests/skills/coverage_baseline_flow_helpers.py`'s `run_baseline_flow` for
the baseline side of the same feature. See
`plugins/dev-team/skills/coverage-delta/SKILL.md` Step 2/2a/5 and
`plugins/dev-team/skills/coverage-baseline/references/multi-project-discovery.md`
for the documented order this mirrors.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_config import (  # noqa: E402
    atomic_write_json,
    drift_check,
    format_active_exclusions,
    measurement_basis_notice,
    weighted_merge,
)

# coverage-delta/SKILL.md Step 2's own pre-existing, unedited generic
# run-failure wording — the generic banner text every hard-failure block in
# Step 2a must stay textually distinct from. Mirrors
# `coverage_baseline_flow_helpers.GENERIC_COVERAGE_RUN_FAILURE_PHRASES` for
# coverage-delta's own (textually different) generic wording.
COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES = (
    "surface the first error and stop",
    "Do not post a delta from a broken run.",
)


@dataclass
class DeltaFlowResult:
    stopped: bool
    hard_failure_message: str | None = None
    stale_warning_message: str | None = None
    stale_exclusions: list = None
    basis_notice: str | None = None
    config: dict | None = None
    merged: dict | None = None
    delta_written: bool = False
    active_exclusions_message: str | None = None


def _merge_included_reports(
    included: list, discovered: list, project_reports_by_path: dict
) -> dict:
    """Same tolerance rule as
    `coverage_baseline_flow_helpers._merge_included_reports`: a
    legitimately-stale included path (no longer discovered at all) is
    skipped silently; a path present in both `included` and `discovered`
    but still missing a report is a test-fixture wiring bug, not a
    legitimate runtime gap, and raises loudly instead of under-counting it
    into the merge."""
    discovered_paths = {entry["path"] for entry in discovered}
    included_reports = []
    for path in included:
        if path in project_reports_by_path:
            included_reports.append(project_reports_by_path[path])
        elif path not in discovered_paths:
            continue  # legitimately stale; not this helper's job to flag
        else:
            raise AssertionError(
                f"{path!r} is in both config['included'] and the discovered "
                "projects, but has no matching entry in "
                "project_reports_by_path — the test fixture is wired wrong, "
                "not exercising a legitimate runtime gap."
            )
    return weighted_merge(included_reports)


def run_delta_flow(
    discovered: list,
    config_path: Path,
    baseline: dict,
    project_reports_by_path: dict | None = None,
    *,
    delta_path: Path | None = None,
) -> DeltaFlowResult:
    """Simulate coverage-delta's Step 2/2a/5 documented flow, calling the
    real Slice 1-3 functions in the exact documented order:

    1. Read the persisted `coverage-config.json` verbatim (never bootstrap
       — coverage-delta assumes a prior `/coverage-baseline` run already
       created it; a missing file is a caller bug in these tests, not a
       flow branch this helper handles).
    2. `measurement_basis_notice(config.get("bootstrapped_at"),
       baseline["captured_at"])`.
    3. `drift_check(config, discovered)` — hard failure stops the flow
       before any delta write. `stale_warning_message` is always carried
       forward on the result regardless of `hard_failure` (Step 5 surfaces
       it as a non-blocking warning either way). `active_exclusions_message`
       (`format_active_exclusions(config)`) is likewise always carried
       forward, computed straight from the loaded config — an always-shown
       informational line, not gated on drift or staleness.
    4. `weighted_merge` over the included projects'/packages' reports (only
       when `project_reports_by_path` is supplied — tests that don't reach
       this step omit it and get `merged=None`).
    5. On success, when `delta_path` is supplied, persist
       `{"line_pct", "branch_pct"}` via `coverage_config.atomic_write_json`
       and set `result.delta_written = True`.

    `discovered` must already be a real `discover_*`-shaped list (never
    `DISCOVERY_NOT_APPLICABLE`/`discovery_error` — callers check that signal
    via the real discovery function before calling this).
    """
    if isinstance(discovered, dict):
        raise ValueError(
            "run_delta_flow expects a real discover_*-shaped list; check "
            "the discovery signal before calling this"
        )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    basis_notice = measurement_basis_notice(
        config.get("bootstrapped_at"), baseline["captured_at"]
    )
    active_exclusions_message = format_active_exclusions(config)

    drift = drift_check(config, discovered)
    if drift["hard_failure"]:
        return DeltaFlowResult(
            stopped=True,
            hard_failure_message=drift["hard_failure_message"],
            stale_warning_message=drift["stale_warning_message"],
            stale_exclusions=drift["stale_exclusions"],
            basis_notice=basis_notice,
            config=config,
            active_exclusions_message=active_exclusions_message,
        )

    merged = None
    if project_reports_by_path is not None:
        merged = _merge_included_reports(
            config["included"], discovered, project_reports_by_path
        )

    delta_written = False
    if delta_path is not None and merged is not None:
        atomic_write_json(
            delta_path,
            {"line_pct": merged["line_pct"], "branch_pct": merged["branch_pct"]},
        )
        delta_written = True

    return DeltaFlowResult(
        stopped=False,
        stale_warning_message=drift["stale_warning_message"],
        stale_exclusions=drift["stale_exclusions"],
        basis_notice=basis_notice,
        config=config,
        merged=merged,
        delta_written=delta_written,
        active_exclusions_message=active_exclusions_message,
    )
