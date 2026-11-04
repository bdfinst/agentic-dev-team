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


@pytest.mark.parametrize("cap", ["1_0", " 5", "5 ", "1e999"])
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


# --- rank -------------------------------------------------------------------


def _cand(cid: int, **overrides) -> dict:
    """A green, fully-met, finding-free candidate dict; override per case."""
    base = {
        "id": cid,
        "branch": f"worktree-c{cid}",
        "suite_green": True,
        "scenarios_total": 5,
        "scenarios_unmet": 0,
        "errors": 0,
        "warnings": 0,
        "diff_lines": 10,
        "cost_usd": 0.5,
        "screening": "ok",
    }
    base.update(overrides)
    return base


def _met(cid: int, met: int, **overrides) -> dict:
    return _cand(cid, scenarios_unmet=5 - met, **overrides)


def _write_candidates(tmp_path, candidates: list, name: str = "c.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    return str(path)


def _rank(tmp_path, candidates: list):
    return _run("rank", "--candidates", _write_candidates(tmp_path, candidates))


def test_rank_orders_by_scenarios_met_before_review_findings(tmp_path) -> None:
    r = _rank(tmp_path, [_met(1, 5, errors=1), _met(2, 4), _met(3, 5)])
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert out["order"] == [3, 1, 2]
    assert out["winner"] == 3
    assert out["rank"] == {"3": 1, "1": 2, "2": 3}


def test_rank_breaks_ties_by_errors_then_warnings_then_diff_lines_then_id(
    tmp_path,
) -> None:
    r = _rank(
        tmp_path,
        [
            _cand(2, errors=1, diff_lines=10, cost_usd=0.1),
            _cand(1, errors=1, diff_lines=10, cost_usd=9.0),
            _cand(3, warnings=5, diff_lines=100),
            _cand(4, warnings=2, diff_lines=200),
            _cand(5, warnings=2, diff_lines=150),
        ],
    )
    assert json.loads(r.stdout)["order"] == [5, 4, 3, 1, 2]


def test_rank_disqualifies_red_suite_and_unparseable_screening(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            _cand(1, suite_green=False, warnings=3),
            _met(2, 3, errors=2),
            _cand(3, screening="unparseable: correctness-review"),
        ],
    )
    out = json.loads(r.stdout)
    assert (out["winner"], out["order"], out["disqualified"]) == (2, [2, 3, 1], [1, 3])


def test_rank_all_red_yields_no_winner_and_exits_zero(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            _met(1, 2, suite_green=False, cost_usd=0.5),
            _met(2, 4, suite_green=False, cost_usd=0.5),
        ],
    )
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert (out["winner"], out["order"], out["disqualified"]) == (None, [2, 1], [1, 2])


def test_rank_accepts_a_lone_candidate(tmp_path) -> None:
    r = _rank(tmp_path, [_cand(1)])
    assert r.returncode == 0
    assert json.loads(r.stdout) == {
        "disqualified": [],
        "order": [1],
        "rank": {"1": 1},
        "scenarios_met": {"1": 5},
        "winner": 1,
    }


def test_rank_lists_disqualified_ids_in_id_order_whatever_the_ranking(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [_met(3, 5, suite_green=False), _met(1, 2, suite_green=False), _cand(2)],
    )
    out = json.loads(r.stdout)
    assert (out["order"], out["disqualified"]) == ([2, 3, 1], [1, 3])


def test_rank_prints_sorted_keys_on_one_newline_terminated_line(tmp_path) -> None:
    r = _rank(tmp_path, [_met(1, 2), _met(2, 5)])
    assert r.stdout == (
        '{"disqualified": [], "order": [2, 1], "rank": {"1": 2, "2": 1}, '
        '"scenarios_met": {"1": 2, "2": 5}, "winner": 2}\n'
    )


def test_rank_places_a_no_commits_candidate_below_a_green_one(tmp_path) -> None:
    no_commits = _cand(1, branch="", suite_green=False, scenarios_unmet=5)
    r = _rank(tmp_path, [no_commits, _met(2, 4)])
    out = json.loads(r.stdout)
    assert (out["winner"], out["disqualified"]) == (2, [1])


