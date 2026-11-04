"""Pure tests for build_candidates.py (#2273): validate-flags, rank, the
Candidate model and project. Nothing here touches git. The git-facing
subcommands are in test_build_candidates_git.py; reconcile and the whole
lifecycle in test_build_candidates_integration.py.
"""

from __future__ import annotations

import json
import sys

import pytest
from _build_candidates_test_helpers import (
    SCENARIOS_TOTAL,
    SCRIPTS_DIR,
    make_candidate,
    run_cli,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import build_candidates

# --- validate-flags ---------------------------------------------------------

UNCHANGED_BUILD = {"candidates": 1, "max_cost_usd": None, "speculative": False}


@pytest.mark.parametrize(
    "args",
    [(), ("--candidates", "1")],
    ids=["no-flags", "candidates-1-alone"],
)
def test_validate_flags_accepts_the_unchanged_build_as_not_speculative(args) -> None:
    r = run_cli("validate-flags", *args)
    assert r.returncode == 0
    assert json.loads(r.stdout) == UNCHANGED_BUILD


def test_validate_flags_accepts_a_speculative_run() -> None:
    r = run_cli("validate-flags", "--candidates", "3", "--max-cost-usd", "12.5")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {
        "candidates": 3,
        "max_cost_usd": 12.5,
        "speculative": True,
    }


def test_validate_flags_prints_max_cost_as_a_number_not_a_string() -> None:
    r = run_cli("validate-flags", "--candidates", "2", "--max-cost-usd", "5")
    assert isinstance(json.loads(r.stdout)["max_cost_usd"], float)


@pytest.mark.parametrize("jobs", ["abc", "1"], ids=["not-a-number", "one"])
def test_validate_flags_leaves_non_parallel_jobs_to_build(jobs) -> None:
    r = run_cli(
        "validate-flags", "--candidates", "2", "--max-cost-usd", "5", "--jobs", jobs
    )
    assert r.returncode == 0
    assert json.loads(r.stdout)["speculative"] is True


def test_validate_flags_ignores_parallel_jobs_when_candidates_is_one() -> None:
    r = run_cli("validate-flags", "--candidates", "1", "--jobs", "4")
    assert r.returncode == 0
    assert json.loads(r.stdout) == UNCHANGED_BUILD


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


def _absent_if_empty(value: str) -> str | None:
    """The Scenario Outline convention: an empty value means the flag is absent."""
    return value or None


@pytest.mark.parametrize(
    "candidates,cap,jobs,message",
    _REJECTED,
    ids=[
        f"c={c or '-'},cap={cap or '-'},jobs={j or '-'}" for c, cap, j, _ in _REJECTED
    ],
)
def test_validate_flags_rejects_bad_combination_with_the_exact_message(
    candidates, cap, jobs, message
) -> None:
    with pytest.raises(build_candidates.FlagError) as raised:
        build_candidates.validate_flags(
            _absent_if_empty(candidates), _absent_if_empty(cap), _absent_if_empty(jobs)
        )
    assert str(raised.value) == message


@pytest.fixture(scope="module")
def rejected_run():
    """One real CLI run with a rejected combination, for the three pins."""
    return run_cli("validate-flags", "--candidates=0", "--max-cost-usd=5")


def test_a_rejected_flag_combination_exits_two(rejected_run) -> None:
    assert rejected_run.returncode == 2


def test_a_rejected_flag_combination_prints_nothing_on_stdout(rejected_run) -> None:
    assert rejected_run.stdout == ""


def test_a_rejected_flag_combination_prints_one_newline_terminated_stderr_line(
    rejected_run,
) -> None:
    assert (
        rejected_run.stderr
        == "--candidates must be an integer between 1 and 8; got '0'\n"
    )


@pytest.mark.parametrize(
    "flag,companion,message",
    [
        (
            "--max-cost-usd=-inf",
            "--candidates=2",
            "--max-cost-usd must be a number greater than 0; got '-inf'",
        ),
        (
            "--candidates=-abc",
            "--max-cost-usd=5",
            "--candidates must be an integer between 1 and 8; got '-abc'",
        ),
    ],
    ids=["cap-negative-inf", "candidates-negative-word"],
)
def test_validate_flags_gives_its_own_message_for_a_value_that_looks_like_a_flag(
    flag, companion, message
) -> None:
    r = run_cli("validate-flags", flag, companion)
    assert (r.returncode, r.stdout, r.stderr) == (2, "", message + "\n")


def test_validate_flags_cli_forwards_jobs_to_the_pairing_check() -> None:
    r = run_cli("validate-flags", "--candidates=2", "--max-cost-usd=5", "--jobs=2")
    message = "--candidates N with N >= 2 cannot be combined with --jobs greater than 1"
    assert (r.returncode, r.stdout, r.stderr) == (2, "", message + "\n")


def test_validate_flags_cli_treats_an_empty_candidates_value_as_given() -> None:
    r = run_cli("validate-flags", "--candidates=")
    message = "--candidates must be an integer between 1 and 8; got ''"
    assert (r.returncode, r.stdout, r.stderr) == (2, "", message + "\n")


def test_validate_flags_rejects_an_explicitly_empty_candidates_value() -> None:
    with pytest.raises(build_candidates.FlagError) as raised:
        build_candidates.validate_flags("", None, None)
    assert str(raised.value) == (
        "--candidates must be an integer between 1 and 8; got ''"
    )


def test_validate_flags_rejects_an_explicitly_empty_cap_value() -> None:
    with pytest.raises(build_candidates.FlagError) as raised:
        build_candidates.validate_flags("2", "", None)
    assert str(raised.value) == (
        "--max-cost-usd must be a number greater than 0; got ''"
    )


def test_validate_flags_rejects_non_ascii_digits_in_candidates() -> None:
    with pytest.raises(build_candidates.FlagError, match="--candidates must be an"):
        build_candidates.validate_flags("٣", "5", None)


@pytest.mark.parametrize(
    "cap",
    ["1_0", " 5", "5 ", "1e999", "+5"],
    ids=["underscore", "leading-space", "trailing-space", "overflow", "plus-sign"],
)
def test_validate_flags_rejects_cap_spellings_float_would_tolerate(cap) -> None:
    with pytest.raises(build_candidates.FlagError) as raised:
        build_candidates.validate_flags("2", cap, None)
    assert str(raised.value) == (
        f"--max-cost-usd must be a number greater than 0; got '{cap}'"
    )


@pytest.mark.parametrize(
    "cap,expected",
    [(".5", 0.5), ("5.", 5.0), ("1e3", 1000.0), ("02", 2.0)],
    ids=["leading-dot", "trailing-dot", "exponent", "leading-zero"],
)
def test_validate_flags_accepts_plain_ascii_decimal_cap_spellings(
    cap, expected
) -> None:
    assert build_candidates.validate_flags("2", cap, None)["max_cost_usd"] == expected


@pytest.mark.parametrize(
    "candidates",
    ["+5", ".5", "5.", "1e3"],
    ids=["plus-sign", "leading-dot", "trailing-dot", "exponent"],
)
def test_validate_flags_rejects_candidates_spellings_that_are_not_plain_integers(
    candidates,
) -> None:
    with pytest.raises(build_candidates.FlagError, match="--candidates must be an"):
        build_candidates.validate_flags(candidates, "5", None)


def test_validate_flags_accepts_a_leading_zero_candidates_count() -> None:
    assert build_candidates.validate_flags("02", "5", None)["candidates"] == 2


def test_validate_flags_checks_candidates_syntax_before_cap_syntax() -> None:
    with pytest.raises(build_candidates.FlagError, match="^--candidates must be"):
        build_candidates.validate_flags("x", "y", None)


def test_validate_flags_checks_cap_syntax_before_pairing() -> None:
    with pytest.raises(build_candidates.FlagError, match="^--max-cost-usd must be a"):
        build_candidates.validate_flags("1", "y", None)


def test_validate_flags_checks_pairing_before_jobs() -> None:
    with pytest.raises(build_candidates.FlagError) as raised:
        build_candidates.validate_flags("2", None, "4")
    assert str(raised.value) == "--candidates N with N >= 2 requires --max-cost-usd"


def test_validate_flags_accepts_the_upper_bound_of_eight_candidates() -> None:
    assert build_candidates.validate_flags("8", "1", None)["candidates"] == 8


def test_unknown_subcommand_is_a_usage_error_with_exit_two() -> None:
    r = run_cli("frobnicate")
    assert (r.returncode, r.stdout) == (2, "")
    assert "invalid choice: 'frobnicate'" in r.stderr


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
def test_reconcile_rejects_a_blank_test_command_as_a_usage_error(blank) -> None:
    r = run_cli(
        "reconcile",
        "--repo=.",
        "--into=build",
        "--base=HEAD",
        f"--test-cmd={blank}",
        "c1",
    )
    assert (r.returncode, r.stdout) == (2, "")
    assert "argument --test-cmd:" in r.stderr


# --- rank -------------------------------------------------------------------


def _write_candidates(tmp_path, candidates: list, name: str = "c.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    return str(path)


def _rank(tmp_path, candidates: list):
    return run_cli("rank", "--candidates-json", _write_candidates(tmp_path, candidates))


def test_rank_orders_by_scenarios_met_before_review_findings(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [make_candidate(1, errors=1), make_candidate(2, met=4), make_candidate(3)],
    )
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
            make_candidate(2, errors=1, diff_lines=10, cost_usd=0.1),
            make_candidate(1, errors=1, diff_lines=10, cost_usd=9.0),
            make_candidate(3, warnings=5, diff_lines=100),
            make_candidate(4, warnings=2, diff_lines=200),
            make_candidate(5, warnings=2, diff_lines=150),
        ],
    )
    assert json.loads(r.stdout)["order"] == [5, 4, 3, 1, 2]


