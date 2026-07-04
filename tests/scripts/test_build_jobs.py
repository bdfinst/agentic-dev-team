"""Pytest port of build-jobs cases from build_wave_tests.bats (#610 / #572
Phase 3). Covers the `--jobs`/`--wave-width` clamp semantics and the default
concurrency policy from `DEV_TEAM_MAX_PARALLEL_BUILDS`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_jobs.py"


def _run(*args, max_env=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    if max_env is not None:
        env["DEV_TEAM_MAX_PARALLEL_BUILDS"] = max_env
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_min_of_jobs_max_width() -> None:
    r = _run("--jobs", "5", "--wave-width", "4", max_env="2")
    assert r.returncode == 0
    assert r.stdout.strip() == "2"


def test_clamps_zero_to_one() -> None:
    r = _run("--jobs", "0", "--wave-width", "3", max_env="4")
    assert r.stdout.strip() == "1"


def test_clamps_negative_to_one() -> None:
    r = _run("--jobs", "-2", "--wave-width", "3", max_env="4")
    assert r.stdout.strip() == "1"


def test_non_integer_clamps_to_one() -> None:
    r = _run("--jobs", "abc", "--wave-width", "3", max_env="4")
    assert r.stdout.strip() == "1"


def test_wave_width_caps_concurrency() -> None:
    r = _run("--jobs", "8", "--wave-width", "1", max_env="8")
    assert r.stdout.strip() == "1"


def test_default_max_when_env_unset() -> None:
    """`DEV_TEAM_MAX_PARALLEL_BUILDS` unset → default 2."""
    r = _run("--jobs", "5", "--wave-width", "5")
    assert r.stdout.strip() == "2"


def test_unset_jobs_defaults_to_max() -> None:
    """When `--jobs` is omitted, it defaults to the max — verify by giving
    a max lower than the wave-width so the effective is the max."""
    r = _run("--wave-width", "10", max_env="3")
    assert r.stdout.strip() == "3"


def test_stderr_has_resolution_line() -> None:
    r = _run("--jobs", "5", "--wave-width", "4", max_env="2")
    assert "build-jobs: requested=5" in r.stderr
    assert "max=2" in r.stderr
    assert "wave_width=4" in r.stderr
    assert "effective=2" in r.stderr


def test_stderr_shows_unset_literal() -> None:
    r = _run("--wave-width", "4", max_env="2")
    assert "requested=(unset)" in r.stderr


def test_unknown_flag_is_usage_error() -> None:
    r = _run("--wat")
    assert r.returncode == 2
    assert "usage" in r.stderr
