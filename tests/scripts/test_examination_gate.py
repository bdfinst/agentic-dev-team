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
from examination_fixtures import EXEMPT_HEADER, write_met_record
from examination_repo import (
    BINDING_HASH,
    CRITERION_1,
    INPUTS_DIGEST,
    PLAN_ID,
    SOURCE_FILE,
    git_env,
    make_repo,
)
from examination_repo import record as make_record
from examination_repo import row as make_row

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))
import examination_gate as gate  # type: ignore[import-not-found]
from examination_store import (  # type: ignore[import-not-found]
    BASE_UNRESOLVABLE,
    EMPTY_DIFF,
    Binding,
    RecordUnreadable,
)
from examination_verdict import (  # type: ignore[import-not-found]
    build_record,
    validate_rows,
)

PG = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "progress_guardian.py"
CLI = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "acceptance_examination.py"
PATH = ".claude/memory/acceptance-examination-plans__x.md.json"
HASH, DIGEST = BINDING_HASH, INPUTS_DIGEST


def _check(
    record: object = "default",
    binding: str = HASH,
    digest: str = DIGEST,
    exempt: bool = False,
    after: str | None = None,
) -> list[dict]:
    record = make_record() if record == "default" else record
    return gate.check_acceptance_examination(
        PLAN_ID,
        record,
        PATH,
        Binding(binding, digest),
        exempt,
        gate.parse_timestamp(after) if after else None,
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
    assert issues[0]["rule_id"] == gate.RULE_NOT_APPLICABLE


def test_exempt_plan_ignores_an_unreadable_record() -> None:
    issues = _check(record=RecordUnreadable("invalid JSON"), exempt=True)
    assert [i["severity"] for i in issues] == ["info"]


def test_not_met_names_criteria_and_first_observation_line_only() -> None:
    rows = [
        make_row("AC1"),
        make_row("AC2", "not-met", observation="expected 3 got 2\nstack trace"),
    ]
    issue = _only_error(_check(make_record(overall="not-met", criteria=rows)))
    text = _text(issue)
    for expected in (
        "Acceptance criteria not met: AC2",
        "AC2: expected 3 got 2",
        "/build plans/x.md",
    ):
        assert expected in text
    assert "stack trace" not in text


def test_not_met_lists_every_failing_criterion() -> None:
    rows = [
        make_row("AC1", "not-met", observation="one"),
        make_row("AC2", "not-met", observation="two"),
    ]
    text = _text(_only_error(_check(make_record(overall="not-met", criteria=rows))))
    assert "not met: AC1, AC2" in text
    assert "AC1: one" in text and "AC2: two" in text


def test_unobservable_indeterminate_names_criteria_and_observation() -> None:
    rows = [
        make_row("AC1"),
        make_row("AC2", "indeterminate", observation="no HTTP entry point named"),
    ]
    issue = _only_error(_check(make_record(overall="indeterminate", criteria=rows)))
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
            ["base-unresolvable"],
            "the branch base could not be resolved",
            "git fetch origin",
        ),
        (
            ["empty-diff"],
            "the branch has no commits ahead of its base",
            "Commit your changes",
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
    issue = _only_error(_check(make_record(overall="indeterminate", problems=problems)))
    assert "the examiner's result was incomplete" in issue["message"]
    assert gloss in issue["message"]
    assert remedy in issue["suggestedFix"]


def test_malformed_result_glosses_every_problem() -> None:
    problems = ["missing AC2", "command-not-run AC1"]
    issue = _only_error(_check(make_record(overall="indeterminate", problems=problems)))
    assert "no row for AC2" in issue["message"]
    assert "AC1 names a command it never ran" in issue["message"]


def test_unrecognised_problem_is_shown_as_written() -> None:
    issue = _only_error(
        _check(make_record(overall="indeterminate", problems=["odd 7"]))
    )
    assert "odd 7" in issue["message"]


def test_tainted_lists_three_commands_the_overflow_and_the_show_hint() -> None:
    findings = [{"command": f"cat secret{n}"} for n in range(1, 5)]
    issue = _only_error(_check(make_record(overall="tainted", audit_findings=findings)))
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
        _only_error(_check(make_record(overall="tainted", audit_findings=findings)))
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
    issue = _only_error(_check(make_record(plan="plans/y.md")))
    assert "belongs to plans/y.md" in issue["message"]
    assert PATH in issue["message"]


@pytest.mark.parametrize(
    "after",
    [
        "2026-11-03T10:00:01+00:00",
        "2026-11-03T10:00:00Z",
        "2026-11-03T10:00:00",
        "2026-11-03T12:00:00+01:00",
    ],
    ids=[
        "one-second-later",
        "same-instant-z",
        "same-instant-naive",
        "same-instant-offset",
    ],
)
def test_record_not_newer_than_after_counts_as_absent(after: str) -> None:
    issue = _only_error(_check(after=after))
    assert issue["rule_id"] == gate.RULE_MISSING
    assert issue["message"] == gate.refusal_message(
        gate.RULE_MISSING, PLAN_ID, path=PATH
    )


@pytest.mark.parametrize(
    "after",
    ["2026-11-03T09:59:59+00:00", "2026-11-03T09:59:59Z", "2026-11-03T11:00:00+02:00"],
    ids=["second-earlier", "second-earlier-z", "earlier-in-offset"],
)
def test_record_newer_than_after_keeps_its_verdict(after: str) -> None:
    assert _check(after=after) == []
    not_met = make_record(overall="not-met", rows=[make_row("AC1", verdict="not-met")])
    assert _only_error(_check(not_met, after=after))["rule_id"] == gate.RULE_NOT_MET


@pytest.mark.parametrize(
    "recorded_at",
    [None, "", "yesterday", 20261103],
    ids=["absent", "empty", "unparsable", "not-a-string"],
)
def test_record_without_a_usable_time_counts_as_absent_under_after(
    recorded_at: object,
) -> None:
    record = make_record()
    if recorded_at is None:
        del record["recorded_at"]
    else:
        record["recorded_at"] = recorded_at
    issue = _only_error(_check(record, after="2020-01-01T00:00:00Z"))
    assert issue["rule_id"] == gate.RULE_MISSING


def test_without_after_an_old_record_is_judged_on_its_verdict() -> None:
    assert _check(make_record(recorded_at="1999-01-01T00:00:00+00:00")) == []


@pytest.mark.parametrize(
    ("record", "rule"),
    [
        (RecordUnreadable("bad"), gate.RULE_UNREADABLE),
        (make_record(plan="plans/y.md"), gate.RULE_OTHER_PLAN),
    ],
    ids=["unreadable", "other-plan"],
)
def test_after_does_not_outrank_unreadable_or_other_plan(
    record: object, rule: str
) -> None:
    assert _only_error(_check(record, after="2030-01-01T00:00:00Z"))["rule_id"] == rule


def test_after_outranks_a_sentinel_binding() -> None:
    issue = _only_error(_check(binding=EMPTY_DIFF, after="2030-01-01T00:00:00Z"))
    assert issue["rule_id"] == gate.RULE_MISSING


def test_exempt_plan_ignores_after() -> None:
    issues = _check(record=None, exempt=True, after="2030-01-01T00:00:00Z")
    assert [i["rule_id"] for i in issues] == [gate.RULE_NOT_APPLICABLE]


@pytest.mark.parametrize("text", ["", "now", "2026-13-01T00:00:00Z"])
def test_parse_timestamp_rejects_what_is_not_iso_8601(text: str) -> None:
    assert gate.parse_timestamp(text) is None


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


def _sentinel_record(stored: str) -> dict:
    return make_record(
        overall="indeterminate",
        problems=[stored],
        binding_hash=stored,
    )


@pytest.mark.parametrize("stored", [BASE_UNRESOLVABLE, EMPTY_DIFF])
def test_record_stored_with_a_sentinel_is_redispatchable_once_the_binding_resolves(
    stored: str,
) -> None:
    issue = _only_error(_check(_sentinel_record(stored), binding=HASH))
    assert issue["rule_id"] == gate.RULE_STALE_DIFF
    assert "re-runs the examiner" in issue["suggestedFix"]


@pytest.mark.parametrize(
    ("stored", "rule", "remedy"),
    [
        (BASE_UNRESOLVABLE, gate.RULE_BASE_UNRESOLVABLE, "git fetch origin"),
        (EMPTY_DIFF, gate.RULE_EMPTY_DIFF, "Commit your changes"),
    ],
)
def test_record_stored_with_a_sentinel_gets_the_current_sentinels_refusal(
    stored: str, rule: str, remedy: str
) -> None:
    issue = _only_error(_check(_sentinel_record(stored), binding=stored))
    assert issue["rule_id"] == rule
    assert remedy in issue["suggestedFix"]


def test_unchanged_binding_and_inputs_are_not_stale() -> None:
    assert _check(binding=HASH, digest=DIGEST) == []


@pytest.mark.parametrize(
    ("hash_now", "digest_now", "expected"),
    [
        ("h2", DIGEST, "commits landed after it ran"),
        (HASH, "d2", "acceptance criteria, Gherkin, or run commands"),
    ],
)
def test_staleness_is_detected_by_hash_or_digest(
    hash_now: str, digest_now: str, expected: str
) -> None:
    issues = _check(binding=hash_now, digest=digest_now)
    assert expected in _only_error(issues)["message"]
    assert "re-runs the examiner" in issues[0]["suggestedFix"]


STALE_BOTH = {"binding": "h2", "digest": "d2"}
PRECEDENCE_CASES = {
    "unreadable": (
        {"record": RecordUnreadable("bad"), **STALE_BOTH},
        "record unreadable",
    ),
    "other plan over not-met": (
        {"record": make_record(plan="plans/y.md", overall="not-met")},
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
            "record": make_record(
                overall="tainted", audit_findings=[{"command": "cat x"}]
            ),
            "digest": "d2",
        },
        "acceptance criteria, Gherkin, or run commands",
    ),
    "stale diff over not-met": (
        {"record": make_record(overall="not-met"), "binding": "h2"},
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


def test_load_and_check_after_a_later_time_reports_the_record_absent(
    repo: Path,
) -> None:
    write_met_record(repo)
    issue = _only_error(
        gate.load_and_check(repo / PLAN_ID, after="2999-01-01T00:00:00Z")
    )
    assert issue["rule_id"] == gate.RULE_MISSING


def test_load_and_check_after_an_earlier_time_keeps_the_met_verdict(
    repo: Path,
) -> None:
    write_met_record(repo)
    assert gate.load_and_check(repo / PLAN_ID, after="2000-01-01T00:00:00Z") == []


def test_load_and_check_rejects_an_after_that_is_not_a_time(repo: Path) -> None:
    with pytest.raises(ValueError, match="not an ISO 8601 time"):
        gate.load_and_check(repo / PLAN_ID, after="soon")


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
            "# Plan x\n", "# Plan x\n\n" + EXEMPT_HEADER
        ),
        encoding="utf-8",
    )
    result = _run_pg(repo, "--pre-pr")
    assert result.returncode == 0, result.stdout
    issues = json.loads(result.stdout)["issues"]
    assert [i["rule_id"] for i in issues] == [gate.RULE_NOT_APPLICABLE]
    assert [i["severity"] for i in issues] == ["info"]
    assert "not applicable" in issues[0]["message"]