def test_rank_disqualifies_red_suite_and_unparseable_screening(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            make_candidate(1, suite_green=False, warnings=3),
            make_candidate(2, met=3, errors=2),
            make_candidate(3, screening="unparseable: correctness-review"),
        ],
    )
    out = json.loads(r.stdout)
    assert (out["winner"], out["order"], out["disqualified"]) == (2, [2, 3, 1], [1, 3])


def test_rank_reports_why_each_candidate_is_disqualified(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            make_candidate(1, suite_green=False),
            make_candidate(2),
            make_candidate(3, screening="unparseable: correctness-review"),
        ],
    )
    assert json.loads(r.stdout)["reasons"] == {
        "1": "red suite",
        "2": "",
        "3": "screening: correctness-review unparseable",
    }


def test_rank_names_the_red_suite_when_the_screening_is_also_unparseable(
    tmp_path,
) -> None:
    r = _rank(
        tmp_path,
        [make_candidate(1, suite_green=False, screening="unparseable: x-review")],
    )
    assert json.loads(r.stdout)["reasons"] == {"1": "red suite"}


def test_rank_all_red_yields_no_winner_and_exits_zero(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            make_candidate(1, met=2, suite_green=False),
            make_candidate(2, met=4, suite_green=False),
        ],
    )
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert (out["winner"], out["order"], out["disqualified"]) == (None, [2, 1], [1, 2])


