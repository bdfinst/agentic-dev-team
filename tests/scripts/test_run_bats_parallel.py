"""scripts/run-bats-parallel.sh — portable across-file bats fan-out (xargs
-P, no GNU `parallel`). These tests pin its orchestration contract — file
discovery, parallel fan-out, and collect-all-failures exit semantics.

They drive the runner with a STUB `bats` placed on PATH rather than
nesting a real bats inside this suite. Nesting real bats is fragile
across versions (the inner process inherits the outer's test-selection
state), and we only need to verify the runner's own logic, not bats
itself. The stub reports which file it "ran" and fails iff the path is
marked to fail.

Ported from tests/scripts/run_bats_parallel_tests.bats (issue #676).
scripts/run-bats-parallel.sh stays bash (out of scope per issue note);
only the test harness moves to pytest.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "run-bats-parallel.sh"


@pytest.fixture
def work(tmp_path: Path) -> Path:
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    stub = stub_bin / "bats"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'echo "ran:$1"\n'
        'case "$1" in *fail*) exit 1 ;; *) exit 0 ;; esac\n'
    )
    stub.chmod(0o755)

    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "pass_a.bats").touch()
    (suite / "pass_b.bats").touch()
    (suite / "fail_c.bats").touch()

    return tmp_path


def _run_runner(work: Path, *args: str) -> subprocess.CompletedProcess:
    stub_bin = work / "bin"
    env = {**os.environ, "PATH": f"{stub_bin}:{os.environ.get('PATH', '')}"}
    return subprocess.run(
        ["bash", str(RUNNER), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_all_files_pass_exit_0(work: Path) -> None:
    suite = work / "suite"
    result = _run_runner(
        work, "-j", "2", str(suite / "pass_a.bats"), str(suite / "pass_b.bats")
    )
    assert result.returncode == 0


def test_any_file_fails_non_zero_exit(work: Path) -> None:
    suite = work / "suite"
    result = _run_runner(
        work, "-j", "2", str(suite / "pass_a.bats"), str(suite / "fail_c.bats")
    )
    assert result.returncode != 0


def test_collect_all_failures_a_failing_file_does_not_abort_the_others(
    work: Path,
) -> None:
    suite = work / "suite"
    result = _run_runner(
        work, "-j", "2", str(suite / "pass_a.bats"), str(suite / "fail_c.bats")
    )
    assert result.returncode != 0
    assert "ran:" in result.stdout and "pass_a.bats" in result.stdout
    assert "ran:" in result.stdout and "fail_c.bats" in result.stdout


def test_directory_args_expand_to_their_bats_files(work: Path) -> None:
    suite = work / "suite"
    result = _run_runner(work, "-j", "2", str(suite))
    assert result.returncode != 0
    assert "pass_a.bats" in result.stdout
    assert "pass_b.bats" in result.stdout
    assert "fail_c.bats" in result.stdout


def test_no_bats_files_exit_0_with_a_message(work: Path, tmp_path_factory) -> None:
    empty = tmp_path_factory.mktemp("empty")
    result = _run_runner(work, str(empty))
    assert result.returncode == 0
    assert "no .bats files found" in (result.stdout + result.stderr)


def test_jobs_defaults_sanely_when_j_is_omitted(work: Path) -> None:
    suite = work / "suite"
    result = _run_runner(work, str(suite / "pass_a.bats"))
    assert result.returncode == 0
    assert "pass_a.bats" in result.stdout
