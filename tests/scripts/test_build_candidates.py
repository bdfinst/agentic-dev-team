"""Tests for build_candidates.py (#2273): validate-flags, rank, project,
collect and cleanup. The reconcile and lifecycle scenarios live in
test_build_candidates_integration.py.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
_SCRIPT_PY = _SCRIPTS_DIR / "build_candidates.py"
_FLOOR_TEST = _REPO_ROOT / "tests" / "repo" / "test_python_floor.py"

sys.path.insert(0, str(_SCRIPTS_DIR))

import build_candidates


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _flag_args(candidates: str, cap: str, jobs: str) -> list[str]:
    """CLI args for the Scenario Outline convention: an empty value means the
    flag is absent."""
    args: list[str] = []
    for flag, value in (
        ("--candidates", candidates),
        ("--max-cost-usd", cap),
        ("--jobs", jobs),
    ):
        if value != "":
            args += [f"{flag}={value}"]
    return args


# --- validate-flags ---------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [(), ("--candidates", "1")],
    ids=["no-flags", "candidates-1-alone"],
)
def test_validate_flags_accepts_the_unchanged_build_as_not_speculative(args) -> None:
    r = _run("validate-flags", *args)
    assert r.returncode == 0
    assert json.loads(r.stdout)["speculative"] is False


def test_validate_flags_output_has_exactly_the_documented_keys() -> None:
    r = _run("validate-flags", "--candidates", "1")
    assert set(json.loads(r.stdout)) == {"candidates", "max_cost_usd", "speculative"}


def test_validate_flags_accepts_a_speculative_run() -> None:
    r = _run("validate-flags", "--candidates", "3", "--max-cost-usd", "12.5")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {
        "candidates": 3,
        "max_cost_usd": 12.5,
        "speculative": True,
    }


def test_validate_flags_prints_max_cost_as_a_number_not_a_string() -> None:
    r = _run("validate-flags", "--candidates", "2", "--max-cost-usd", "5")
    assert isinstance(json.loads(r.stdout)["max_cost_usd"], float)


@pytest.mark.parametrize("jobs", ["abc", "1"])
def test_validate_flags_leaves_non_parallel_jobs_to_build(jobs) -> None:
    r = _run(
        "validate-flags", "--candidates", "2", "--max-cost-usd", "5", "--jobs", jobs
    )
    assert r.returncode == 0
    assert json.loads(r.stdout)["speculative"] is True


def test_validate_flags_ignores_parallel_jobs_when_candidates_is_one() -> None:
    r = _run("validate-flags", "--candidates", "1", "--jobs", "4")
    assert r.returncode == 0
    assert json.loads(r.stdout)["speculative"] is False


_REJECTED = [
    ("0", "5", "", "--candidates must be an integer between 1 and 8; got '0'"),
    ("abc", "5", "", "--candidates must be an integer between 1 and 8; got 'abc'"),
    ("2.5", "5", "", "--candidates must be an integer between 1 and 8; got '2.5'"),
    ("9", "5", "", "--candidates must be an integer between 1 and 8; got '9'"),
    ("-1", "5", "", "--candidates must be an integer between 1 and 8; got '-1'"),
    ("0", "", "", "--candidates must be an integer between 1 and 8; got '0'"),
    ("2", "", "", "--candidates N with N >= 2 requires --max-cost-usd"),
    ("2", "0", "", "--max-cost-usd must be a number greater than 0; got '0'"),
    ("2", "-1", "", "--max-cost-usd must be a number greater than 0; got '-1'"),
    ("2", "nan", "", "--max-cost-usd must be a number greater than 0; got 'nan'"),
    ("2", "inf", "", "--max-cost-usd must be a number greater than 0; got 'inf'"),
    ("1", "0", "", "--max-cost-usd must be a number greater than 0; got '0'"),
    ("1", "5", "", "--max-cost-usd requires --candidates N with N >= 2"),
    ("", "5", "", "--max-cost-usd requires --candidates N with N >= 2"),
    (
        "2",
        "5",
        "2",
        "--candidates N with N >= 2 cannot be combined with --jobs greater than 1",
    ),
]


@pytest.mark.parametrize("candidates,cap,jobs,message", _REJECTED)
def test_validate_flags_rejects_bad_combination_with_the_exact_message(
    candidates, cap, jobs, message
) -> None:
    r = _run("validate-flags", *_flag_args(candidates, cap, jobs))
    assert (r.returncode, r.stdout, r.stderr) == (2, "", message + "\n")


def test_validate_flags_rejects_an_explicitly_empty_candidates_value() -> None:
    r = _run("validate-flags", "--candidates", "")
    assert r.returncode == 2
    assert r.stderr == "--candidates must be an integer between 1 and 8; got ''\n"


def test_validate_flags_rejects_an_explicitly_empty_cap_value() -> None:
    r = _run("validate-flags", "--candidates", "2", "--max-cost-usd", "")
    assert r.returncode == 2
    assert r.stderr == "--max-cost-usd must be a number greater than 0; got ''\n"


def test_validate_flags_rejects_non_ascii_digits_in_candidates() -> None:
    r = _run("validate-flags", "--candidates", "\u0663", "--max-cost-usd", "5")
    assert (r.returncode, r.stdout) == (2, "")
    assert r.stderr.startswith("--candidates must be an integer")


@pytest.mark.parametrize("cap", ["1_0", " 5", "5 "])
def test_validate_flags_rejects_cap_spellings_float_would_tolerate(cap) -> None:
    r = _run("validate-flags", "--candidates", "2", "--max-cost-usd", cap)
    assert (r.returncode, r.stdout) == (2, "")
    assert r.stderr == f"--max-cost-usd must be a number greater than 0; got '{cap}'\n"


def test_validate_flags_checks_candidates_syntax_before_cap_syntax() -> None:
    r = _run("validate-flags", "--candidates", "x", "--max-cost-usd", "y")
    assert r.stderr.startswith("--candidates must be")


def test_validate_flags_checks_cap_syntax_before_pairing() -> None:
    r = _run("validate-flags", "--candidates", "1", "--max-cost-usd", "y")
    assert r.stderr.startswith("--max-cost-usd must be a number")


def test_validate_flags_checks_pairing_before_jobs() -> None:
    r = _run("validate-flags", "--candidates", "2", "--jobs", "4")
    assert r.stderr == "--candidates N with N >= 2 requires --max-cost-usd\n"


def test_validate_flags_accepts_the_upper_bound_of_eight_candidates() -> None:
    assert build_candidates.validate_flags("8", "1", None)["candidates"] == 8


def test_validate_flags_raises_flag_error_for_a_pure_call() -> None:
    with pytest.raises(build_candidates.FlagError, match="got '9'"):
        build_candidates.validate_flags("9", "5", None)


def test_unknown_subcommand_is_a_usage_error_with_exit_two() -> None:
    assert _run("frobnicate").returncode == 2


# --- floor slice exemption (the module's own pass is run alongside this file) -


def test_floor_exclusions_map_build_candidates_to_a_non_empty_reason() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_floor_under_test", _FLOOR_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SLICE_EXCLUSIONS["build_candidates.py"].strip() != ""