def test_without_pre_pr_the_gate_is_not_consulted(repo: Path) -> None:
    result = _run_pg(repo)
    json.loads(result.stdout)  # a result document, not a crash
    assert "Traceback" not in result.stderr
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


# --- review-fix additions (#2270) ---------------------------------------------


def test_is_stale_is_true_for_a_moved_hash_or_a_moved_digest() -> None:
    record = make_record()
    assert not gate.is_stale(record, Binding(HASH, DIGEST))
    assert gate.is_stale(record, Binding("h2", DIGEST))
    assert gate.is_stale(record, Binding(HASH, "d2"))


def test_is_stale_is_true_against_a_sentinel_binding() -> None:
    for sentinel in (BASE_UNRESOLVABLE, EMPTY_DIFF):
        assert gate.is_stale(make_record(), Binding(sentinel, DIGEST))


@pytest.mark.parametrize("sentinel", [BASE_UNRESOLVABLE, EMPTY_DIFF])
def test_is_stale_is_true_for_a_sentinel_record_against_the_same_sentinel(
    sentinel: str,
) -> None:
    record = make_record(binding_hash=sentinel)
    assert gate.is_stale(record, Binding(sentinel, DIGEST))
    assert gate.stale_rule(record, Binding(sentinel, DIGEST)) == gate.RULE_STALE_DIFF