def test_rank_accepts_a_lone_candidate(tmp_path) -> None:
    r = _rank(tmp_path, [make_candidate(1)])
    assert r.returncode == 0
    assert json.loads(r.stdout) == {
        "disqualified": [],
        "order": [1],
        "rank": {"1": 1},
        "reasons": {"1": ""},
        "scenarios_met": {"1": SCENARIOS_TOTAL},
        "winner": 1,
    }


def test_rank_lists_disqualified_ids_in_id_order_whatever_the_ranking(tmp_path) -> None:
    r = _rank(
        tmp_path,
        [
            make_candidate(3, suite_green=False),
            make_candidate(1, met=2, suite_green=False),
            make_candidate(2),
        ],
    )
    out = json.loads(r.stdout)
    assert (out["order"], out["disqualified"]) == ([2, 3, 1], [1, 3])


def test_rank_prints_sorted_keys_on_one_newline_terminated_line(tmp_path) -> None:
    r = _rank(tmp_path, [make_candidate(1, met=2), make_candidate(2)])
    assert r.stdout == (
        '{"disqualified": [], "order": [2, 1], "rank": {"1": 2, "2": 1}, '
        '"reasons": {"1": "", "2": ""}, '
        '"scenarios_met": {"1": 2, "2": 5}, "winner": 2}\n'
    )


def test_rank_places_a_no_commits_candidate_below_a_green_one(tmp_path) -> None:
    no_commits = make_candidate(1, met=0, branch="", suite_green=False)
    r = _rank(tmp_path, [no_commits, make_candidate(2, met=4)])
    out = json.loads(r.stdout)
    assert (out["winner"], out["disqualified"]) == (2, [1])


