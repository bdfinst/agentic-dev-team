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
