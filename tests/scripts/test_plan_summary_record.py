"""Tests for plan_summary_record.py (#2273): `record` writes one row per
candidate under the plan's `## Plan Review Summary` -> `### Speculative
dispatch`. Pure cases call `record()` in-process; the exit-code contract runs
the real command line.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

import pytest
from _build_candidates_test_helpers import SCRIPTS_DIR, make_candidate

from _repo_root import REPO_ROOT

sys.path.insert(0, str(SCRIPTS_DIR))

import plan_summary_record

SCRIPT_PY = SCRIPTS_DIR / "plan_summary_record.py"
FLOOR_TEST = REPO_ROOT / "tests" / "repo" / "test_python_floor.py"
CLI_TIMEOUT_SECONDS = 60

SUMMARY_HEADING = "## Plan Review Summary\n"
SUBSECTION_HEADING = "### Speculative dispatch\n"
TABLE_HEADER = (
    "| Step | Attempt | Rank | Candidate | Branch | Suite | Scenarios met | Errors "
    "| Warnings | Diff lines | Cost (USD) | Outcome | Reason |\n"
)
TABLE_SEPARATOR = "| " + " | ".join(["---"] * 13) + " |\n"
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


def data_rows(text: str) -> list[str]:
    return table_lines(text)[2:]


KEPT_ROW_LINE = (
    "| 2.1 | 1 | 1 | 1 | worktree-c1 | green | 5/5 | 0 | 0 | 10 | 0.5000 | kept |  |\n"
)


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
    assert created_summary.endswith("\n" + BUILD_PROGRESS)
    assert created_summary.index(SUMMARY_HEADING) == len(PLAN_HEAD)


def test_record_leaves_the_text_around_a_new_summary_byte_identical(
    created_summary,
) -> None:
    inserted = created_summary[len(PLAN_HEAD) : -len(BUILD_PROGRESS)]
    assert created_summary == PLAN_HEAD + inserted + BUILD_PROGRESS


def test_record_creates_one_summary_section_and_one_subsection(
    created_summary,
) -> None:
    assert (
        created_summary.count(SUMMARY_HEADING),
        created_summary.count(SUBSECTION_HEADING),
    ) == (1, 1)


def test_record_nests_the_subsection_directly_under_the_summary_heading(
    created_summary,
) -> None:
    assert SUMMARY_HEADING + "\n" + SUBSECTION_HEADING in created_summary


def test_record_writes_the_exact_table_header_and_separator(created_summary) -> None:
    assert table_lines(created_summary)[:2] == [TABLE_HEADER, TABLE_SEPARATOR]


def test_record_writes_one_row_per_candidate(created_summary) -> None:
    assert len(data_rows(created_summary)) == len(FOUR_ROWS)


def test_record_renders_a_kept_row_with_an_empty_reason_cell(created_summary) -> None:
    assert data_rows(created_summary)[0] == ROW_1_LINE


def test_record_renders_scenarios_met_as_met_over_total(created_summary) -> None:
    assert data_rows(created_summary)[1] == ROW_2_LINE


def test_record_renders_a_red_suite_and_its_reason(created_summary) -> None:
    assert data_rows(created_summary)[2] == ROW_3_LINE


def test_record_renders_a_not_dispatched_row_with_dashes_for_every_metric(
    created_summary,
) -> None:
    assert data_rows(created_summary)[3] == ROW_4_LINE


def test_record_orders_rows_by_candidate_id_whatever_the_input_order() -> None:
    shuffled = [FOUR_ROWS[3], FOUR_ROWS[1], FOUR_ROWS[0], FOUR_ROWS[2]]
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, shuffled)
    assert data_rows(recorded) == [ROW_1_LINE, ROW_2_LINE, ROW_3_LINE, ROW_4_LINE]


def test_record_renders_cost_to_four_decimals() -> None:
    row = make_row(1, cost_usd=1.23456)
    recorded = plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, [row])
    assert data_rows(recorded)[0].split(" | ")[10] == "1.2346"


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
    summary_end = (
        SUMMARY_BODY + "\n" + subsection(KEPT_ROW_LINE.replace("2.1", "1.1", 1))
    )
    assert summary_end + "\n## Risks\n" in appended_inside_summary


def test_record_changes_no_byte_outside_the_inserted_subsection(
    appended_inside_summary,
) -> None:
    inserted = "\n" + subsection(KEPT_ROW_LINE.replace("2.1", "1.1", 1))
    assert appended_inside_summary.replace(inserted, "", 1) == (
        PLAN_WITH_SUMMARY_THEN_RISKS
    )


# --- insertion: the summary is the last section -------------------------------

SUMMARY_LAST_BODY = PLAN_HEAD + BUILD_PROGRESS + "\n" + SUMMARY_HEADING + "\nDone.\n"
FIRST_KEPT_ROW = KEPT_ROW_LINE.replace("2.1", "1.1", 1)


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
    assert recorded.endswith(FIRST_KEPT_ROW)


def test_record_puts_the_subsection_at_the_end_of_a_last_summary() -> None:
    recorded = plan_summary_record.record(
        SUMMARY_LAST_BODY, "1.1", ATTEMPT, one_kept_row()
    )
    assert recorded == SUMMARY_LAST_BODY + "\n" + subsection(FIRST_KEPT_ROW)


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
    assert recorded.endswith(subsection(FIRST_KEPT_ROW) + "\n" + BUILD_PROGRESS)


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


# --- the command line writes the file -----------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(SCRIPT_PY), *args]
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"timed out after {CLI_TIMEOUT_SECONDS}s: {argv}")


def _write_result(directory, rows: list[dict]):
    path = directory / "result.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return path


def test_record_cli_writes_the_updated_plan_and_prints_nothing(tmp_path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_bytes(PLAN_WITHOUT_SUMMARY.encode("utf-8"))
    result = _write_result(tmp_path, one_kept_row())
    run = _run(
        "record",
        "--plan",
        str(plan),
        "--step",
        STEP,
        "--attempt",
        "1",
        "--result",
        str(result),
    )
    assert (run.returncode, run.stdout, plan.read_bytes().decode("utf-8")) == (
        0,
        "",
        plan_summary_record.record(PLAN_WITHOUT_SUMMARY, STEP, ATTEMPT, one_kept_row()),
    )


def test_record_cli_keeps_utf8_text_and_crlf_line_ends_of_the_plan(tmp_path) -> None:
    original = "# Plan: café — naïve\r\n\r\n" + BUILD_PROGRESS.replace("\n", "\r\n")
    plan = tmp_path / "plan.md"
    plan.write_bytes(original.encode("utf-8"))
    result = _write_result(tmp_path, [make_row(1, reason="naïve — ok")])
    _run(
        "record",
        "--plan",
        str(plan),
        "--step",
        STEP,
        "--attempt",
        "1",
        "--result",
        str(result),
    )
    written = plan.read_bytes().decode("utf-8")
    assert (
        written.startswith("# Plan: café — naïve\r\n\r\n"),
        written.endswith(BUILD_PROGRESS.replace("\n", "\r\n")),
        "naïve — ok" in written,
    ) == (True, True, True)


# --- the floor-slice exemption ------------------------------------------------


def _slice_exclusions() -> dict[str, str]:
    tree = ast.parse(FLOOR_TEST.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "SLICE_EXCLUSIONS" for t in node.targets)
    )
    return ast.literal_eval(assignment.value)


def test_the_record_script_is_exempt_from_the_floor_slice_with_a_reason() -> None:
    assert _slice_exclusions().get("plan_summary_record.py", "").strip() != ""
