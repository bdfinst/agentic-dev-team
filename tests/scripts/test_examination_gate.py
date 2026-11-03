"""Pre-PR examination gate (#2270, Step 1.4).

The pure function is tested with injected inputs; the real-record and wiring
scenarios run `load_and_check` and `progress_guardian --pre-pr` against a temp
git repository.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from examination_fixtures import (
    CRITERION_1,
    PLAN_ID,
    SOURCE_FILE,
    git_env,
    make_repo,
    write_met_record,
)

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))
import examination_gate as gate  # type: ignore[import-not-found]
from examination_store import (  # type: ignore[import-not-found]
    BASE_UNRESOLVABLE,
    EMPTY_DIFF,
    RecordUnreadable,
)

PG = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "progress_guardian.py"
CLI = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "acceptance_examination.py"
PATH = ".claude/memory/acceptance-examination-plans__x.md.json"
HASH, DIGEST = "h1", "d1"


def _row(cid: str, verdict: str = "met", observation: str = "fine") -> dict:
    return {
        "criterion": cid,
        "verdict": verdict,
        "command": "run",
        "observation": observation,
    }


def _record(**overrides: object) -> dict:
    record = {
        "plan": PLAN_ID,
        "overall": "met",
        "criteria": [_row("AC1"), _row("AC2")],
        "problems": [],
        "audit_findings": [],
        "binding_hash": HASH,
        "inputs_digest": DIGEST,
    }
    record.update(overrides)
    return record


def _check(
    record: object = "default",
    binding: str = HASH,
    digest: str = DIGEST,
    exempt: bool = False,
) -> list[dict]:
    record = _record() if record == "default" else record
    return gate.check_acceptance_examination(
        PLAN_ID, record, PATH, binding, digest, exempt
    )


def _text(issue: dict) -> str:
    return issue["message"] + " " + issue["suggestedFix"]


def _only_error(issues: list[dict]) -> dict:
    assert [i["severity"] for i in issues] == ["error"], issues
    return issues[0]


def test_current_met_record_passes() -> None:
    assert _check() == []


def test_exempt_plan_without_record_reports_info_only() -> None:
    issues = _check(record=None, exempt=True)
    assert [i["severity"] for i in issues] == ["info"]
    assert "not applicable" in issues[0]["message"]


def test_exempt_plan_ignores_an_unreadable_record() -> None:
    issues = _check(record=RecordUnreadable("invalid JSON"), exempt=True)
    assert [i["severity"] for i in issues] == ["info"]


def test_not_met_names_criteria_and_first_observation_line_only() -> None:
    rows = [_row("AC1"), _row("AC2", "not-met", "expected 3 got 2\nstack trace")]
    issue = _only_error(_check(_record(overall="not-met", criteria=rows)))
    text = _text(issue)
    for expected in (
        "Acceptance criteria not met: AC2",
        "AC2: expected 3 got 2",
        "/build plans/x.md",
    ):
        assert expected in text
    assert "stack trace" not in text


def test_not_met_lists_every_failing_criterion() -> None:
    rows = [_row("AC1", "not-met", "one"), _row("AC2", "not-met", "two")]
    text = _text(_only_error(_check(_record(overall="not-met", criteria=rows))))
    assert "not met: AC1, AC2" in text
    assert "AC1: one" in text and "AC2: two" in text


def test_unobservable_indeterminate_names_criteria_and_observation() -> None:
    rows = [_row("AC1"), _row("AC2", "indeterminate", "no HTTP entry point named")]
    issue = _only_error(_check(_record(overall="indeterminate", criteria=rows)))
    for expected in (
        "could not observe AC2",
        "no HTTP entry point named",
        "Make each criterion observable",
    ):
        assert expected in _text(issue)


@pytest.mark.parametrize(
    ("problems", "gloss", "remedy"),
    [
        (["missing AC2"], "no row for AC2", "again without changing the plan"),
        (["missing AC1,AC3"], "no row for AC1, AC3", "again without changing"),
        (
            ["command-not-run AC1"],
            "AC1 names a command it never ran",
            "again without changing the plan",
        ),
        (
            ["no-acceptance-criteria"],
            "the plan lists no acceptance criteria",
            "Add acceptance criteria to the plan",
        ),
        (
            ["binding-hash-unavailable"],
            "the branch base could not be resolved",
            "git fetch origin",
        ),
        (["duplicate AC2"], "AC2 has more than one row", "again without changing"),
        (["unknown AC9"], "AC9 is not a criterion in the plan", "again without"),
        (["incomplete-row AC1"], "AC1 has no observation or no command", "again"),
        (["invalid-verdict AC1 maybe"], "AC1 has a verdict that is not", "again"),
        (["invalid-result-shape"], "did not have the expected shape", "again"),
        (["unparseable-result"], "could not be parsed", "again"),
    ],
)
def test_malformed_result_glosses_each_problem(
    problems: list[str], gloss: str, remedy: str
) -> None:
    issue = _only_error(_check(_record(overall="indeterminate", problems=problems)))
    assert "the examiner's result was incomplete" in issue["message"]
    assert gloss in issue["message"]
    assert remedy in issue["suggestedFix"]


def test_malformed_result_glosses_every_problem() -> None:
    problems = ["missing AC2", "command-not-run AC1"]
    issue = _only_error(_check(_record(overall="indeterminate", problems=problems)))
    assert "no row for AC2" in issue["message"]
    assert "AC1 names a command it never ran" in issue["message"]


def test_unrecognised_problem_is_shown_as_written() -> None:
    issue = _only_error(_check(_record(overall="indeterminate", problems=["odd 7"])))
    assert "odd 7" in issue["message"]


def test_tainted_lists_three_commands_the_overflow_and_the_show_hint() -> None:
    findings = [{"command": f"cat secret{n}"} for n in range(1, 5)]
    issue = _only_error(_check(_record(overall="tainted", audit_findings=findings)))
    text = _text(issue)
    for expected in (
        "cat secret1",
        "cat secret2",
        "cat secret3",
        "(+1 more)",
        "may be a false positive",
        "show --plan plans/x.md",
        "Name a run command for each criterion",
    ):
        assert expected in text
    assert "cat secret4" not in text


def test_tainted_with_three_commands_has_no_overflow_marker() -> None:
    findings = [{"command": f"cat s{n}"} for n in range(3)]
    text = _text(
        _only_error(_check(_record(overall="tainted", audit_findings=findings)))
    )
    assert "more)" not in text


def test_missing_record_names_the_path_and_remedy() -> None:
    text = _text(_only_error(_check(record=None)))
    for expected in (
        "Acceptance examination missing",
        PATH,
        "has not run on this branch",
        "/build plans/x.md",
    ):
        assert expected in text


def test_unreadable_record_names_path_and_problem() -> None:
    issue = _only_error(_check(record=RecordUnreadable("missing key")))
    for expected in ("unreadable", PATH, "missing key", "Delete the file"):
        assert expected in _text(issue)


def test_record_for_another_plan_names_it() -> None:
    issue = _only_error(_check(_record(plan="plans/y.md")))
    assert "belongs to plans/y.md" in issue["message"]
    assert PATH in issue["message"]


@pytest.mark.parametrize(
    ("binding", "text"),
    [
        (BASE_UNRESOLVABLE, "branch base could not be resolved"),
        (EMPTY_DIFF, "no commits ahead of"),
    ],
)
def test_unavailable_binding_refuses_even_a_met_record(binding: str, text: str) -> None:
    assert text in _only_error(_check(binding=binding))["message"]


def test_base_unresolvable_remedy_is_the_git_fetch_line() -> None:
    issue = _only_error(_check(binding=BASE_UNRESOLVABLE))
    assert "git fetch origin" in issue["suggestedFix"]


@pytest.mark.parametrize(
    ("hash_now", "digest_now", "expected"),
    [
        ("h1", "d1", None),
        ("h2", "d1", "commits landed after it ran"),
        ("h1", "d2", "acceptance criteria, Gherkin, or run commands"),
    ],
)
def test_staleness_is_detected_by_hash_or_digest(
    hash_now: str, digest_now: str, expected: str | None
) -> None:
    issues = _check(binding=hash_now, digest=digest_now)
    if expected is None:
        assert issues == []
        return
    assert expected in _only_error(issues)["message"]
    assert "re-runs the examiner" in issues[0]["suggestedFix"]


STALE_BOTH = {"binding": "h2", "digest": "d2"}
PRECEDENCE_CASES = {
    "unreadable": (
        {"record": RecordUnreadable("bad"), **STALE_BOTH},
        "record unreadable",
    ),
    "other plan over not-met": (
        {"record": _record(plan="plans/y.md", overall="not-met")},
        "belongs to plans/y.md",
    ),
    "base-unresolvable over stale diff": (
        {"binding": BASE_UNRESOLVABLE},
        "branch base could not be resolved",
    ),
    "empty-diff over stale diff": ({"binding": EMPTY_DIFF}, "no commits ahead of"),
    "stale diff over stale inputs": (STALE_BOTH, "commits landed after it ran"),
    "stale inputs over tainted": (
        {
            "record": _record(overall="tainted", audit_findings=[{"command": "cat x"}]),
            "digest": "d2",
        },
        "acceptance criteria, Gherkin, or run commands",
    ),
    "stale diff over not-met": (
        {"record": _record(overall="not-met"), "binding": "h2"},
        "commits landed after it ran",
    ),
}


@pytest.mark.parametrize(
    ("kwargs", "message"), PRECEDENCE_CASES.values(), ids=PRECEDENCE_CASES.keys()
)
def test_only_the_highest_precedence_condition_is_reported(
    kwargs: dict, message: str
) -> None:
    assert message in _only_error(_check(**kwargs))["message"]


def test_every_error_carries_a_rule_id_and_the_plan_as_file() -> None:
    issue = _only_error(_check(record=None))
    assert issue["rule_id"] == gate.RULE_MISSING
    assert issue["file"] == PLAN_ID


# --- real repository -------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key, value in git_env(tmp_path).items():
        monkeypatch.setenv(key, value)
    return make_repo(tmp_path)


def _run_pg(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PG), "--plan", str(root / PLAN_ID), "--skip-llm", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env=git_env(root.parent),
    )


def _tick_all_and_render_section(root: Path) -> None:
    plan = root / PLAN_ID
    plan.write_text(
        plan.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(CLI), "render", "--plan", str(plan)],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env=git_env(root.parent),
    )
    assert result.returncode == 0, result.stderr
    assert "## Acceptance Examination" in plan.read_text(encoding="utf-8")


def test_real_met_record_is_current_per_load_and_check(repo: Path) -> None:
    write_met_record(repo)
    assert gate.load_and_check(repo / PLAN_ID) == []


def test_real_met_record_stays_current_through_builds_own_edits(repo: Path) -> None:
    write_met_record(repo)
    _tick_all_and_render_section(repo)
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["issues"] == []


def test_real_met_record_stales_on_a_criterion_edit(repo: Path) -> None:
    write_met_record(repo)
    plan = repo / PLAN_ID
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(CRITERION_1, "Changed behavior"),
        encoding="utf-8",
    )
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 1
    assert "acceptance criteria, Gherkin, or run commands changed" in result.stdout


def test_real_met_record_stales_when_a_commit_lands(repo: Path) -> None:
    write_met_record(repo)
    (repo / SOURCE_FILE).write_text("changed\n", encoding="utf-8")
    subprocess.run(
        ["git", "commit", "-q", "-am", "fix: change"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=git_env(repo.parent),
    )
    assert (
        "commits landed after it ran"
        in gate.load_and_check(repo / PLAN_ID)[0]["message"]
    )


def test_pre_pr_without_a_record_is_refused(repo: Path) -> None:
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 1
    assert "Acceptance examination missing" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


def test_exempt_plan_passes_pre_pr_without_a_record(repo: Path) -> None:
    plan = repo / PLAN_ID
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "# Plan x\n", "# Plan x\n\n**Examination**: not-applicable\n"
        ),
        encoding="utf-8",
    )
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 0, result.stdout
    assert "Acceptance examination" not in result.stdout


def test_without_pre_pr_the_gate_is_not_consulted(repo: Path) -> None:
    result = _run_pg(repo)
    assert "Acceptance examination" not in result.stdout


def test_unreadable_record_on_disk_is_refused_without_traceback(repo: Path) -> None:
    path = write_met_record(repo)
    path.write_text("{not json", encoding="utf-8")
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 1
    assert "unreadable" in result.stdout and "invalid JSON" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


def test_load_and_check_outside_a_repository_is_one_error(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# plan\n", encoding="utf-8")
    issue = _only_error(gate.load_and_check(plan))
    assert "not a git repository" in issue["message"]


def test_load_and_check_with_a_missing_plan_file_is_one_error(repo: Path) -> None:
    issue = _only_error(gate.load_and_check(repo / "plans" / "gone.md"))
    assert "could not be read" in issue["message"]
