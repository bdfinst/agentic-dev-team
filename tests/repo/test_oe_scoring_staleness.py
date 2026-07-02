"""OE scoring staleness alert: detects when subject prose / fixtures /
expected change (or are added) after a scoring snapshot, so the scorecard's
currency is visible. Model-free (SHA-256 of inputs), so it runs in CI like
the grader.

Ported from tests/repo/oe_scoring_staleness_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "oe_scoring_staleness.py"


@pytest.fixture
def suite(tmp_path: Path) -> Dict[str, Path]:
    suite_dir = tmp_path / "suite"
    root = tmp_path / "root"
    manifest = tmp_path / "manifest.json"
    (suite_dir / "expected").mkdir(parents=True)
    (suite_dir / "fixtures").mkdir(parents=True)
    (root / "specs").mkdir(parents=True)

    (suite_dir / "subjects.json").write_text(
        '{ "alpha": ["specs/alpha.md"], "beta": ["specs/beta.md"] }\n'
    )
    (root / "specs" / "alpha.md").write_text("alpha v1\n")
    (root / "specs" / "beta.md").write_text("beta v1\n")

    (suite_dir / "expected" / "oe-01-thing.json").write_text(
        '{"fixture":"oe-01-thing.md","subjects":["alpha","beta"]}\n'
    )
    (suite_dir / "fixtures" / "oe-01-thing.md").write_text("scenario one\n")

    return {"suite": suite_dir, "root": root, "manifest": manifest}


def _write(suite: Dict[str, Path]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--write",
            "--suite-dir",
            str(suite["suite"]),
            "--repo-root",
            str(suite["root"]),
            "--manifest",
            str(suite["manifest"]),
        ],
        capture_output=True,
        text=True,
    )


def _check(suite: Dict[str, Path], *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--suite-dir",
            str(suite["suite"]),
            "--repo-root",
            str(suite["root"]),
            "--manifest",
            str(suite["manifest"]),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_fresh_snapshot_reports_ok_and_exits_0(suite: Dict[str, Path]) -> None:
    _write(suite)
    result = _check(suite)
    assert result.returncode == 0
    assert "OK — all scored" in result.stdout + result.stderr


def test_missing_manifest_is_reported_and_exits_nonzero(suite: Dict[str, Path]) -> None:
    result = _check(suite)
    assert result.returncode != 0
    assert "NO MANIFEST" in result.stdout + result.stderr


def test_changed_subject_spec_marks_its_pairs_stale(suite: Dict[str, Path]) -> None:
    _write(suite)
    (suite["root"] / "specs" / "alpha.md").write_text("alpha v2 (edited)\n")
    result = _check(suite)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "STALE" in out
    assert "oe-01-thing::alpha" in out
    assert "subject prose changed" in out
    # beta was untouched, so its pair must NOT be flagged stale
    assert "oe-01-thing::beta" not in out


def test_changed_expected_file_marks_all_that_fixtures_pairs_stale(
    suite: Dict[str, Path],
) -> None:
    _write(suite)
    (suite["suite"] / "expected" / "oe-01-thing.json").write_text(
        '{"fixture":"oe-01-thing.md","subjects":["alpha","beta"],"x":1}\n'
    )
    result = _check(suite)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "oe-01-thing::alpha" in out
    assert "oe-01-thing::beta" in out
    assert "expected criteria changed" in out


def test_new_never_scored_fixture_is_reported_as_new(suite: Dict[str, Path]) -> None:
    _write(suite)
    (suite["suite"] / "expected" / "oe-02-new.json").write_text(
        '{"fixture":"oe-02-new.md","subjects":["alpha"]}\n'
    )
    (suite["suite"] / "fixtures" / "oe-02-new.md").write_text("scenario two\n")
    result = _check(suite)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "NEW" in out
    assert "oe-02-new::alpha" in out
    assert "never scored" in out


def test_warn_only_prints_the_alert_but_exits_0(suite: Dict[str, Path]) -> None:
    _write(suite)
    (suite["root"] / "specs" / "alpha.md").write_text("alpha v2\n")
    result = _check(suite, "--warn-only")
    assert result.returncode == 0
    assert "STALE" in result.stdout + result.stderr


def test_real_repo_manifest_parses_and_resolves_against_live_suite() -> None:
    # Smoke-only: the staleness signal is deliberately ADVISORY (ci-local runs
    # it with --warn-only), so we do NOT hard-assert the manifest is current
    # here - that would turn a cosmetic subject edit into a test-suite
    # failure. We only assert the checker runs end-to-end against the real
    # tree and emits a report.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--warn-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OE scoring staleness" in result.stdout + result.stderr
