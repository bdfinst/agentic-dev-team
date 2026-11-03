"""Subprocess tests for the acceptance-examination CLI (#2270, Step 1.5)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from examination_fixtures import (
    CRITERION_1,
    CRITERION_2,
    PLAN_ID,
    PLAN_TEXT,
    RUN_COMMAND,
    git_env,
    make_repo,
    store,
    write_met_record,
)

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "scripts"
    / "acceptance_examination.py"
)
sys.path.insert(0, str(SCRIPT.parent))
import acceptance_examination as cli

MARKER = f"Acceptance-examination plan: {PLAN_ID}"
GHERKIN_BLOCK = "Feature: x\n  Scenario: y"


def run_cli(
    root: Path, *args: str, home: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=git_env(home or root.parent),
        timeout=60,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_inputs_prints_criteria_gherkin_commands_and_marker(repo: Path) -> None:
    plan = repo / PLAN_ID
    gate_item = f"- `{RUN_COMMAND}`"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(gate_item, f"- [ ] `{RUN_COMMAND}`")
        + f"\n## Slices\n\n```gherkin\n{GHERKIN_BLOCK}\n```\n",
        encoding="utf-8",
    )

    result = run_cli(repo, "inputs", "--plan", PLAN_ID)

    assert result.returncode == 0
    assert f"AC1: {CRITERION_1}" in result.stdout
    assert f"AC2: {CRITERION_2}" in result.stdout
    assert GHERKIN_BLOCK in result.stdout
    assert f"- {RUN_COMMAND}" in result.stdout
    assert result.stdout.rstrip().endswith(MARKER)


@pytest.mark.parametrize(
    "plan_arg",
    ["plans/missing.md", "NO_AC_PLAN"],
    ids=["missing-plan-file", "no-acceptance-criteria-heading"],
)
def test_inputs_misuse_is_one_line_exit_two(repo: Path, plan_arg: str) -> None:
    if plan_arg == "NO_AC_PLAN":
        plan_arg = "plans/no-ac.md"
        (repo / plan_arg).write_text("# Plan\n\n## Goal\n\ntext\n", encoding="utf-8")

    result = run_cli(repo, "inputs", "--plan", plan_arg)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert result.stdout == ""


NOT_MET_ROW = {
    "criterion": "AC1",
    "verdict": "not-met",
    "command": RUN_COMMAND,
    "observation": "AC1 failed on input 3\nsecond line",
}
MISSING_MESSAGE = "Acceptance examination missing"
BUILD_REMEDY = f"/build {PLAN_ID}"


def test_status_on_current_met_record_exits_zero(repo: Path) -> None:
    write_met_record(repo)

    result = run_cli(repo, "status", "--plan", PLAN_ID)

    assert result.returncode == 0
    assert result.stdout.strip() == (
        f"Acceptance examination met and up to date for {PLAN_ID}."
    )


def test_status_prints_exactly_the_not_met_message_and_remedy(repo: Path) -> None:
    write_met_record(repo, overall="not-met", criteria=[NOT_MET_ROW])

    result = run_cli(repo, "status", "--plan", PLAN_ID)

    assert result.returncode == 1
    assert result.stdout.strip().splitlines() == [
        "Acceptance criteria not met: AC1. AC1: AC1 failed on input 3.",
        f"Fix the delivered behavior, commit, then run: {BUILD_REMEDY}.",
    ]


def test_status_on_exempt_plan_exits_zero_without_a_record(repo: Path) -> None:
    plan = repo / PLAN_ID
    plan.write_text(
        "**Examination**: not-applicable\n\n" + plan.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = run_cli(repo, "status", "--plan", PLAN_ID)

    assert result.returncode == 0
    assert "not applicable" in result.stdout


def test_status_without_wait_reports_missing_and_does_not_announce_waiting(
    repo: Path,
) -> None:
    result = run_cli(repo, "status", "--plan", PLAN_ID)

    assert result.returncode == 1
    assert MISSING_MESSAGE in result.stdout
    assert "Waiting" not in result.stderr


def test_status_waits_for_a_record_that_appears_late(repo: Path) -> None:
    wait = 30
    process = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT),
            *("status", "--plan", PLAN_ID),
            *("--wait", str(wait), "--poll-interval", "0"),
        ],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=git_env(repo.parent),
    )
    try:
        waiting_line = process.stderr.readline()  # blocks until polling began
        write_met_record(repo)
        stdout, stderr = process.communicate(timeout=60)
    finally:
        process.kill()
        process.communicate()

    assert process.returncode == 0
    assert f"Waiting for the acceptance examination record (up to {wait}s)" in (
        waiting_line + stderr
    )
    assert "met and up to date" in stdout


def test_status_gives_up_after_the_wait_window(repo: Path) -> None:
    result = run_cli(repo, "status", "--plan", PLAN_ID, "--wait", "1")

    assert result.returncode == 1
    assert MISSING_MESSAGE in result.stdout
    assert BUILD_REMEDY in result.stdout
    assert "Waiting for the acceptance examination record (up to 1s)" in result.stderr


@pytest.mark.parametrize(
    "extra",
    [("--wait", "abc"), ("--wait", "-1"), ("--poll-interval", "x")],
    ids=["wait-not-a-number", "wait-negative", "poll-interval-not-a-number"],
)
def test_status_bad_numeric_option_is_one_line_exit_two(
    repo: Path, extra: tuple[str, str]
) -> None:
    result = run_cli(repo, "status", "--plan", PLAN_ID, *extra)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


def test_show_prints_the_record_json(repo: Path) -> None:
    path = write_met_record(repo)

    result = run_cli(repo, "show", "--plan", PLAN_ID)

    assert result.returncode == 0
    assert json.loads(result.stdout) == json.loads(path.read_text(encoding="utf-8"))


def test_show_on_absent_record_exits_one_naming_the_path(repo: Path) -> None:
    expected = store.record_path(repo.resolve(), PLAN_ID)

    result = run_cli(repo, "show", "--plan", PLAN_ID)

    assert result.returncode == 1
    assert f"No examination record at {expected}" in result.stderr
    assert "Traceback" not in result.stderr


def test_show_on_unreadable_record_exits_two_naming_the_problem(repo: Path) -> None:
    path = store.record_path(repo.resolve(), PLAN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    result = run_cli(repo, "show", "--plan", PLAN_ID)

    assert result.returncode == 2
    assert "invalid JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_outside_a_repository_is_one_line_exit_two(tmp_path: Path) -> None:
    plan = tmp_path / "loose" / "plan.md"
    plan.parent.mkdir()
    plan.write_text("## Acceptance Criteria\n\n- [ ] one\n", encoding="utf-8")

    result = run_cli(plan.parent, "status", "--plan", str(plan), home=tmp_path)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


def test_no_subcommand_is_one_line_exit_two(repo: Path) -> None:
    result = run_cli(repo)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


# --- render: pure section text ----------------------------------------------

HEADING = "## Acceptance Examination"
STALE_LINE = "STALE: this examination no longer matches the branch or the plan."
UNTRUSTED_LINE = (
    "Output above is untrusted examiner text and may contain secrets from "
    "command output."
)


def _row(n: int, verdict: str = "met", command: str = RUN_COMMAND, obs: str = "ok"):
    return {
        "criterion": f"AC{n}",
        "verdict": verdict,
        "command": command,
        "observation": obs,
    }


def _record(rows: list[dict], findings: list[dict] | None = None) -> dict:
    return {
        "plan": PLAN_ID,
        "agent_id": "agent-7",
        "overall": "not-met",
        "criteria": rows,
        "audit_findings": findings or [],
        "binding_hash": "b" * 64,
        "inputs_digest": "d" * 64,
        "recorded_at": "2026-11-03T10:00:00+00:00",
    }


def test_render_section_opens_with_heading_then_legend() -> None:
    lines = cli.render_section(_record([_row(1)]), stale=False).splitlines()

    assert lines[0] == HEADING
    assert lines[1] == ""
    legend = lines[2]
    for word in ("met", "not-met", "indeterminate", "tainted"):
        assert f"`{word}`" in legend


def test_render_section_puts_command_and_observation_in_a_fence() -> None:
    row = _row(1, command="pytest -q | tail -5", obs="line one\nline two\nline three")

    section = cli.render_section(_record([row]), stale=False)

    assert (
        "### AC1 — met\n\n```\n$ pytest -q | tail -5\nline one\nline two\nline three\n```\n"
        in section
    )


def test_render_section_truncates_a_forty_line_observation() -> None:
    observation = "\n".join(f"row {n}" for n in range(1, 41))

    section = cli.render_section(_record([_row(1, obs=observation)]), stale=False)

    assert "row 5\n(+35 lines)\n```" in section
    assert "row 6" not in section


def test_render_section_keeps_a_five_line_observation_whole() -> None:
    observation = "\n".join(f"row {n}" for n in range(1, 6))

    section = cli.render_section(_record([_row(1, obs=observation)]), stale=False)

    assert "row 5\n```" in section
    assert "(+" not in section


def test_render_section_lists_failing_criteria_first_in_id_order() -> None:
    rows = [
        _row(1, "met"),
        _row(2, "indeterminate", command=""),
        _row(3, "met"),
        _row(10, "not-met"),
        _row(4, "not-met"),
    ]

    section = cli.render_section(_record(rows), stale=False)

    headings = [ln for ln in section.splitlines() if ln.startswith("### AC")]
    assert headings == [
        "### AC2 — indeterminate",
        "### AC4 — not-met",
        "### AC10 — not-met",
        "### AC1 — met",
        "### AC3 — met",
    ]


def test_render_section_omits_the_command_line_when_there_is_no_command() -> None:
    row = _row(1, "indeterminate", command="", obs="could not observe")

    section = cli.render_section(_record([row]), stale=False)

    assert "```\ncould not observe\n```" in section


def test_render_section_outgrows_backticks_inside_the_observation() -> None:
    row = _row(1, obs="before\n```\n## not a heading\nafter")

    section = cli.render_section(_record([row]), stale=False)

    assert (
        "````\n$ python3 -m pytest -q\nbefore\n```\n## not a heading\nafter\n````"
        in section
    )


def test_render_section_stale_marker_is_the_first_line_after_the_heading() -> None:
    stale = cli.render_section(_record([_row(1)]), stale=True).splitlines()
    fresh = cli.render_section(_record([_row(1)]), stale=False)

    assert stale[0] == HEADING
    assert stale[1:3] == ["", STALE_LINE]
    assert "STALE" not in fresh


def test_render_section_ends_with_audit_details() -> None:
    findings = [{"kind": "read", "target": "src/a.py", "command": "cat src/a.py"}]

    section = cli.render_section(_record([_row(1)], findings), stale=False)

    tail = section.split("### Audit details\n", 1)[1]
    for expected in (
        "Overall: not-met",
        f"Binding hash: {'b' * 64}",
        f"Inputs digest: {'d' * 64}",
        "Agent: agent-7",
        "Recorded at: 2026-11-03T10:00:00+00:00",
        "read src/a.py: cat src/a.py",
    ):
        assert expected in tail
    assert section.rstrip("\n").endswith(UNTRUSTED_LINE)


def test_render_section_says_none_without_audit_findings() -> None:
    section = cli.render_section(_record([_row(1)]), stale=False)

    assert "Audit findings: none" in section


# --- render: upsert into the plan text ----------------------------------------

SECTION = f"{HEADING}\n\n### AC1 — met\n\nbody\n"
PLAN_WITH_REVIEW = (
    "# Plan\n\n## Plan Review Summary\n\nreviewed\n\n## Build Progress\n\n- [x] one\n"
)


def test_upsert_inserts_between_review_summary_and_next_heading() -> None:
    result = cli.upsert_section(PLAN_WITH_REVIEW, SECTION)

    assert result == (
        "# Plan\n\n## Plan Review Summary\n\nreviewed\n\n"
        f"{SECTION}\n## Build Progress\n\n- [x] one\n"
    )


def test_upsert_appends_after_review_summary_that_ends_the_file() -> None:
    result = cli.upsert_section(
        "# Plan\n\n## Plan Review Summary\n\nreviewed\n", SECTION
    )

    assert result == f"# Plan\n\n## Plan Review Summary\n\nreviewed\n\n{SECTION}"


def test_upsert_replaces_an_existing_section_in_place() -> None:
    old = f"{HEADING}\n\n### AC1 — not-met\n\nold\n"
    plan = f"# Plan\n\n## Plan Review Summary\n\nr\n\n{old}\n## Build Progress\n\nx\n"

    result = cli.upsert_section(plan, SECTION)

    assert result == (
        f"# Plan\n\n## Plan Review Summary\n\nr\n\n{SECTION}\n## Build Progress\n\nx\n"
    )
    assert result.count(HEADING) == 1


def test_upsert_replaces_a_section_that_ends_the_file() -> None:
    plan = f"# Plan\n\n## Build Progress\n\nx\n\n{HEADING}\n\nold\n"

    assert cli.upsert_section(plan, SECTION) == (
        f"# Plan\n\n## Build Progress\n\nx\n\n{SECTION}"
    )


def test_upsert_appends_at_the_end_without_a_review_summary() -> None:
    plan = "# Plan\n\n## Build Progress\n\n- [x] one\n"

    assert cli.upsert_section(plan, SECTION) == f"{plan}\n{SECTION}"


def test_upsert_appends_when_the_file_lacks_a_final_newline() -> None:
    assert (
        cli.upsert_section("# Plan\n\ntext", SECTION) == f"# Plan\n\ntext\n\n{SECTION}"
    )


def test_upsert_ignores_headings_inside_fenced_output() -> None:
    old = f"{HEADING}\n\n```\n## Build Progress\n```\n"
    plan = f"# Plan\n\n{old}\n## Build Progress\n\nreal\n"

    result = cli.upsert_section(plan, SECTION)

    assert result == f"# Plan\n\n{SECTION}\n## Build Progress\n\nreal\n"


@pytest.mark.parametrize(
    "plan", ["", "# Plan\n", PLAN_WITH_REVIEW, f"# Plan\n\n{SECTION}\n## B\n\nx\n"]
)
def test_upsert_twice_equals_once(plan: str) -> None:
    once = cli.upsert_section(plan, SECTION)

    assert cli.upsert_section(once, SECTION) == once


# --- render: CLI contract -------------------------------------------------------

REVIEW_PLAN_TEXT = PLAN_TEXT.replace(
    "## Build Progress", "## Plan Review Summary\n\nreviewed\n\n## Build Progress"
)


def _write_plan(root: Path, text: str) -> Path:
    plan = root / PLAN_ID
    plan.write_text(text, encoding="utf-8")
    return plan


def _headings(plan_text: str) -> list[str]:
    return [ln for ln in plan_text.splitlines() if ln.startswith("## ")]


def _rewrite_record(root: Path, **changes: object) -> None:
    path = store.record_path(root.resolve(), PLAN_ID)
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(changes)
    path.write_text(json.dumps(record), encoding="utf-8")


def test_render_places_the_section_between_review_summary_and_build_progress(
    repo: Path,
) -> None:
    plan = _write_plan(repo, REVIEW_PLAN_TEXT)
    write_met_record(repo)

    result = run_cli(repo, "render", "--plan", PLAN_ID)

    assert result.returncode == 0, result.stderr
    assert _headings(plan.read_text(encoding="utf-8")) == [
        "## Acceptance Criteria",
        "## Pre-PR Quality Gate",
        "## Plan Review Summary",
        HEADING,
        "## Build Progress",
    ]


def test_render_writes_legend_criteria_and_audit_details(repo: Path) -> None:
    write_met_record(repo)

    run_cli(repo, "render", "--plan", PLAN_ID)

    text = (repo / PLAN_ID).read_text(encoding="utf-8")
    assert cli.LEGEND_LINE in text
    assert f"### AC1 — met\n\n```\n$ {RUN_COMMAND}\nAC1 passed\n```" in text
    assert text.index("### AC2") < text.index("### Audit details")
    assert text.rstrip("\n").endswith(UNTRUSTED_LINE)
    assert "STALE" not in text


def test_render_keeps_pipes_and_multiline_output_verbatim(repo: Path) -> None:
    write_met_record(repo)
    rows = [_row(1, command="pytest -q | tail -5", obs="a | b\nsecond\nthird"), _row(2)]
    _rewrite_record(repo, criteria=rows)

    run_cli(repo, "render", "--plan", PLAN_ID)

    text = (repo / PLAN_ID).read_text(encoding="utf-8")
    assert "```\n$ pytest -q | tail -5\na | b\nsecond\nthird\n```" in text


def test_render_replaces_an_existing_section_in_place(repo: Path) -> None:
    old = f"{HEADING}\n\n### AC1 — not-met\n\nold\n\n"
    _write_plan(
        repo, REVIEW_PLAN_TEXT.replace("## Build Progress", old + "## Build Progress")
    )
    write_met_record(repo)

    run_cli(repo, "render", "--plan", PLAN_ID)

    text = (repo / PLAN_ID).read_text(encoding="utf-8")
    assert _headings(text).count(HEADING) == 1
    assert _headings(text)[-2:] == [HEADING, "## Build Progress"]
    assert "### AC1 — met" in text
    assert "### AC1 — not-met" not in text
    assert "\nold\n" not in text


def test_render_appends_at_the_end_without_a_review_summary(repo: Path) -> None:
    write_met_record(repo)

    run_cli(repo, "render", "--plan", PLAN_ID)

    assert _headings((repo / PLAN_ID).read_text(encoding="utf-8"))[-1] == HEADING


def test_render_twice_leaves_the_file_byte_identical(repo: Path) -> None:
    _write_plan(repo, REVIEW_PLAN_TEXT)
    write_met_record(repo)
    run_cli(repo, "render", "--plan", PLAN_ID)
    after_first = (repo / PLAN_ID).read_bytes()

    result = run_cli(repo, "render", "--plan", PLAN_ID)

    assert result.returncode == 0
    assert (repo / PLAN_ID).read_bytes() == after_first


def test_render_truncates_a_forty_line_observation(repo: Path) -> None:
    write_met_record(repo)
    observation = "\n".join(f"line {n}" for n in range(1, 41))
    _rewrite_record(repo, criteria=[_row(1, obs=observation), _row(2)])

    run_cli(repo, "render", "--plan", PLAN_ID)

    text = (repo / PLAN_ID).read_text(encoding="utf-8")
    assert "line 5\n(+35 lines)\n```" in text
    assert "line 6\n" not in text


def test_render_marks_a_record_whose_binding_is_not_current(repo: Path) -> None:
    write_met_record(repo)
    _rewrite_record(repo, binding_hash="0" * 64)

    run_cli(repo, "render", "--plan", PLAN_ID)

    lines = (repo / PLAN_ID).read_text(encoding="utf-8").splitlines()
    start = lines.index(HEADING)
    assert lines[start + 2] == STALE_LINE


def test_render_marks_a_record_whose_inputs_digest_is_not_current(repo: Path) -> None:
    write_met_record(repo)
    _rewrite_record(repo, inputs_digest="0" * 64)

    run_cli(repo, "render", "--plan", PLAN_ID)

    assert STALE_LINE in (repo / PLAN_ID).read_text(encoding="utf-8")


def test_render_refuses_an_absent_record_and_leaves_the_plan_alone(repo: Path) -> None:
    before = (repo / PLAN_ID).read_bytes()
    expected = store.record_path(repo.resolve(), PLAN_ID)

    result = run_cli(repo, "render", "--plan", PLAN_ID)

    assert result.returncode == 1
    assert f"No examination record at {expected}" in result.stderr
    assert "Traceback" not in result.stderr
    assert (repo / PLAN_ID).read_bytes() == before


def test_render_refuses_an_unreadable_record_and_leaves_the_plan_alone(
    repo: Path,
) -> None:
    path = store.record_path(repo.resolve(), PLAN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    before = (repo / PLAN_ID).read_bytes()

    result = run_cli(repo, "render", "--plan", PLAN_ID)

    assert result.returncode == 2
    assert "invalid JSON" in result.stderr
    assert "Traceback" not in result.stderr
    assert (repo / PLAN_ID).read_bytes() == before


def test_render_refuses_a_record_for_another_plan(repo: Path) -> None:
    path = write_met_record(repo)
    _rewrite_record(repo, plan="plans/other.md")
    before = (repo / PLAN_ID).read_bytes()

    result = run_cli(repo, "render", "--plan", PLAN_ID)

    assert result.returncode == 2
    assert f"Record at {path} belongs to plans/other.md, not {PLAN_ID}" in result.stderr
    assert "Traceback" not in result.stderr
    assert (repo / PLAN_ID).read_bytes() == before


@pytest.mark.parametrize(
    "name",
    [
        "acceptance-examination-plans__x.md.json",
        "acceptance-examination-plans__x.md.json.lock",
    ],
)
def test_record_and_lock_paths_are_gitignored(name: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    rules = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/memory/acceptance-examination-*.json*" in rules
    result = subprocess.run(
        ["git", "check-ignore", "-q", f".claude/memory/{name}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
