"""Pytest port of build-jobs cases from build_wave_tests.bats (#610 / #572
Phase 3). Covers the `--jobs`/`--wave-width` clamp semantics and the default
concurrency policy from `DEV_TEAM_MAX_PARALLEL_BUILDS`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_jobs.py"


def _load_build_jobs():
    """Import build_jobs.py as a module so its internals are unit-testable
    directly (the seam #1170 added), independent of the subprocess harness."""
    spec = importlib.util.spec_from_file_location("build_jobs", _SCRIPT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILD_JOBS = _load_build_jobs()


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


def test_jobs_one_forces_sequential() -> None:
    """`--jobs 1` resolves to 1 regardless of a wide wave / high max — the
    sequential decision (AC4)."""
    r = _run("--jobs", "1", "--wave-width", "8", max_env="8")
    assert r.stdout.strip() == "1"


def test_explicit_max_one_forces_sequential() -> None:
    """`DEV_TEAM_MAX_PARALLEL_BUILDS=1` resolves to 1 even with --jobs unset
    and a wide wave — the sequential decision (AC4)."""
    r = _run("--wave-width", "5", max_env="1")
    assert r.stdout.strip() == "1"


@pytest.mark.parametrize(
    "cpu_count,expected",
    [
        (None, 1),  # unknown core count floors at 1
        (1, 1),  # 1-2 = -1 -> floored to 1
        (2, 1),  # 2-2 = 0 -> floored to 1
        (3, 1),  # 3-2 = 1 -> the exact floor-transition edge
        (7, 5),  # 7-2 = 5, under the 16 ceiling
        (8, 6),  # 8-2 = 6
        (18, 16),  # 18-2 = 16, exactly at the ceiling
        (100, 16),  # clamp engages above 18 cores
    ],
)
def test_default_max_parallel_builds_formula(cpu_count, expected) -> None:
    """The extracted seam computes min(16, cores-2) floored at 1, proven with
    literal inputs independent of the real host (#1170)."""
    assert _BUILD_JOBS._default_max_parallel_builds(cpu_count) == expected


def test_default_max_when_env_unset() -> None:
    """`DEV_TEAM_MAX_PARALLEL_BUILDS` unset → the cores-derived ceiling. This
    is a wiring check: it composes the same imported helper the code uses
    rather than re-deriving the formula, so it cannot pass vacuously (#1170)."""
    expected = min(5, _BUILD_JOBS._default_max_parallel_builds(os.cpu_count()))
    r = _run("--jobs", "5", "--wave-width", "5")
    assert r.stdout.strip() == str(expected)


def test_default_equals_wave_width_one_host_independent() -> None:
    """Env unset, wave width 1 → effective 1 on every host, because the
    cores-derived default is always >= 1."""
    r = _run("--wave-width", "1")
    assert r.stdout.strip() == "1"


def test_explicit_max_above_ceiling_honored_verbatim() -> None:
    """An explicit DEV_TEAM_MAX_PARALLEL_BUILDS above the cores ceiling is a
    deliberate override — honored verbatim, never re-capped (#1170)."""
    r = _run("--jobs", "50", "--wave-width", "50", max_env="32")
    assert r.stdout.strip() == "32"


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