def test_rank_output_is_byte_identical_for_any_input_order(tmp_path) -> None:
    cands = [_met(i, 5 - i % 3, errors=i % 2, warnings=i) for i in range(1, 6)]
    first = _run("rank", "--candidates", _write_candidates(tmp_path, cands, "a.json"))
    second = _run(
        "rank", "--candidates", _write_candidates(tmp_path, cands[::-1], "b.json")
    )
    assert first.stdout == second.stdout
    assert first.stdout.endswith("}\n")


def test_rank_scenarios_met_reports_met_count_per_candidate(tmp_path) -> None:
    r = _rank(tmp_path, [_met(1, 5), _met(2, 2)])
    assert json.loads(r.stdout)["scenarios_met"] == {"1": 5, "2": 2}


_MALFORMED = [
    ("two candidates sharing id 2", [_cand(2), _cand(1), _cand(2)], "2"),
    (
        "a candidate missing the errors field",
        [{k: v for k, v in _cand(1).items() if k != "errors"}],
        "errors",
    ),
    ("a candidate with diff_lines -3", [_cand(1, diff_lines=-3)], "diff_lines"),
    ("a candidate with suite_green 1", [_cand(1, suite_green=1)], "suite_green"),
    (
        "a candidate with scenarios_unmet 6 of total 5",
        [_cand(1, scenarios_unmet=6)],
        "scenarios_unmet",
    ),
    ("a candidate with cost_usd -0.1", [_cand(1, cost_usd=-0.1)], "cost_usd"),
    ("a candidate with screening maybe", [_cand(1, screening="maybe")], "screening"),
    ("an empty candidates list", [], "no candidates"),
]


@pytest.mark.parametrize(
    "candidates,names",
    [(c, n) for _, c, n in _MALFORMED],
    ids=[d for d, _, _ in _MALFORMED],
)
def test_rank_rejects_malformed_candidates_with_exit_one(
    tmp_path, candidates, names
) -> None:
    r = _rank(tmp_path, candidates)
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert names in r.stderr


def test_rank_rejects_a_file_that_is_not_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json at all", encoding="utf-8")
    r = _run("rank", "--candidates", str(path))
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert "not JSON" in r.stderr


def test_rank_rejects_a_path_that_does_not_exist(tmp_path) -> None:
    r = _run("rank", "--candidates", str(tmp_path / "missing.json"))
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert "no such file" in r.stderr


def test_rank_rejects_a_candidates_value_that_is_not_a_list(tmp_path) -> None:
    path = tmp_path / "obj.json"
    path.write_text(json.dumps({"candidates": {"id": 1}}), encoding="utf-8")
    r = _run("rank", "--candidates", str(path))
    assert (r.returncode, r.stdout) == (1, "")
    assert "must be a list" in r.stderr


def test_rank_ignores_unknown_keys_in_the_file_and_in_candidates(tmp_path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps({"candidates": [_cand(1, note="x")], "other": 1}),
        encoding="utf-8",
    )
    assert json.loads(_run("rank", "--candidates", str(path)).stdout)["winner"] == 1


# --- Candidate / sort_key (pure) --------------------------------------------


def test_from_dict_rejects_a_bool_id() -> None:
    with pytest.raises(ValueError, match="id must be a positive int"):
        build_candidates.Candidate.from_dict(_cand(True))


def test_from_dict_rejects_an_empty_branch_on_a_green_suite() -> None:
    with pytest.raises(ValueError, match="candidate 1: branch"):
        build_candidates.Candidate.from_dict(_cand(1, branch=""))


def test_from_dict_accepts_an_empty_branch_on_a_red_suite() -> None:
    c = build_candidates.Candidate.from_dict(_cand(1, branch="", suite_green=False))
    assert c.branch == ""


def test_from_dict_rejects_a_non_finite_cost() -> None:
    with pytest.raises(ValueError, match="cost_usd"):
        build_candidates.Candidate.from_dict(_cand(1, cost_usd=float("inf")))


def test_from_dict_rejects_a_bare_unparseable_screening() -> None:
    with pytest.raises(ValueError, match="screening"):
        build_candidates.Candidate.from_dict(_cand(1, screening="unparseable: "))


def test_from_dict_names_the_id_of_the_failing_candidate() -> None:
    with pytest.raises(ValueError, match="candidate 7:"):
        build_candidates.Candidate.from_dict(_cand(7, errors=-1))


