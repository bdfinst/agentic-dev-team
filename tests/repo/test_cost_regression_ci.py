"""Tests for scripts/cost-regression-check.sh — the CI wiring for the cost-meter
regression gate (#140 mechanism, #171 real cross-machine baseline): self-test
(blocking), real baseline (warn-only), and no-baseline (clean pass).

Ported from tests/repo/cost_regression_ci_tests.bats (issue #672).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

CHECK = REPO_ROOT / "scripts" / "cost-regression-check.sh"
EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"


def _run_check(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    return subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, env=env)


def test_ci_cost_self_test_passes_and_no_baseline_clean_exit_0(tmp_path: Path) -> None:
    res = _run_check({"COST_BASELINE_LOG": str(tmp_path / "none.jsonl")})
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout + res.stderr
    assert "spike flagged, within-tolerance passes" in out
    assert "no baseline log" in out


def test_ci_cost_a_committed_baseline_with_a_spike_warns_but_does_not_block(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.jsonl"
    base.write_text(
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":1.0}}\n'
        '{"total":{"cost_usd":9.0}}\n'
    )
    res = _run_check({"COST_BASELINE_LOG": str(base), "COST_TOLERANCE": "0.5"})
    assert res.returncode == 0, res.stdout + res.stderr  # warn-only: never blocks
    out = res.stdout + res.stderr
    assert "COST REGRESSION" in out
    assert "::warning" in out


def test_ci_cost_a_within_tolerance_baseline_passes_without_a_warning(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.jsonl"
    base.write_text('{"total":{"cost_usd":1.0}}\n{"total":{"cost_usd":1.1}}\n')
    res = _run_check({"COST_BASELINE_LOG": str(base), "COST_TOLERANCE": "0.5"})
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout + res.stderr
    assert "no cost regression" in out
    assert "::warning" not in out


def test_ci_cost_171_end_to_end_telemetry_digests_cost_log_baseline_warn(
    tmp_path: Path,
) -> None:
    # Simulate the CI flow: a cloned telemetry repo's digests become the baseline.
    digests = tmp_path / "digests" / "boxA"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxA","session_id":"s1",'
        '"ts":"2026-06-01T00:00:00Z","cost_usd":1.0}\n'
        '{"schema":"session-sync/v1","host":"boxA","session_id":"s2",'
        '"ts":"2026-06-02T00:00:00Z","cost_usd":1.0}\n'
        '{"schema":"session-sync/v1","host":"boxA","session_id":"s3",'
        '"ts":"2026-06-03T00:00:00Z","cost_usd":9.0}\n'
    )
    cost_log = tmp_path / "cost-log.jsonl"
    subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--cost-log",
            str(tmp_path / "digests"),
            "-o",
            str(cost_log),
        ],
        check=True,
    )
    # newest session (ts 06-03) is the spike; priors mean to 1.0
    res = _run_check({"COST_BASELINE_LOG": str(cost_log), "COST_TOLERANCE": "0.5"})
    assert res.returncode == 0, res.stdout + res.stderr  # warn-only: never blocks
    out = res.stdout + res.stderr
    assert "COST REGRESSION" in out
    assert "::warning" in out


def test_ci_cost_registered_as_a_step_in_plugin_tests_yml() -> None:
    # Wired either directly or through the shared gate (scripts/ci-local.sh's
    # chk_cost_regression — single source of truth for CI and pre-push). For the
    # indirect form, confirm ci-local actually maps the check to the script.
    workflow = (REPO_ROOT / ".github" / "workflows" / "plugin-tests.yml").read_text()
    if "cost-regression-check.sh" in workflow:
        return
    ci_local = (REPO_ROOT / "scripts" / "ci-local.sh").read_text()
    assert "chk_cost_regression" in workflow
    assert re.search(r"chk_cost_regression.*cost-regression-check\.sh", ci_local)
