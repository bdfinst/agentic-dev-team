"""Tests for plan_summary_record.py: `record` writes one row per candidate
under the plan's `## Plan Review Summary` -> `### Speculative dispatch`. Pure
cases call `record()` in-process; the exit-code contract runs the real
command line.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from _build_candidates_test_helpers import (
    SCRIPTS_DIR,
    make_candidate,
    run_script,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import plan_summary_record

SCRIPT_PY = SCRIPTS_DIR / "plan_summary_record.py"

SUMMARY_HEADING = "## Plan Review Summary\n"
SUBSECTION_HEADING = "### Speculative dispatch\n"
COLUMN_COUNT = 13
HEADER_LINE_COUNT = 2
COST_COLUMN_INDEX = 10
TABLE_HEADER = (
    "| Step | Attempt | Rank | Candidate | Branch | Suite | Scenarios met | Errors "
    "| Warnings | Diff lines | Cost (USD) | Outcome | Reason |\n"
)
TABLE_SEPARATOR = "| " + " | ".join(["---"] * COLUMN_COUNT) + " |\n"
TABLE_TOP = TABLE_HEADER + TABLE_SEPARATOR

PLAN_HEAD = "# Plan: Example\n\n## Goal\n\nDo the thing.\n\n"
BUILD_PROGRESS = "## Build Progress\n\n- [ ] Slice 1\n  - [ ] Step 1.1\n"

STEP = "2.1"
ATTEMPT = 1


def make_row(candidate_id: int, outcome: str = "kept", **overrides) -> dict:
    """A row of the result file: a `make_candidate` dict plus rank, outcome
    and reason; `overrides` replace any field."""
    row = make_candidate(candidate_id)
    row.update({"rank": candidate_id, "outcome": outcome, "reason": ""})
    row.update(overrides)
    return row


def not_dispatched_row(candidate_id: int, reason: str = "cost cap") -> dict:
    return {"id": candidate_id, "outcome": "not dispatched", "reason": reason}


def one_kept_row() -> list[dict]:
    return [make_row(1)]


def subsection(*row_lines: str) -> str:
    """The text `record` inserts for a new subsection holding `row_lines`."""
    return SUBSECTION_HEADING + "\n" + TABLE_TOP + "".join(row_lines)


def table_lines(text: str) -> list[str]:
    return [line for line in text.splitlines(keepends=True) if line.startswith("|")]


def data_row_lines(text: str) -> list[str]:
    return table_lines(text)[HEADER_LINE_COUNT:]


def kept_row_line(step: str, attempt: int, candidate_id: int) -> str:
    """The row line `record` writes for `make_row(candidate_id)`; the values
    (worktree-c<id>, green, 5/5, 0 findings, 10 diff lines, 0.5000 cost) are
    the `make_candidate` defaults."""
    return (
        f"| {step} | {attempt} | {candidate_id} | {candidate_id} "
        f"| worktree-c{candidate_id} | green | 5/5 | 0 | 0 | 10 | 0.5000 | kept |  |\n"
    )


KEPT_ROW_LINE = kept_row_line(STEP, ATTEMPT, 1)
FIRST_KEPT_ROW_LINE = kept_row_line("1.1", ATTEMPT, 1)


def test_the_metric_columns_are_the_six_cells_between_branch_and_outcome() -> None:
    assert plan_summary_record.METRIC_COLUMNS == (
        "Suite",
        "Scenarios met",
        "Errors",
        "Warnings",
        "Diff lines",
        "Cost (USD)",
    )


def test_the_metric_columns_sit_between_the_branch_and_outcome_columns() -> None:
    columns, metrics = plan_summary_record.COLUMNS, plan_summary_record.METRIC_COLUMNS
    assert columns[columns.index("Branch") + 1] == metrics[0]
    assert columns[columns.index("Outcome") - 1] == metrics[-1]
    assert len(metrics) == columns.index("Outcome") - columns.index("Branch") - 1


# --- insertion: no Plan Review Summary yet ------------------------------------

FOUR_ROWS = [
    make_row(
        1,
        "kept",
        branch="b1",
        warnings=1,
        diff_lines=40,
        cost_usd=1.25,
    ),
    make_row(
        2,
        "removed",
        branch="b2",
        scenarios_unmet=1,
        diff_lines=30,
        cost_usd=1.25,
    ),
    make_row(
        3,
        "disqualified",
        branch="b3",
        suite_green=False,
        diff_lines=20,
        cost_usd=1.25,
        reason="red suite",
    ),
    not_dispatched_row(4),
]
ROW_1_LINE = "| 2.1 | 1 | 1 | 1 | b1 | green | 5/5 | 0 | 1 | 40 | 1.2500 | kept |  |\n"
ROW_2_LINE = (
    "| 2.1 | 1 | 2 | 2 | b2 | green | 4/5 | 0 | 0 | 30 | 1.2500 | removed |  |\n"
)
ROW_3_LINE = (
    "| 2.1 | 1 | 3 | 3 | b3 | red | 5/5 | 0 | 0 | 20 | 1.2500 | disqualified "
    "| red suite |\n"
)
ROW_4_LINE = (
    "| 2.1 | 1 | — | 4 | — | — | — | — | — | — | — | not dispatched | cost cap |\n"
)

PLAN_WITHOUT_SUMMARY = PLAN_HEAD + BUILD_PROGRESS


@pytest.fixture(scope="module")
def created_summary() -> str:
    return plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, FOUR_ROWS)


def test_record_places_a_new_summary_immediately_before_build_progress(
    created_summary,
) -> None:
    assert created_summary.endswith(ROW_4_LINE + "\n" + BUILD_PROGRESS)
    assert created_summary.index(SUMMARY_HEADING) == len(PLAN_HEAD)


def test_record_leaves_the_text_around_a_new_summary_byte_identical(
    created_summary,
) -> None:
    inserted = created_summary[len(PLAN_HEAD) : -len(BUILD_PROGRESS)]
    assert created_summary == PLAN_HEAD + inserted + BUILD_PROGRESS


def test_record_creates_one_summary_section(created_summary) -> None:
    assert created_summary.count(SUMMARY_HEADING) == 1


def test_record_creates_one_subsection(created_summary) -> None:
    assert created_summary.count(SUBSECTION_HEADING) == 1


def test_record_nests_the_subsection_directly_under_the_summary_heading(
    created_summary,
) -> None:
    assert SUMMARY_HEADING + "\n" + SUBSECTION_HEADING in created_summary


def test_record_writes_the_exact_table_header_and_separator(created_summary) -> None:
    assert table_lines(created_summary)[:HEADER_LINE_COUNT] == [
        TABLE_HEADER,
        TABLE_SEPARATOR,
    ]


def test_record_writes_one_row_per_candidate(created_summary) -> None:
    assert len(data_row_lines(created_summary)) == len(FOUR_ROWS)


def test_record_renders_a_kept_row_with_an_empty_reason_cell(created_summary) -> None:
    assert data_row_lines(created_summary)[0] == ROW_1_LINE


def test_record_renders_scenarios_met_as_met_over_total(created_summary) -> None:
    assert data_row_lines(created_summary)[1] == ROW_2_LINE


def test_record_renders_a_red_suite_and_its_reason(created_summary) -> None:
    assert data_row_lines(created_summary)[2] == ROW_3_LINE


def test_record_renders_a_not_dispatched_row_with_dashes_for_every_metric(
    created_summary,
) -> None:
    assert data_row_lines(created_summary)[3] == ROW_4_LINE


def test_record_orders_rows_by_candidate_id_whatever_the_input_order() -> None:
    shuffled = [FOUR_ROWS[3], FOUR_ROWS[1], FOUR_ROWS[0], FOUR_ROWS[2]]
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, shuffled)
    assert data_row_lines(recorded) == [ROW_1_LINE, ROW_2_LINE, ROW_3_LINE, ROW_4_LINE]


def test_record_renders_cost_to_four_decimals() -> None:
    row = make_row(1, cost_usd=1.23456)
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, [row])
    assert data_row_lines(recorded)[0].split(" | ")[COST_COLUMN_INDEX] == "1.2346"


# --- an empty branch ----------------------------------------------------------

NO_COMMITS_ROW_LINE = (
    "| 2.1 | 1 | 1 | 1 | — | red | 5/5 | 0 | 0 | 10 | 0.5000 | disqualified "
    "| no commits |\n"
)


@pytest.fixture(scope="module")
def recorded_no_commits() -> str:
    row = make_row(1, "disqualified", branch="", suite_green=False, reason="no commits")
    return plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, [row])


def test_record_renders_an_empty_branch_as_an_em_dash(recorded_no_commits) -> None:
    assert data_row_lines(recorded_no_commits) == [NO_COMMITS_ROW_LINE]


def test_record_replaces_an_empty_branch_row_when_the_attempt_is_recorded_again(
    recorded_no_commits,
) -> None:
    recorded_again = plan_summary_record.record(
        recorded_no_commits, STEP, ATTEMPT, one_kept_row()
    )
    assert data_row_lines(recorded_again) == [KEPT_ROW_LINE]


# --- insertion: inside an existing summary ------------------------------------

SUMMARY_BODY = "Reviewed by three agents.\n"
PLAN_WITH_SUMMARY_THEN_RISKS = (
    PLAN_HEAD
    + SUMMARY_HEADING
    + "\n"
    + SUMMARY_BODY
    + "\n## Risks\n\nNone known.\n\n"
    + BUILD_PROGRESS
)


@pytest.fixture(scope="module")
def appended_inside_summary() -> str:
    return plan_summary_record.record(
        PLAN_WITH_SUMMARY_THEN_RISKS, "1.1", ATTEMPT, one_kept_row()
    )


def test_record_appends_the_subsection_at_the_end_of_the_summary(
    appended_inside_summary,
) -> None:
    summary_end = SUMMARY_BODY + "\n" + subsection(FIRST_KEPT_ROW_LINE)
    assert summary_end + "\n## Risks\n" in appended_inside_summary


def test_record_changes_no_byte_outside_the_inserted_subsection(
    appended_inside_summary,
) -> None:
    inserted = "\n" + subsection(FIRST_KEPT_ROW_LINE)
    assert appended_inside_summary.replace(inserted, "", 1) == (
        PLAN_WITH_SUMMARY_THEN_RISKS
    )


# --- insertion: the summary is the last section -------------------------------

SUMMARY_LAST_BODY = PLAN_HEAD + BUILD_PROGRESS + "\n" + SUMMARY_HEADING + "\nDone.\n"


@pytest.mark.parametrize(
    "tail",
    ["", "\n", "\n\n\n"],
    ids=["no-final-newline", "one-blank-line", "many-blank-lines"],
)
def test_record_ends_the_file_with_exactly_one_newline_when_the_summary_is_last(
    tail,
) -> None:
    recorded = plan_summary_record.record(
        SUMMARY_LAST_BODY.rstrip("\n") + tail, "1.1", ATTEMPT, one_kept_row()
    )
    assert recorded.endswith(FIRST_KEPT_ROW_LINE)


def test_record_puts_the_subsection_at_the_end_of_a_last_summary() -> None:
    recorded = plan_summary_record.record(
        SUMMARY_LAST_BODY, "1.1", ATTEMPT, one_kept_row()
    )
    assert recorded == SUMMARY_LAST_BODY + "\n" + subsection(FIRST_KEPT_ROW_LINE)


# --- insertion: headings inside fenced blocks are not headings ----------------


def _plan_with_fenced_build_progress(fence: str) -> str:
    return (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\nA sample plan:\n\n"
        + f"{fence}\n## Build Progress\n{fence}\n\n"
        + BUILD_PROGRESS
    )


@pytest.mark.parametrize(
    "fence", ["```", "~~~", "````"], ids=["backticks", "tildes", "four-backticks"]
)
def test_record_inserts_before_the_real_build_progress_not_a_fenced_one(fence) -> None:
    plan = _plan_with_fenced_build_progress(fence)
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    fenced_block_end = recorded.index(f"{fence}\n\n") + len(fence)
    assert recorded.index(SUBSECTION_HEADING) > fenced_block_end


@pytest.mark.parametrize("fence", ["```", "~~~"], ids=["backticks", "tildes"])
def test_record_ends_the_summary_at_the_real_build_progress_heading(fence) -> None:
    plan = _plan_with_fenced_build_progress(fence)
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    assert recorded.endswith(subsection(FIRST_KEPT_ROW_LINE) + "\n" + BUILD_PROGRESS)


def test_record_keeps_a_fence_open_when_a_different_fence_character_appears() -> None:
    plan = (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n~~~\n```\n## Build Progress\n```\n~~~\n\n"
        + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    assert recorded.index(SUBSECTION_HEADING) > recorded.index("~~~\n\n")


def test_record_keeps_a_fence_open_when_a_shorter_fence_appears() -> None:
    plan = (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n````\n```\n## Build Progress\n````\n\n"
        + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    assert recorded.index(SUBSECTION_HEADING) > recorded.index("````\n\n")


def test_record_keeps_a_fence_open_when_the_closing_line_has_an_info_string() -> None:
    plan = (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n```\n```python\n## Build Progress\n```\n\n"
        + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    assert recorded.index(SUBSECTION_HEADING) > recorded.index("```\n\n")


def test_record_does_not_take_inline_triple_backticks_for_a_fence_opener() -> None:
    plan = (
        PLAN_HEAD + "```x```\n\n" + SUMMARY_HEADING + "\nReviewed.\n\n" + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "1.1", ATTEMPT, one_kept_row())
    assert recorded == (
        PLAN_HEAD
        + "```x```\n\n"
        + SUMMARY_HEADING
        + "\nReviewed.\n\n"
        + subsection(FIRST_KEPT_ROW_LINE)
        + "\n"
        + BUILD_PROGRESS
    )


def test_record_rejects_a_plan_whose_fence_is_never_closed() -> None:
    plan = PLAN_HEAD + "```\n## Build Progress\n"
    with pytest.raises(ValueError, match="never closed"):
        plan_summary_record.record(plan, STEP, ATTEMPT, one_kept_row())


def test_record_ends_the_summary_at_a_level_one_heading() -> None:
    appendix = "# Appendix\n\nMore.\n\n"
    plan = PLAN_HEAD + SUMMARY_HEADING + "\nReviewed.\n\n" + appendix + BUILD_PROGRESS
    recorded = plan_summary_record.record(plan, STEP, ATTEMPT, one_kept_row())
    assert recorded == (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\nReviewed.\n\n"
        + subsection(KEPT_ROW_LINE)
        + "\n"
        + appendix
        + BUILD_PROGRESS
    )


# --- insertion: neither section -----------------------------------------------

SECTION_AT_END = SUMMARY_HEADING + "\n" + subsection(KEPT_ROW_LINE)


def test_record_appends_the_summary_at_the_end_of_a_plan_with_neither_section() -> None:
    recorded = plan_summary_record.record(PLAN_HEAD, STEP, ATTEMPT, one_kept_row())
    assert recorded == PLAN_HEAD + SECTION_AT_END


def test_record_completes_a_last_line_that_lacks_its_newline() -> None:
    plan = PLAN_HEAD.rstrip("\n")
    recorded = plan_summary_record.record(plan, STEP, ATTEMPT, one_kept_row())
    assert recorded == plan + "\n\n" + SECTION_AT_END


def test_record_inserts_the_summary_into_an_empty_plan() -> None:
    recorded = plan_summary_record.record("", STEP, ATTEMPT, one_kept_row())
    assert recorded == SECTION_AT_END


# --- line endings -------------------------------------------------------------


def test_record_gives_every_inserted_line_the_plans_crlf_ending() -> None:
    plan = PLAN_WITHOUT_SUMMARY.replace("\n", "\r\n")
    recorded = plan_summary_record.record(plan, STEP, ATTEMPT, one_kept_row())
    expected = (PLAN_HEAD + SECTION_AT_END + "\n" + BUILD_PROGRESS).replace(
        "\n", "\r\n"
    )
    assert recorded == expected


def test_record_completes_a_last_crlf_line_with_crlf() -> None:
    plan = "# Plan\r\n\r\n## Goal"
    recorded = plan_summary_record.record(plan, STEP, ATTEMPT, one_kept_row())
    expected = ("# Plan\n\n## Goal\n\n" + SECTION_AT_END).replace("\n", "\r\n")
    assert recorded == expected


def test_record_keeps_lf_endings_when_the_first_line_ends_in_lf() -> None:
    later_crlf = BUILD_PROGRESS.replace("\n", "\r\n")
    recorded = plan_summary_record.record(
        PLAN_HEAD + later_crlf, STEP, ATTEMPT, one_kept_row()
    )
    assert recorded == PLAN_HEAD + SECTION_AT_END + "\n" + later_crlf


def test_record_gives_replacement_rows_the_crlf_ending() -> None:
    plan = plan_with_table(EXISTING_ROW_LINE_1).replace("\n", "\r\n")
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert data_row_lines(recorded) == [REPLACEMENT_ROW_LINE.replace("\n", "\r\n")]


# --- the command line writes the file -----------------------------------------


def _run(*args: str, python_flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    return run_script(SCRIPT_PY, *args, python_flags=python_flags)


def _run_record(
    plan,
    result,
    step: str = STEP,
    attempt: str = "1",
    python_flags: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    return _run(
        "record",
        "--plan",
        str(plan),
        "--step",
        step,
        "--attempt",
        attempt,
        "--result",
        str(result),
        python_flags=python_flags,
    )


def _write_result(directory, rows: list[dict]):
    path = directory / "result.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return path


EXPECTED_AFTER_RECORD = (PLAN_HEAD + SECTION_AT_END + "\n" + BUILD_PROGRESS).encode(
    "utf-8"
)


@pytest.fixture(scope="module")
def cli_write(tmp_path_factory):
    """The CLI run that records one kept row, and the plan bytes afterwards."""
    directory = tmp_path_factory.mktemp("cli-write")
    plan = directory / "plan.md"
    plan.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    process = _run_record(plan, _write_result(directory, one_kept_row()))
    return process, plan.read_bytes()


def test_record_cli_exits_zero_when_it_writes_the_plan(cli_write) -> None:
    process, _ = cli_write
    assert process.returncode == 0


def test_record_cli_prints_nothing_when_it_writes_the_plan(cli_write) -> None:
    process, _ = cli_write
    assert process.stdout == ""


def test_record_cli_writes_the_updated_plan(cli_write) -> None:
    _, written = cli_write
    assert written == EXPECTED_AFTER_RECORD


def test_record_cli_runs_in_isolated_mode(tmp_path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    result = _write_result(tmp_path, one_kept_row())
    process = _run_record(plan, result, python_flags=("-I",))
    assert process.returncode == 0, process.stderr
    assert plan.read_bytes() == EXPECTED_AFTER_RECORD


CRLF_ROW_LINE = (
    "| 2.1 | 1 | 1 | 1 | worktree-c1 | green | 5/5 | 0 | 0 | 10 | 0.5000 | kept "
    "| naïve — ok |\n"
)
CRLF_PLAN_LF_FORM = "# Plan: café — naïve\n\n" + BUILD_PROGRESS


@pytest.fixture(scope="module")
def cli_crlf_write(tmp_path_factory):
    directory = tmp_path_factory.mktemp("cli-crlf")
    plan = directory / "plan.md"
    plan.write_bytes(CRLF_PLAN_LF_FORM.replace("\n", "\r\n").encode("utf-8"))
    result = _write_result(directory, [make_row(1, reason="naïve — ok")])
    return _run_record(plan, result), plan.read_bytes().decode("utf-8")


def test_record_cli_exits_zero_for_a_crlf_plan(cli_crlf_write) -> None:
    process, _ = cli_crlf_write
    assert process.returncode == 0, process.stderr


def test_record_cli_writes_a_crlf_plan_as_utf8_with_crlf_throughout(
    cli_crlf_write,
) -> None:
    _, written = cli_crlf_write
    expected_lf = (
        "# Plan: café — naïve\n\n"
        + SUMMARY_HEADING
        + "\n"
        + subsection(CRLF_ROW_LINE)
        + "\n"
        + BUILD_PROGRESS
    )
    assert written == expected_lf.replace("\n", "\r\n")


def test_record_cli_leaves_no_bare_line_feed_in_a_crlf_plan(cli_crlf_write) -> None:
    _, written = cli_crlf_write
    assert re.findall(r"(?<!\r)\n", written) == []


# --- the write is atomic ------------------------------------------------------


@dataclass(frozen=True)
class FailedReplace:
    exit_code: int
    stdout: str
    stderr: str
    plan_before: bytes
    plan_after: bytes
    directory_listing: list[str]


@pytest.fixture(scope="module")
def failed_replace(tmp_path_factory) -> FailedReplace:
    """`main` run in-process while os.replace raises OSError."""
    directory = tmp_path_factory.mktemp("failed-replace")
    plan = directory / "plan.md"
    plan.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    before = plan.read_bytes()
    result = _write_result(directory, one_kept_row())

    def refuse(*_args, **_kwargs):
        raise OSError("replace refused")

    stdout, stderr = io.StringIO(), io.StringIO()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(plan_summary_record.os, "replace", refuse)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = plan_summary_record.main(
                ["record", "--plan", str(plan)]
                + ["--step", STEP, "--attempt", "1", "--result", str(result)]
            )
    return FailedReplace(
        exit_code,
        stdout.getvalue(),
        stderr.getvalue(),
        before,
        plan.read_bytes(),
        sorted(entry.name for entry in directory.iterdir()),
    )


def test_record_exits_one_when_the_replace_fails(failed_replace) -> None:
    assert failed_replace.exit_code == 1


def test_record_prints_nothing_to_stdout_when_the_replace_fails(failed_replace) -> None:
    assert failed_replace.stdout == ""


def test_record_reports_a_failed_replace_on_stderr(failed_replace) -> None:
    assert failed_replace.stderr == "record: replace refused\n"


def test_record_leaves_the_plan_byte_identical_when_the_replace_fails(
    failed_replace,
) -> None:
    assert failed_replace.plan_after == failed_replace.plan_before


def test_record_leaves_no_temp_file_behind_when_the_replace_fails(
    failed_replace,
) -> None:
    assert failed_replace.directory_listing == ["plan.md", "result.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_record_keeps_the_plans_file_mode(tmp_path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    plan.chmod(0o640)
    process = _run_record(plan, _write_result(tmp_path, one_kept_row()))
    assert process.returncode == 0, process.stderr
    assert stat.S_IMODE(plan.stat().st_mode) == 0o640


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_record_updates_the_target_of_a_symlinked_plan(tmp_path) -> None:
    target = tmp_path / "real-plan.md"
    target.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    link = tmp_path / "plan.md"
    os.symlink(target, link)
    process = _run_record(link, _write_result(tmp_path, one_kept_row()))
    assert process.returncode == 0, process.stderr
    assert target.read_bytes() == EXPECTED_AFTER_RECORD


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_record_keeps_a_symlinked_plan_a_symlink(tmp_path) -> None:
    target = tmp_path / "real-plan.md"
    target.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    link = tmp_path / "plan.md"
    os.symlink(target, link)
    process = _run_record(link, _write_result(tmp_path, one_kept_row()))
    assert process.returncode == 0, process.stderr
    assert link.is_symlink()


# --- replacement and appending in an existing table ---------------------------


def plan_with_table(*row_lines: str) -> str:
    return (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n"
        + subsection(*row_lines)
        + "\n"
        + BUILD_PROGRESS
    )


EXISTING_ROW_LINE_1 = kept_row_line("2.1", 1, 1)
EXISTING_ROW_LINE_2 = kept_row_line("2.1", 1, 2)
OTHER_STEP_ROW_LINE = kept_row_line("2.10", 1, 1)
SECOND_ATTEMPT_ROW_LINE = kept_row_line("2.1", 2, 1)
PLAN_WITH_FOUR_ROWS = plan_with_table(
    EXISTING_ROW_LINE_1,
    EXISTING_ROW_LINE_2,
    OTHER_STEP_ROW_LINE,
    SECOND_ATTEMPT_ROW_LINE,
)
REPLACEMENT_ROW_LINE = kept_row_line("2.1", 1, 7)


@pytest.fixture(scope="module")
def replaced_attempt() -> str:
    return plan_summary_record.record(PLAN_WITH_FOUR_ROWS, "2.1", 1, [make_row(7)])


def test_record_puts_the_new_row_where_the_replaced_rows_were(replaced_attempt) -> None:
    assert data_row_lines(replaced_attempt)[0] == REPLACEMENT_ROW_LINE


def test_record_leaves_other_steps_and_attempts_unchanged_and_in_order(
    replaced_attempt,
) -> None:
    assert data_row_lines(replaced_attempt)[1:] == [
        OTHER_STEP_ROW_LINE,
        SECOND_ATTEMPT_ROW_LINE,
    ]


def test_record_keeps_the_subsection_heading_once_when_replacing(
    replaced_attempt,
) -> None:
    assert replaced_attempt.count(SUBSECTION_HEADING) == 1


def test_record_keeps_the_table_header_once_when_replacing(replaced_attempt) -> None:
    assert replaced_attempt.count(TABLE_HEADER) == 1


def test_record_changes_no_byte_outside_the_replaced_rows(replaced_attempt) -> None:
    restored = replaced_attempt.replace(
        REPLACEMENT_ROW_LINE, EXISTING_ROW_LINE_1 + EXISTING_ROW_LINE_2, 1
    )
    assert restored == PLAN_WITH_FOUR_ROWS


def test_record_replaces_rows_of_one_attempt_that_are_not_adjacent() -> None:
    other_step = kept_row_line("2.2", 1, 1)
    plan = plan_with_table(EXISTING_ROW_LINE_1, other_step, EXISTING_ROW_LINE_2)
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert data_row_lines(recorded) == [REPLACEMENT_ROW_LINE, other_step]


def test_record_matches_the_attempt_cell_exactly() -> None:
    attempt_10 = kept_row_line("2.1", 10, 1)
    plan = plan_with_table(attempt_10)
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert data_row_lines(recorded) == [attempt_10, REPLACEMENT_ROW_LINE]


NEW_STEP_PLAN = plan_with_table(kept_row_line("1.1", 1, 1), kept_row_line("1.1", 1, 2))


def test_record_appends_a_new_steps_rows_after_the_existing_rows() -> None:
    recorded = plan_summary_record.record(NEW_STEP_PLAN, "2.1", 1, [make_row(1)])
    assert data_row_lines(recorded) == [
        kept_row_line("1.1", 1, 1),
        kept_row_line("1.1", 1, 2),
        kept_row_line("2.1", 1, 1),
    ]


def test_record_keeps_the_subsection_heading_once_when_appending_a_new_step() -> None:
    recorded = plan_summary_record.record(NEW_STEP_PLAN, "2.1", 1, [make_row(1)])
    assert recorded.count(SUBSECTION_HEADING) == 1


def test_record_keeps_the_table_header_once_when_appending_a_new_step() -> None:
    recorded = plan_summary_record.record(NEW_STEP_PLAN, "2.1", 1, [make_row(1)])
    assert recorded.count(TABLE_HEADER) == 1


def test_record_changes_no_byte_outside_the_appended_row() -> None:
    recorded = plan_summary_record.record(NEW_STEP_PLAN, "2.1", 1, [make_row(1)])
    assert recorded.replace(kept_row_line("2.1", 1, 1), "", 1) == NEW_STEP_PLAN


def test_record_appends_a_second_attempt_after_the_first() -> None:
    plan = plan_with_table(EXISTING_ROW_LINE_1)
    recorded = plan_summary_record.record(plan, "2.1", 2, [make_row(1)])
    assert data_row_lines(recorded) == [EXISTING_ROW_LINE_1, kept_row_line("2.1", 2, 1)]


def test_record_appends_in_call_order_not_attempt_order() -> None:
    plan = plan_with_table(SECOND_ATTEMPT_ROW_LINE)
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(1)])
    assert data_row_lines(recorded) == [
        SECOND_ATTEMPT_ROW_LINE,
        kept_row_line("2.1", 1, 1),
    ]


@pytest.mark.parametrize(
    "plan",
    [PLAN_WITHOUT_SUMMARY, NEW_STEP_PLAN, PLAN_WITH_FOUR_ROWS],
    ids=["no-summary", "new-step", "replacement"],
)
def test_record_is_idempotent(plan) -> None:
    once = plan_summary_record.record(plan, "2.1", 1, one_kept_row())
    twice = plan_summary_record.record(once, "2.1", 1, one_kept_row())
    assert twice == once


def test_record_ends_a_file_whose_table_is_last_with_exactly_one_newline() -> None:
    plan = (
        PLAN_HEAD + SUMMARY_HEADING + "\n" + subsection(EXISTING_ROW_LINE_1) + "\n\n\n"
    )
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert recorded == (
        PLAN_HEAD + SUMMARY_HEADING + "\n" + subsection(REPLACEMENT_ROW_LINE)
    )


def test_record_completes_a_last_table_row_that_lacks_its_newline() -> None:
    plan = (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n"
        + subsection(EXISTING_ROW_LINE_1.rstrip("\n"))
    )
    recorded = plan_summary_record.record(plan, "2.2", 1, [make_row(1)])
    assert data_row_lines(recorded) == [EXISTING_ROW_LINE_1, kept_row_line("2.2", 1, 1)]


def test_record_adds_the_table_to_a_subsection_that_has_none() -> None:
    plan = (
        PLAN_HEAD + SUMMARY_HEADING + "\n" + SUBSECTION_HEADING + "\n" + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "2.1", 1, one_kept_row())
    assert recorded == (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n"
        + subsection(KEPT_ROW_LINE)
        + "\n"
        + BUILD_PROGRESS
    )


def test_record_adds_rows_to_a_table_that_has_only_a_header() -> None:
    plan = (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n"
        + SUBSECTION_HEADING
        + "\n"
        + TABLE_HEADER
        + "\n"
        + BUILD_PROGRESS
    )
    recorded = plan_summary_record.record(plan, "2.1", 1, one_kept_row())
    assert recorded.endswith(TABLE_HEADER + KEPT_ROW_LINE + "\n" + BUILD_PROGRESS)


def test_record_ignores_a_subsection_heading_outside_the_summary() -> None:
    summary = SUMMARY_HEADING + "\nReviewed.\n\n"
    elsewhere = (
        "## Notes\n\n"
        + SUBSECTION_HEADING
        + "\n"
        + TABLE_TOP
        + EXISTING_ROW_LINE_1
        + "\n"
    )
    plan = PLAN_HEAD + summary + elsewhere + BUILD_PROGRESS
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert recorded.endswith(elsewhere + BUILD_PROGRESS)


def test_record_matches_rows_of_a_table_indented_by_spaces() -> None:
    plan = plan_with_table("  " + EXISTING_ROW_LINE_1)
    recorded = plan_summary_record.record(plan, "2.1", 1, [make_row(7)])
    assert recorded == plan_with_table(REPLACEMENT_ROW_LINE)


def test_record_does_not_take_a_deeper_heading_for_the_summary() -> None:
    deeper = "### Plan Review Summary\n\nNotes.\n\n"
    recorded = plan_summary_record.record(
        PLAN_HEAD + deeper + BUILD_PROGRESS, "2.1", 1, one_kept_row()
    )
    assert recorded.startswith(PLAN_HEAD + deeper + SUMMARY_HEADING)


def test_record_does_not_take_a_higher_heading_for_the_subsection() -> None:
    higher = "## Speculative dispatch\n\nNotes.\n\n"
    plan = PLAN_HEAD + SUMMARY_HEADING + "\n" + higher + BUILD_PROGRESS
    recorded = plan_summary_record.record(plan, "2.1", 1, one_kept_row())
    assert recorded == (
        PLAN_HEAD
        + SUMMARY_HEADING
        + "\n"
        + subsection(KEPT_ROW_LINE)
        + "\n"
        + higher
        + BUILD_PROGRESS
    )


def test_record_escapes_a_pipe_in_the_reason() -> None:
    row = make_row(1, reason="a | b")
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, 1, [row])
    assert data_row_lines(recorded)[0].endswith("| kept | a \\| b |\n")


def test_record_escapes_a_backslash_before_a_pipe_in_the_reason() -> None:
    row = make_row(1, reason="a\\|b")
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, 1, [row])
    assert data_row_lines(recorded)[0].endswith(r"| kept | a\\\|b |" + "\n")


@pytest.mark.parametrize(
    "overrides",
    [{"reason": "a\n## Build Progress"}, {"branch": "b\r1"}],
    ids=["newline-in-reason", "carriage-return-in-branch"],
)
def test_record_rejects_cell_text_that_would_split_the_row(overrides) -> None:
    with pytest.raises(ValueError, match="single line"):
        plan_summary_record.record(
            PLAN_WITHOUT_SUMMARY, STEP, 1, [make_row(1, **overrides)]
        )


# --- bad input, in-process ----------------------------------------------------

_BAD_ROWS = [
    ("rows-not-a-list", 1, "rows must be a list"),
    ("rows-empty", [], "rows must not be empty"),
    ("row-not-an-object", ["x"], "row 1: not an object"),
    (
        "reason-missing",
        [{"id": 1, "outcome": "not dispatched"}],
        "row 1: reason must be a string",
    ),
    (
        "reason-not-a-string",
        [make_row(1, reason=None)],
        "row 1: reason must be a string",
    ),
    (
        "not-dispatched-id-zero",
        [not_dispatched_row(0)],
        "row 1: id must be a positive int",
    ),
    (
        "not-dispatched-id-bool",
        [not_dispatched_row(True)],
        "row 1: id must be a positive int",
    ),
    (
        "not-dispatched-id-missing",
        [{"outcome": "not dispatched", "reason": ""}],
        "row 1: id must be a positive int",
    ),
    (
        "outcome-unhashable",
        [make_row(1, outcome=["kept"])],
        "outcome must be one of",
    ),
    ("rank-missing", [{**make_row(1), "rank": None}], "candidate 1: rank must be"),
    ("rank-zero", [make_row(1, rank=0)], "candidate 1: rank must be"),
    ("rank-negative", [make_row(1, rank=-1)], "candidate 1: rank must be"),
    ("rank-float", [make_row(1, rank=1.5)], "candidate 1: rank must be"),
    ("rank-bool", [make_row(1, rank=True)], "candidate 1: rank must be"),
    ("rank-string", [make_row(1, rank="1")], "candidate 1: rank must be"),
    (
        "candidate-field-invalid",
        [make_row(1, suite_green=1)],
        "candidate 1: suite_green must be a boolean",
    ),
    (
        "kept-with-a-red-suite",
        [make_row(1, suite_green=False)],
        "candidate 1: kept but disqualified (red suite)",
    ),
    (
        "kept-with-an-unparseable-lens",
        [make_row(1, screening="unparseable: correctness-review")],
        (
            "candidate 1: kept but disqualified "
            "(screening: correctness-review unparseable)"
        ),
    ),
    (
        "duplicate-id",
        [make_row(1, "removed"), make_row(1, "removed")],
        "duplicate candidate id 1",
    ),
    (
        "two-kept",
        [make_row(1), make_row(2)],
        "more than one kept row: candidates 1, 2",
    ),
]


@pytest.mark.parametrize(
    "rows,message",
    [(rows, message) for _, rows, message in _BAD_ROWS],
    ids=[case_id for case_id, _, _ in _BAD_ROWS],
)
def test_record_rejects_invalid_rows_naming_the_problem(rows, message) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, 1, rows)


_BAD_STEPS = ["2", "2.", ".1", "a.b", "2.1.1", " 2.1", "2.1\n", "2,1", "٢.١"]


@pytest.mark.parametrize("step", _BAD_STEPS, ids=[repr(s) for s in _BAD_STEPS])
def test_record_rejects_a_step_that_is_not_n_dot_m(step) -> None:
    with pytest.raises(ValueError, match="step must be N.M"):
        plan_summary_record.record(PLAN_WITHOUT_SUMMARY, step, 1, one_kept_row())


_BAD_ATTEMPTS = [0, -1, True, 1.0, "1", None]


@pytest.mark.parametrize("attempt", _BAD_ATTEMPTS, ids=[repr(a) for a in _BAD_ATTEMPTS])
def test_record_rejects_an_attempt_that_is_not_a_positive_int(attempt) -> None:
    with pytest.raises(ValueError, match="attempt must be a positive integer"):
        plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, attempt, one_kept_row())


def test_record_accepts_a_multi_digit_step_and_attempt() -> None:
    recorded = plan_summary_record.record(
        PLAN_WITHOUT_SUMMARY, "12.34", 10, one_kept_row()
    )
    assert data_row_lines(recorded)[0].startswith("| 12.34 | 10 | ")


# --- bad input on the command line --------------------------------------------

VALID_PLAN_BYTES = PLAN_WITHOUT_SUMMARY.encode("utf-8")
PLAN_NAME = "plan.md"
RESULT_NAME = "result.json"
_ROW_WITHOUT_OUTCOME = {k: v for k, v in make_row(1).items() if k != "outcome"}
_KEPT_WITHOUT_RANK = {k: v for k, v in make_row(1).items() if k != "rank"}


@dataclass(frozen=True)
class BadInputCase:
    """One bad CLI request: the files to create under a fresh directory
    (name -> bytes; a name inside a subdirectory makes that directory), which
    of them the command is pointed at, and the text its stderr must contain."""

    case_id: str
    names: str
    files: dict[str, bytes]
    step: str = STEP
    attempt: str = "1"
    plan_name: str = PLAN_NAME
    result_name: str = RESULT_NAME


def bad_result(
    case_id: str, result_text: str, names: str, step: str = STEP, attempt: str = "1"
) -> BadInputCase:
    """A request against a valid plan with `result_text` as the result file."""
    files = {PLAN_NAME: VALID_PLAN_BYTES, RESULT_NAME: result_text.encode("utf-8")}
    return BadInputCase(case_id, names, files, step=step, attempt=attempt)


_VALID_RESULT_TEXT = json.dumps({"rows": [make_row(1)]})

_BAD_INPUT_CASES = [
    bad_result("not-json", "{not json", "not JSON"),
    bad_result(
        "json-list-names-rows", json.dumps([]), plan_summary_record.RESULT_SHAPE_HINT
    ),
    bad_result("json-list", json.dumps([]), "JSON root is not an object"),
    bad_result(
        "row-without-outcome",
        json.dumps({"rows": [_ROW_WITHOUT_OUTCOME]}),
        "outcome",
    ),
    bad_result("outcome-won", json.dumps({"rows": [make_row(1, "won")]}), "won"),
    bad_result("kept-missing-rank", json.dumps({"rows": [_KEPT_WITHOUT_RANK]}), "rank"),
    bad_result("kept-rank-0", json.dumps({"rows": [make_row(1, rank=0)]}), "rank"),
    bad_result("kept-rank-1.5", json.dumps({"rows": [make_row(1, rank=1.5)]}), "rank"),
    bad_result(
        "kept-errors-minus-1",
        json.dumps({"rows": [make_row(1, errors=-1)]}),
        "errors",
    ),
    bad_result("two-kept", json.dumps({"rows": [make_row(1), make_row(2)]}), "kept"),
    bad_result("step-2", _VALID_RESULT_TEXT, "step", step="2"),
    bad_result("attempt-0", _VALID_RESULT_TEXT, "attempt", attempt="0"),
    bad_result("attempt-not-a-number", _VALID_RESULT_TEXT, "attempt", attempt="x"),
    bad_result("attempt-trailing-text", _VALID_RESULT_TEXT, "attempt", attempt="1x"),
    bad_result(
        "attempt-5000-digits", _VALID_RESULT_TEXT, "attempt", attempt="9" * 5000
    ),
    bad_result("json-nested-too-deep", "[" * 100_000, "not JSON"),
    bad_result("json-string", json.dumps("rows"), "JSON root is not an object"),
    bad_result("result-without-rows", json.dumps({"other": []}), "no 'rows' key"),
    BadInputCase(
        "plan-missing",
        "plan file: no such file",
        {RESULT_NAME: _VALID_RESULT_TEXT.encode("utf-8")},
    ),
    BadInputCase(
        "plan-not-utf-8",
        "UTF-8",
        {PLAN_NAME: b"\xff\xfe", RESULT_NAME: _VALID_RESULT_TEXT.encode("utf-8")},
    ),
    BadInputCase(
        "plan-is-a-directory",
        "cannot read",
        {"plan-dir/inner.md": b"", RESULT_NAME: _VALID_RESULT_TEXT.encode("utf-8")},
        plan_name="plan-dir",
    ),
    BadInputCase(
        "result-missing", "result: no such file", {PLAN_NAME: VALID_PLAN_BYTES}
    ),
]


class BadInputRun:
    """One CLI run against a bad request: the plan file's bytes before and
    after (None when the plan path has no file) and the command's result."""

    def __init__(self, directory: Path, case: BadInputCase) -> None:
        for name, content in case.files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.target = directory / case.plan_name
        self.before = case.files.get(case.plan_name)
        self.process = _run_record(
            self.target,
            directory / case.result_name,
            step=case.step,
            attempt=case.attempt,
        )

    @property
    def after(self) -> bytes | None:
        return self.target.read_bytes() if self.target.is_file() else None