_ORDER_SENSITIVE_CANDIDATES = [
    make_candidate(1, met=4, errors=1, warnings=3),
    make_candidate(2, errors=1, warnings=2),
    make_candidate(3, met=3, warnings=1),
    make_candidate(4, errors=1, warnings=2, diff_lines=5),
    make_candidate(5, suite_green=False),
]


def test_rank_output_is_byte_identical_for_any_input_order(tmp_path) -> None:
    forward = _write_candidates(tmp_path, _ORDER_SENSITIVE_CANDIDATES, "a.json")
    backward = _write_candidates(tmp_path, _ORDER_SENSITIVE_CANDIDATES[::-1], "b.json")
    first = run_cli("rank", "--candidates-json", forward)
    second = run_cli("rank", "--candidates-json", backward)
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["order"] == [4, 2, 1, 3, 5]


def test_rank_scenarios_met_reports_met_count_per_candidate(tmp_path) -> None:
    r = _rank(tmp_path, [make_candidate(1), make_candidate(2, met=2)])
    assert json.loads(r.stdout)["scenarios_met"] == {"1": 5, "2": 2}


_MALFORMED = [
    (
        "two candidates sharing id 2",
        [make_candidate(2), make_candidate(1), make_candidate(2)],
        "duplicate candidate id 2",
    ),
    (
        "a candidate missing the errors field",
        [{k: v for k, v in make_candidate(1).items() if k != "errors"}],
        "errors",
    ),
    (
        "a candidate with diff_lines -3",
        [make_candidate(1, diff_lines=-3)],
        "diff_lines",
    ),
    (
        "a candidate with suite_green 1",
        [make_candidate(1, suite_green=1)],
        "suite_green",
    ),
    (
        "a candidate with scenarios_unmet 6 of total 5",
        [make_candidate(1, scenarios_unmet=6)],
        "scenarios_unmet",
    ),
    (
        "a candidate with cost_usd -0.1",
        [make_candidate(1, cost_usd=-0.1)],
        "cost_usd",
    ),
    (
        "a candidate with screening maybe",
        [make_candidate(1, screening="maybe")],
        "screening",
    ),
    ("an empty candidates list", [], "no candidates"),
]


@pytest.mark.parametrize(
    "candidates,expected_message",
    [(c, m) for _, c, m in _MALFORMED],
    ids=[d for d, _, _ in _MALFORMED],
)
def test_rank_rejects_malformed_candidates_with_exit_one(
    tmp_path, candidates, expected_message
) -> None:
    r = _rank(tmp_path, candidates)
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert expected_message in r.stderr


def test_rank_rejects_a_file_that_is_not_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json at all", encoding="utf-8")
    r = run_cli("rank", "--candidates-json", str(path))
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert "not JSON" in r.stderr


def test_rank_rejects_a_path_that_does_not_exist(tmp_path) -> None:
    r = run_cli("rank", "--candidates-json", str(tmp_path / "missing.json"))
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("rank:")
    assert "no such file" in r.stderr


def test_rank_rejects_a_candidates_value_that_is_not_a_list(tmp_path) -> None:
    path = tmp_path / "obj.json"
    path.write_text(json.dumps({"candidates": {"id": 1}}), encoding="utf-8")
    r = run_cli("rank", "--candidates-json", str(path))
    assert (r.returncode, r.stdout) == (1, "")
    assert "must be a list" in r.stderr


def test_rank_ignores_unknown_keys_in_the_file_and_in_candidates(tmp_path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps({"candidates": [make_candidate(1, note="x")], "other": 1}),
        encoding="utf-8",
    )
    r = run_cli("rank", "--candidates-json", str(path))
    assert json.loads(r.stdout)["winner"] == 1


# --- Candidate / sort_key (pure) --------------------------------------------


def test_from_dict_rejects_a_bool_id() -> None:
    with pytest.raises(ValueError, match="id must be a positive int"):
        build_candidates.Candidate.from_dict(make_candidate(True))


def test_from_dict_rejects_an_empty_branch_on_a_green_suite() -> None:
    with pytest.raises(ValueError, match="candidate 1: branch"):
        build_candidates.Candidate.from_dict(make_candidate(1, branch=""))