def test_from_dict_normalizes_an_integer_cost_to_float() -> None:
    c = build_candidates.Candidate.from_dict(_cand(1, cost_usd=2))
    assert isinstance(c.cost_usd, float)


def test_disqualified_is_true_for_a_red_suite_and_false_for_green_ok() -> None:
    from_dict = build_candidates.Candidate.from_dict
    assert build_candidates.disqualified(from_dict(_cand(1, suite_green=False)))
    assert not build_candidates.disqualified(from_dict(_cand(1)))


def test_sort_key_ignores_cost_usd() -> None:
    from_dict = build_candidates.Candidate.from_dict
    cheap, dear = from_dict(_cand(1, cost_usd=0.1)), from_dict(_cand(1, cost_usd=99))
    assert build_candidates.sort_key(cheap) == build_candidates.sort_key(dear)


# --- project ----------------------------------------------------------------


def _project(cap, spent, completed, remaining, delta):
    return _run(
        "project",
        "--cap",
        str(cap),
        "--spent",
        str(spent),
        "--completed",
        str(completed),
        "--remaining",
        str(remaining),
        "--last-batch-delta",
        str(delta),
    )


def test_project_continues_when_the_projection_equals_the_cap() -> None:
    r = _project(10, 4, 2, 3, 2)
    out = json.loads(r.stdout)
    assert (r.returncode, out["decision"], out["projected"], out["reason"]) == (
        0,
        "continue",
        10,
        "",
    )


def test_project_stops_when_the_projection_exceeds_the_cap() -> None:
    out = json.loads(_project(10, 4.5, 2, 3, 2.25).stdout)
    assert (out["decision"], out["projected"], out["reason"]) == (
        "stop",
        11.25,
        "projected spend exceeds the cap",
    )


def test_project_stops_once_spend_reaches_the_cap() -> None:
    out = json.loads(_project(10, 10, 3, 1, 3).stdout)
    assert (out["decision"], out["reason"]) == ("stop", "spent has reached the cap")


def test_project_halts_when_the_meter_saw_no_spend() -> None:
    out = json.loads(_project(10, 0, 1, 2, 0).stdout)
    assert out["decision"] == "halt"
    assert "cost meter recorded no spend for the last batch" in out["reason"]


def test_project_halts_on_zero_delta_even_when_spend_has_reached_the_cap() -> None:
    assert json.loads(_project(10, 12, 2, 1, 0).stdout)["decision"] == "halt"


def test_project_output_has_exactly_the_documented_keys_on_one_line() -> None:
    r = _project(10, 4, 2, 3, 2)
    assert list(json.loads(r.stdout)) == [
        "cap",
        "completed",
        "decision",
        "last_batch_delta",
        "projected",
        "reason",
        "remaining",
        "spent",
    ]
    assert r.stdout.count("\n") == 1


def test_project_rounds_projected_to_four_decimals() -> None:
    out = json.loads(_project(100, 1, 3, 1, 1).stdout)
    assert out["projected"] == 1.3333


_BAD_PROJECT_ARGS = [
    ("0", "1", "1", "1", "1"),
    ("10", "-1", "1", "1", "1"),
    ("10", "1", "1.5", "1", "1"),
    ("10", "1", "0", "1", "1"),
    ("10", "1", "1", "0", "1"),
    ("inf", "1", "1", "1", "1"),
    ("10", "nan", "1", "1", "1"),
    ("10", "1", "1", "1", "-1"),
]


@pytest.mark.parametrize("cap,spent,completed,remaining,delta", _BAD_PROJECT_ARGS)
def test_project_rejects_out_of_range_arguments_with_exit_two(
    cap, spent, completed, remaining, delta
) -> None:
    r = _project(cap, spent, completed, remaining, delta)
    assert (r.returncode, r.stdout) == (2, "")
    assert "usage" in r.stderr


def test_project_requires_every_argument() -> None:
    r = _run("project", "--cap", "10")
    assert (r.returncode, r.stdout) == (2, "")


# --- floor slice exemption (the module's own pass is run alongside this file) -


def test_floor_exclusions_map_build_candidates_to_a_non_empty_reason() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_floor_under_test", _FLOOR_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SLICE_EXCLUSIONS["build_candidates.py"].strip() != ""