def test_blocking_issues_keeps_only_errors() -> None:
    info = _check(record=None, exempt=True)
    error = _check(record=None)
    assert gate.blocking_issues(info + error) == error
    assert gate.SEVERITY_ERROR == "error"


def test_refusal_message_is_the_one_message_table_text() -> None:
    message = gate.refusal_message(
        gate.RULE_OTHER_PLAN, PLAN_ID, path=PATH, other="plans/y.md"
    )
    assert message == _only_error(_check(make_record(plan="plans/y.md")))["message"]


def test_a_huge_single_line_observation_is_capped_in_the_refusal() -> None:
    rows = [make_row("AC1", "not-met", observation="x" * 200_000)]
    issue = _only_error(_check(make_record(overall="not-met", criteria=rows)))
    assert len(issue["message"]) < 2 * gate.OBSERVATION_CHAR_LIMIT
    assert "x" * gate.OBSERVATION_CHAR_LIMIT + "…" in issue["message"]


def test_an_observation_at_the_cap_is_shown_whole() -> None:
    observation = "y" * gate.OBSERVATION_CHAR_LIMIT
    rows = [make_row("AC1", "not-met", observation=observation)]
    issue = _only_error(_check(make_record(overall="not-met", criteria=rows)))
    assert observation in issue["message"]
    assert "…" not in issue["message"]


