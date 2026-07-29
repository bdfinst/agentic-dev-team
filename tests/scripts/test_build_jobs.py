"""Pytest port of build-jobs cases from build_wave_tests.bats (#610 / #572
Phase 3). Covers the `--jobs`/`--wave-width` clamp semantics and the default
concurrency policy from `DEV_TEAM_MAX_PARALLEL_BUILDS`.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

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


@pytest.mark.parametrize(
    "args,max_env",
    [
        (("--jobs", "0", "--wave-width", "5"), None),  # zero --jobs, env unset
        (("--jobs", "abc", "--wave-width", "5"), None),  # non-integer --jobs
        (("--wave-width", "5"), "0"),  # zero env
        (("--wave-width", "5"), "-3"),  # negative env
        (("--wave-width", "5"), "abc"),  # non-integer env
        (("--wave-width", "abc"), None),  # non-integer width (same _norm clamp)
        (("--wave-width", "0"), None),  # zero width
        (("--wave-width", "-3"), None),  # negative width
        (("--jobs", "²", "--wave-width", "5"), None),  # unicode digit --jobs
        (("--wave-width", "5"), "²"),  # unicode digit env (isdigit-true edge)
    ],
)
def test_invalid_value_clamps_to_sequential_without_error(args, max_env) -> None:
    """Every invalid --jobs or env value clamps to 1, exits 0, and writes no
    traceback — a rewritten branch must never turn bad input into a crash
    (#1515, AC5)."""
    r = _run(*args, max_env=max_env)
    assert r.stdout.strip() == "1"
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


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


def test_unset_both_defaults_to_sequential() -> None:
    """The core #1515 change: neither `--jobs` nor the env var set → sequential
    (1), regardless of wave width. Parallel fan-out is opt-in only."""
    r = _run("--wave-width", "5")
    assert r.returncode == 0
    assert r.stdout.strip() == "1"


@pytest.mark.parametrize(
    "jobs,width,expected",
    [
        ("3", "5", "3"),  # N < W
        ("3", "3", "3"),  # N == W
        ("5", "2", "2"),  # N > W, width caps
    ],
)
def test_explicit_jobs_opts_in_bounded_by_width(jobs, width, expected) -> None:
    """Env unset: an explicit `--jobs N` opts into fan-out, bounded only by wave
    width (no per-host ceiling anymore, #1515)."""
    r = _run("--jobs", jobs, "--wave-width", width)
    assert r.stdout.strip() == expected


@pytest.mark.parametrize(
    "env,width,expected",
    [
        ("4", "6", "4"),  # K < W, env honored verbatim
        ("5", "5", "5"),  # K == W
        ("8", "3", "3"),  # K > W, width caps
    ],
)
def test_explicit_env_opts_in_bounded_by_width(env, width, expected) -> None:
    """Env set + `--jobs` unset: fan out to the env max, bounded by wave width
    (#1515)."""
    r = _run("--wave-width", width, max_env=env)
    assert r.stdout.strip() == expected


@pytest.mark.parametrize(
    "jobs,env,width,expected",
    [
        ("6", "8", "5", "5"),  # width tightest
        ("6", "2", "8", "2"),  # env tightest — proves env is not dropped
        ("3", "8", "8", "3"),  # jobs tightest
    ],
)
def test_both_set_resolves_to_tightest_bound(jobs, env, width, expected) -> None:
    """Both `--jobs` and env set → min(jobs, env, width); the env-tightest row
    guards against a regression that drops the env term (#1515)."""
    r = _run("--jobs", jobs, "--wave-width", width, max_env=env)
    assert r.stdout.strip() == expected


def test_wave_width_one_caps_to_one() -> None:
    """Env unset, wave width 1 → effective 1: wave width caps regardless of the
    default. (The sequential-default change itself is guarded by
    test_unset_both_defaults_to_sequential, which uses width > 1.)"""
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


def test_stderr_max_falls_back_to_wave_width_when_env_unset() -> None:
    """With the env var unset, `max` has no independent ceiling — it falls back
    to wave width, and the resolution line must surface that value (#1515)."""
    r = _run("--jobs", "2", "--wave-width", "5")
    assert "max=5" in r.stderr


def test_unknown_flag_is_usage_error() -> None:
    r = _run("--wat")
    assert r.returncode == 2
    assert "usage" in r.stderr