@pytest.fixture(
    scope="module",
    params=_BAD_INPUT_CASES,
    ids=[case.case_id for case in _BAD_INPUT_CASES],
)
def bad_input(request, tmp_path_factory):
    attempt = BadInputRun(tmp_path_factory.mktemp("bad-input"), request.param)
    return attempt, request.param.names


def test_record_exits_one_with_empty_stdout_on_bad_input(bad_input) -> None:
    attempt, _ = bad_input
    assert (attempt.process.returncode, attempt.process.stdout) == (1, "")


def test_record_reports_bad_input_as_one_record_prefixed_line(bad_input) -> None:
    attempt, _ = bad_input
    assert re.fullmatch(r"record: [^\n]+\n", attempt.process.stderr) is not None


def test_record_names_the_offending_thing_on_stderr(bad_input) -> None:
    attempt, names = bad_input
    assert names in attempt.process.stderr


def test_record_leaves_the_plan_byte_identical_on_bad_input(bad_input) -> None:
    attempt, _ = bad_input
    assert attempt.after == attempt.before


_RECORD_ARGUMENTS = {
    "--plan": "plan.md",
    "--step": STEP,
    "--attempt": "1",
    "--result": "result.json",
}


@pytest.mark.parametrize(
    "missing", list(_RECORD_ARGUMENTS), ids=list(_RECORD_ARGUMENTS)
)
def test_record_cli_exits_two_on_a_missing_required_argument(missing) -> None:
    argv = [
        part
        for flag, value in _RECORD_ARGUMENTS.items()
        if flag != missing
        for part in (flag, value)
    ]
    process = _run("record", *argv)
    assert (process.returncode, process.stdout) == (2, "")
