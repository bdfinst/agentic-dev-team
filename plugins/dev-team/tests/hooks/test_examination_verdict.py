"""Unit tests for hooks/lib/examination_verdict.py (#2270, Step 1.2)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import examination_verdict as ev  # type: ignore[import-not-found]
from examination_store import Binding  # type: ignore[import-not-found]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pytest  -q", "pytest -q"),
        ("  pytest\t-q\n", "pytest -q"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_command_collapses_whitespace(raw, expected):
    assert ev.normalize_command(command=raw) == expected


@pytest.mark.parametrize(
    ("calls", "expected"),
    [
        (["cd repo && pytest -q 2>&1 | tail -20"], {"pytest -q", "tail -20"}),
        (["a && b || c ; d | e"], {"a", "b", "c", "d", "e"}),
        (["pytest -q >&2"], {"pytest -q"}),
        (["pytest -q 1>&2"], {"pytest -q"}),
        (["pytest  -q"], {"pytest -q"}),
        (["cd repo"], set()),
        (["echo hi && cd repo"], {"echo hi", "cd repo"}),
        (["pytest -q", "ruff check"], {"pytest -q", "ruff check"}),
        ([], set()),
        ([""], set()),
    ],
)
def test_ran_segments_splits_calls_into_normalized_segments(calls, expected):
    assert ev.ran_segments(calls) == expected


def _row(verdict):
    return {"criterion": "AC1", "verdict": verdict}


_FINDING = {"kind": "read", "target": "src/app.py", "command": "cat src/app.py"}


@pytest.mark.parametrize(
    ("rows", "findings", "problems", "expected"),
    [
        ([_row("met"), _row("met")], [], [], "met"),
        ([_row("met"), _row("not-met")], [], [], "not-met"),
        ([_row("met"), _row("indeterminate")], [], [], "indeterminate"),
        ([_row("not-met"), _row("indeterminate")], [], [], "not-met"),
        ([_row("met")], [], ["missing AC2"], "indeterminate"),
        ([_row("not-met")], [], ["missing AC2"], "indeterminate"),
        ([_row("met")], [_FINDING], [], "tainted"),
        ([_row("not-met")], [_FINDING], ["missing AC2"], "tainted"),
    ],
)
def test_derive_overall_applies_precedence(rows, findings, problems, expected):
    assert ev.derive_overall(rows, findings, problems) == expected


def test_vocabulary_constants():
    assert ev.VERDICTS == ("met", "not-met", "indeterminate")
    assert ev.TAINTED == "tainted"
    assert ev.TAINTED not in ev.VERDICTS


_IDS = ["AC1", "AC2", "AC3"]


def _full_row(cid="AC1", verdict="met", command="pytest -q", observation="exit 0"):
    return {
        "criterion": cid,
        "verdict": verdict,
        "command": command,
        "observation": observation,
    }


def _derive(result, ids, ran):
    """validate_rows then derive_overall, as the SubagentStop hook does."""
    rows, problems = ev.validate_rows(result, ids, ran)
    return ev.derive_overall(rows, [], problems), problems


def test_complete_met_result_derives_met_with_no_problems():
    result = {"criteria": [_full_row(cid) for cid in _IDS]}
    ran = ["cd repo && pytest -q 2>&1 | tail -20"]
    assert _derive(result, _IDS, ran) == ("met", [])


def test_usable_rows_are_returned_for_a_complete_result():
    rows = [_full_row(cid) for cid in _IDS]
    usable, _ = ev.validate_rows({"criteria": rows}, _IDS, ["pytest -q"])
    assert usable == rows


def test_plan_without_criteria_is_never_met():
    overall, problems = _derive({"criteria": []}, [], [])
    assert overall == "indeterminate"
    assert "no-acceptance-criteria" in problems


@pytest.mark.parametrize(
    ("row_ids", "problem"),
    [
        ([], "missing AC1,AC2,AC3"),
        (["AC1", "AC2"], "missing AC3"),
        (["AC1", "AC1", "AC2", "AC3"], "duplicate AC1"),
        (["AC1", "AC2", "AC3", "AC9"], "unknown AC9"),
    ],
)
def test_incomplete_result_never_derives_met(row_ids, problem):
    result = {"criteria": [_full_row(cid) for cid in row_ids]}
    overall, problems = _derive(result, _IDS, ["pytest -q"])
    assert overall == "indeterminate"
    assert problem in problems


def test_triplicate_row_is_reported_as_one_duplicate_problem():
    result = {"criteria": [_full_row("AC1")] * 3}
    _, problems = ev.validate_rows(result, ["AC1"], ["pytest -q"])
    assert problems == ["duplicate AC1"]


_ABSENT = object()


@pytest.mark.parametrize(
    ("command", "observation"),
    [
        ("", "exit 0"),
        ("   ", "exit 0"),
        ("pytest -q", ""),
        ("pytest -q", "   "),
        ("pytest -q", _ABSENT),
        (_ABSENT, "exit 0"),
        ("pytest -q", 3),
    ],
)
def test_met_row_lacking_evidence_is_incomplete(command, observation):
    row = _full_row(command=command, observation=observation)
    row = {k: v for k, v in row.items() if v is not _ABSENT}
    overall, problems = _derive({"criteria": [row]}, ["AC1"], ["pytest -q"])
    assert overall == "indeterminate"
    assert "incomplete-row AC1" in problems
    assert "command-not-run AC1" not in problems


def test_indeterminate_row_needs_reason_but_not_command():
    row = _full_row(
        verdict="indeterminate", command="", observation="no HTTP entry point is named"
    )
    assert _derive({"criteria": [row]}, ["AC1"], []) == ("indeterminate", [])


def test_indeterminate_row_without_reason_is_incomplete():
    row = _full_row(verdict="indeterminate", command="", observation="")
    _, problems = _derive({"criteria": [row]}, ["AC1"], [])
    assert problems == ["incomplete-row AC1"]


@pytest.mark.parametrize("verdict", ["pass", "tainted"])
def test_verdict_outside_vocabulary_is_a_problem(verdict):
    result = {"criteria": [_full_row(verdict=verdict)]}
    overall, problems = _derive(result, ["AC1"], ["pytest -q"])
    assert overall == "indeterminate"
    assert f"invalid-verdict AC1 {verdict}" in problems


@pytest.mark.parametrize(
    ("verdict", "ran", "overall", "problems"),
    [
        ("met", ["cd repo && pytest  -q | tail"], "met", []),
        ("met", ["pytest -x"], "indeterminate", ["command-not-run AC1"]),
        ("met", ["pytest -xq"], "indeterminate", ["command-not-run AC1"]),
        ("met", ["echo pytest -q"], "indeterminate", ["command-not-run AC1"]),
        ("not-met", [], "indeterminate", ["command-not-run AC1"]),
    ],
)
def test_claimed_command_must_be_a_ran_segment(verdict, ran, overall, problems):
    result = {"criteria": [_full_row(verdict=verdict)]}
    assert _derive(result, ["AC1"], ran) == (overall, problems)


def test_claimed_pipeline_is_not_one_complete_segment():
    row = _full_row(command="pytest -q | tail")
    _, problems = _derive({"criteria": [row]}, ["AC1"], ["pytest -q | tail"])
    assert problems == ["command-not-run AC1"]


def test_claimed_command_with_leading_cd_matches_the_bare_segment():
    row = _full_row(command="cd repo && pytest -q")
    assert _derive({"criteria": [row]}, ["AC1"], ["pytest -q"]) == ("met", [])


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"criteria": "AC1"},
        {"criteria": ["AC1"]},
        {"criteria": [_full_row(verdict=3)]},
        {"criteria": [{"verdict": "met"}]},
        {"criteria": [_full_row(cid=1)]},
        ["criteria"],
        None,
        "met",
    ],
)
def test_wrong_shaped_result_is_a_problem_not_an_exception(result):
    rows, problems = ev.validate_rows(result, ["AC1"], ["pytest -q"])
    assert rows == []
    assert problems == ["invalid-result-shape"]
    assert _derive(result, ["AC1"], ["pytest -q"])[0] == "indeterminate"


def test_wrong_shaped_result_with_no_criteria_reports_both_problems():
    _, problems = ev.validate_rows(None, [], [])
    assert problems == ["invalid-result-shape", "no-acceptance-criteria"]


@pytest.mark.parametrize("verdict", ["not-met", "indeterminate"])
def test_failing_row_sets_the_overall_verdict(verdict):
    command = "" if verdict == "indeterminate" else "pytest -q"
    rows = [_full_row("AC1"), _full_row("AC2", verdict=verdict, command=command)]
    assert _derive({"criteria": rows}, ["AC1", "AC2"], ["pytest -q"]) == (verdict, [])


def test_not_met_row_with_missing_sibling_is_indeterminate():
    result = {"criteria": [_full_row("AC1", verdict="not-met")]}
    overall, problems = _derive(result, ["AC1", "AC2"], ["pytest -q"])
    assert overall == "indeterminate"
    assert "missing AC2" in problems


def test_forbidden_read_outranks_every_row_verdict():
    rows, problems = ev.validate_rows(
        {"criteria": [_full_row(cid) for cid in _IDS]}, _IDS, ["pytest -q"]
    )
    assert ev.derive_overall(rows, [_FINDING], problems) == "tainted"


def test_rows_with_problems_are_not_usable():
    rows = [_full_row("AC1"), _full_row("AC2", observation=""), _full_row("AC9")]
    usable, _ = ev.validate_rows({"criteria": rows}, ["AC1", "AC2"], ["pytest -q"])
    assert [row["criterion"] for row in usable] == ["AC1"]


def _record(rows=(), findings=(), problems=()):
    return ev.build_record(
        "plans/x.md",
        list(rows),
        list(findings),
        list(problems),
        Binding("bh", "id"),
        "agent-1",
    )


def test_build_record_carries_every_field():
    rows = [_full_row()]
    record = _record(rows)
    assert set(record) == set(ev.RECORD_KEYS)
    assert set(ev.RECORD_KEYS) == {
        "schema",
        "plan",
        "agent_id",
        "overall",
        "criteria",
        "audit_findings",
        "problems",
        "binding_hash",
        "inputs_digest",
        "recorded_at",
    }
    assert record["schema"] == 1
    assert record["plan"] == "plans/x.md"
    assert record["agent_id"] == "agent-1"
    assert record["criteria"] == rows
    assert (record["binding_hash"], record["inputs_digest"]) == ("bh", "id")
    assert record["problems"] == []


def test_build_record_derives_overall_from_rows_findings_and_problems():
    assert _record([_full_row()])["overall"] == "met"
    assert _record([_full_row(verdict="not-met")])["overall"] == "not-met"
    assert (
        _record([_full_row()], problems=["missing AC2"])["overall"] == "indeterminate"
    )
    assert _record([_full_row()], findings=[_FINDING])["overall"] == "tainted"


def test_build_record_keeps_only_kind_target_command_of_findings():
    finding = {**_FINDING, "extra": "dropped"}
    assert _record(findings=[finding])["audit_findings"] == [_FINDING]


def test_build_record_recorded_at_is_iso_8601_utc():
    stamp = datetime.fromisoformat(_record()["recorded_at"])
    assert stamp.utcoffset() == timedelta(0)
    assert abs(datetime.now(timezone.utc) - stamp) < timedelta(minutes=1)


def test_build_record_is_json_serializable():
    assert json.loads(json.dumps(_record([_full_row()], [_FINDING], ["x"])))


# --- review-fix additions (#2270) ---------------------------------------------


@pytest.mark.parametrize(
    "criterion", ["AC9 extra", "ac1", "AC", "AC1\n", " AC1", "AC١"]
)
def test_criterion_id_outside_the_ac_grammar_is_an_invalid_shape(criterion):
    result = {"criteria": [_full_row(cid=criterion)]}
    rows, problems = ev.validate_rows(result, ["AC1"], ["pytest -q"])
    assert rows == []
    assert problems == ["invalid-result-shape"]


def test_problem_vocabulary_lives_with_the_writer():
    assert ev.PROBLEM_UNPARSEABLE == "unparseable-result"
    assert ev.PROBLEM_BASE_UNRESOLVABLE == "binding-hash-unavailable"


@pytest.mark.parametrize(
    "call",
    ["pytest -q\nls", "ls\npytest -q", "ls\r\npytest -q", "cd repo\npytest -q"],
)
def test_a_multi_line_call_is_several_segments(call):
    row = _full_row(command="pytest -q")
    assert _derive({"criteria": [row]}, ["AC1"], [call]) == ("met", [])


def test_a_claimed_multi_line_command_is_not_one_segment():
    row = _full_row(command="pytest -q\nls")
    _, problems = _derive({"criteria": [row]}, ["AC1"], ["pytest -q\nls"])
    assert problems == ["command-not-run AC1"]


@pytest.mark.parametrize(
    "call",
    [
        "pytest -q 2>&1| tail",
        "pytest -q 2>&1 | tail",
        "pytest -q 2>&1|tail",
        "pytest -q >&2| tail",
        "pytest -q 1>&2|tail",
        "pytest -q 2>&1&& tail",
    ],
)
def test_fd_duplication_is_stripped_whatever_the_adjacent_whitespace(call):
    assert ev.ran_segments([call]) == {"pytest -q", "tail"}


def test_fd_duplication_does_not_eat_digits_that_end_a_word():
    assert ev.ran_segments(["pytest2>&1 | tail"]) == {"pytest2", "tail"}