def test_from_dict_accepts_an_empty_branch_on_a_red_suite() -> None:
    c = build_candidates.Candidate.from_dict(
        make_candidate(1, branch="", suite_green=False)
    )
    assert c.branch == ""


def test_from_dict_rejects_a_non_finite_cost() -> None:
    with pytest.raises(ValueError, match="cost_usd"):
        build_candidates.Candidate.from_dict(make_candidate(1, cost_usd=float("inf")))


def test_from_dict_rejects_an_integer_cost_too_large_for_a_float() -> None:
    with pytest.raises(ValueError, match="candidate 1: cost_usd"):
        build_candidates.Candidate.from_dict(make_candidate(1, cost_usd=10**400))


def test_from_dict_rejects_a_bare_unparseable_screening() -> None:
    with pytest.raises(ValueError, match="screening"):
        build_candidates.Candidate.from_dict(
            make_candidate(1, screening="unparseable: ")
        )


def test_from_dict_names_the_id_of_the_failing_candidate() -> None:
    with pytest.raises(ValueError, match="candidate 7:"):
        build_candidates.Candidate.from_dict(make_candidate(7, errors=-1))


def test_from_dict_normalizes_an_integer_cost_to_float() -> None:
    c = build_candidates.Candidate.from_dict(make_candidate(1, cost_usd=2))
    assert isinstance(c.cost_usd, float)


def test_disqualified_is_true_for_a_red_suite_and_false_for_green_ok() -> None:
    from_dict = build_candidates.Candidate.from_dict
    assert build_candidates.disqualified(
        from_dict(make_candidate(1, suite_green=False))
    )
    assert not build_candidates.disqualified(from_dict(make_candidate(1)))


def test_sort_key_ignores_cost_usd() -> None:
    from_dict = build_candidates.Candidate.from_dict
    cheap = from_dict(make_candidate(1, cost_usd=0.1))
    dear = from_dict(make_candidate(1, cost_usd=99))
    assert build_candidates.sort_key(cheap) == build_candidates.sort_key(dear)


def test_no_commits_factory_builds_a_red_all_unmet_candidate_with_zero_findings() -> (
    None
):
    candidate = build_candidates.Candidate.no_commits(3, "", 4, 1.5)
    assert candidate == build_candidates.Candidate(
        id=3,
        branch="",
        suite_green=False,
        scenarios_total=4,
        scenarios_unmet=4,
        errors=0,
        warnings=0,
        diff_lines=0,
        cost_usd=1.5,
        screening="ok",
    )


def test_no_commits_factory_rejects_an_invalid_id() -> None:
    with pytest.raises(ValueError, match="id must be a positive int"):
        build_candidates.Candidate.no_commits(0, "", 4, 1.5)


# --- project ----------------------------------------------------------------


def _project(cap, spent, completed, remaining, delta):
    return run_cli(
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


_VALID_PROJECT_ARGS = {
    "--cap": "10",
    "--spent": "1",
    "--completed": "1",
    "--remaining": "1",
    "--last-batch-delta": "1",
}

_BAD_PROJECT_ARGS = [
    ("--cap", "0"),
    ("--cap", "inf"),
    ("--spent", "-1"),
    ("--spent", "nan"),
    ("--completed", "1.5"),
    ("--completed", "0"),
    ("--completed", "9"),
    ("--remaining", "0"),
    ("--remaining", "8"),
    ("--last-batch-delta", "-1"),
]


@pytest.mark.parametrize(
    "flag,bad_value",
    _BAD_PROJECT_ARGS,
    ids=[f"{flag}={value}" for flag, value in _BAD_PROJECT_ARGS],
)
def test_project_rejects_out_of_range_arguments_with_exit_two(flag, bad_value) -> None:
    args = {**_VALID_PROJECT_ARGS, flag: bad_value}
    r = run_cli("project", *(part for pair in args.items() for part in pair))
    assert (r.returncode, r.stdout) == (2, "")
    assert f"argument {flag}:" in r.stderr


def test_project_accepts_the_largest_completed_and_remaining_counts() -> None:
    r = _project(10, 1, 8, 7, 1)
    assert r.returncode == 0


def test_project_requires_every_argument() -> None:
    r = run_cli("project", "--cap", "10")
    assert (r.returncode, r.stdout) == (2, "")
    assert "the following arguments are required" in r.stderr