def test_a_criterion_id_that_is_not_ac_n_never_reaches_the_gloss() -> None:
    result = {"criteria": [{**make_row("AC9 extra"), "observation": "ok"}]}
    rows, problems = validate_rows(result, ["AC1"], ["run"])
    record = build_record(PLAN_ID, rows, [], problems, Binding("a" * 64, "d"), "agent")
    issue = _only_error(
        gate.check_acceptance_examination(
            PLAN_ID, record, PATH, Binding("a" * 64, "d"), False
        )
    )
    assert "AC9" not in issue["message"]
    assert "did not have the expected shape" in issue["message"]


def test_progress_guardian_and_the_cli_share_one_gate_module(tmp_path: Path) -> None:
    """One interpreter, both entry points imported: they call the same gate
    function, so a fix to the gate reaches `--pre-pr` and `status` alike."""
    scripts = REPO_ROOT / "plugins" / "dev-team" / "scripts"
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import progress_guardian, acceptance_examination; "
        "print(progress_guardian.load_and_check is "
        "acceptance_examination.examination_gate.load_and_check)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(scripts)],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env=git_env(tmp_path),
    )
    assert result.stdout.strip() == "True"


def test_base_refusal_message_is_not_the_malformed_result_message() -> None:
    message = gate.refusal_message(gate.RULE_BASE_UNRESOLVABLE, PLAN_ID)
    assert "branch base could not be resolved" in message
    assert "incomplete" not in message


def test_git_failure_is_reported_as_an_unresolvable_base_not_an_empty_diff(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_met_record(repo)
    real_run = subprocess.run

    def _run(argv, **kwargs):
        if "diff" in argv:
            return subprocess.CompletedProcess(argv, 128, stdout=b"", stderr=b"fatal")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _run)
    issue = _only_error(gate.load_and_check(repo / PLAN_ID))
    assert issue["rule_id"] == gate.RULE_BASE_UNRESOLVABLE
    assert "no commits ahead" not in issue["message"]


def test_record_path_that_is_a_directory_is_unreadable_not_a_traceback(
    repo: Path,
) -> None:
    path = write_met_record(repo)
    path.unlink()
    path.mkdir()
    issue = _only_error(gate.load_and_check(repo / PLAN_ID))
    assert issue["rule_id"] == gate.RULE_UNREADABLE
    assert "file could not be read" in issue["message"]


def test_met_record_with_a_stored_sentinel_against_a_real_hash_reports_stale_diff(
    repo: Path,
) -> None:
    write_met_record(repo, binding_hash=BASE_UNRESOLVABLE)
    issue = _only_error(gate.load_and_check(repo / PLAN_ID))
    assert issue["rule_id"] == gate.RULE_STALE_DIFF


def test_load_and_check_uses_a_supplied_binding_without_recomputing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_met_record(repo)
    current = gate.binding_for_plan(
        repo, PLAN_ID, (repo / PLAN_ID).read_text(encoding="utf-8")
    )

    def _unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("binding_for_plan was called")

    # double-waiver: B1 — binding_for_plan spawns git subprocesses; the spy proves none run
    monkeypatch.setattr(gate, "binding_for_plan", _unexpected)

    assert gate.load_and_check(repo / PLAN_ID, binding=current) == []


def test_record_with_a_non_object_criteria_row_is_unreadable(repo: Path) -> None:
    write_met_record(repo, criteria=[7])
    issue = _only_error(gate.load_and_check(repo / PLAN_ID))
    assert "invalid criteria" in issue["message"]
