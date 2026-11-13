"""Records behind ``measured`` baselines, and private paths in any committed baseline file.

The rules are in ``_benefit_baseline_rules.py``; the record tests share one throwaway git repository for the
module and take a fresh records directory each.
"""

from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import pytest
from _benefit_baseline_builders import (
    RECORD_CHECKS,
    assert_clean,
    assert_rejected,
    ctx_for,
    good_entries,
    with_baseline,
)
from _benefit_baseline_rules import (
    COMMON_RECORD_FIELDS,
    METRIC_RECORD_FIELDS,
    PBT,
    RECORDS_DIR,
    TR_TP,
    Context,
    check_measured_cells,
    check_no_private_paths,
    check_records,
    current_usernames,
    problems_for,
    run_checks,
)
from lane_fixtures import commit_file, git

MISSING = object()  # an override value that removes the field
UNKNOWN_SHA = "1" * 40  # a well-formed commit id that no repository holds

# --- records ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def git_root(tmp_path_factory):
    """One throwaway git repository with two commits, shared by every record test in this module."""
    root = tmp_path_factory.mktemp("baseline-repo")
    git(root, "init", "-q", "-b", "main")
    parent = commit_file(root, "a.txt", "a\n", "first")
    head = commit_file(root, "a.txt", "b\n", "second")
    return SimpleNamespace(root=root, head=head, parent=parent)


@pytest.fixture
def repo(git_root):
    """The shared repository with a fresh, empty records directory for this test."""
    records = git_root.root / RECORDS_DIR
    records.mkdir(parents=True)
    yield git_root
    shutil.rmtree(records)


def record_cell(metric_id: str) -> str:
    return f"measured: replayed value in {RECORDS_DIR}/benefit-{metric_id}.json"


def measured_ctx(repo, *metric_ids: str) -> Context:
    entries = good_entries()
    for metric_id in metric_ids:
        entries[metric_id]["baseline"] = record_cell(metric_id)
    return ctx_for(entries, repo_root=repo.root)


def build_record(repo, metric_id: str, **overrides) -> dict:
    """A valid record for the metric; an override of MISSING removes that field."""
    record = {
        "command": "python3 scripts/replay.py --target one",
        "inputs": ["scripts/replay.py"],
        "commit": repo.head,
        "date": "2026-11-13",
        "value": 12,
        "n": good_entries()[metric_id]["minimum_n"],
    }
    if metric_id == PBT:
        record |= {"generated_properties": False, "target_ids": ["one"]}
    if metric_id == TR_TP:
        record |= {
            "commit": repo.parent,
            "introduced_by_sha": repo.head,
            "fixture_ids": ["tr-1"],
        }
    record |= overrides
    return {key: value for key, value in record.items() if value is not MISSING}


def write_record(repo, metric_id: str, record: dict | str, filename: str | None = None):
    path = repo.root / RECORDS_DIR / (filename or f"benefit-{metric_id}.json")
    path.write_text(
        record if isinstance(record, str) else json.dumps(record, indent=2) + "\n"
    )
    return path


def write_pbt_record(repo, **overrides):
    return write_record(repo, PBT, build_record(repo, PBT, **overrides))


def problems_after_writing(repo, metric_id: str = PBT, **overrides) -> list[str]:
    """Write the metric's record with `overrides`, then run the cell and record rules over a measured cell."""
    write_record(repo, metric_id, build_record(repo, metric_id, **overrides))
    return problems_for(measured_ctx(repo, metric_id), *RECORD_CHECKS)


def record_problem_prefix(metric_id: str = PBT) -> str:
    return f"benefit-{metric_id}.json:"


@pytest.mark.parametrize("metric_id", sorted(METRIC_RECORD_FIELDS))
def test_a_complete_record_for_a_measured_metric_is_accepted(repo, metric_id):
    assert problems_after_writing(repo, metric_id) == []


def test_a_record_with_trailing_whitespace_is_accepted(repo):
    write_record(repo, PBT, json.dumps(build_record(repo, PBT)) + "\n\n  \n")
    assert_clean(measured_ctx(repo, PBT), *RECORD_CHECKS)


def test_a_measured_metric_without_its_record_is_rejected_naming_the_record(repo):
    assert_rejected(
        measured_ctx(repo, PBT),
        *RECORD_CHECKS,
        starts=f"{PBT}:",
        has=(f"{RECORDS_DIR}/benefit-{PBT}.json is missing",),
    )


def test_a_measured_cell_in_a_context_with_no_repository_root_is_rejected_naming_the_metric():
    ctx = with_baseline(PBT, record_cell(PBT))
    assert_rejected(
        ctx,
        check_measured_cells,
        starts=f"{PBT}: measured cells cannot be checked",
        has=("no repository root",),
    )


def test_a_context_with_no_repository_root_and_no_measured_cell_is_accepted():
    assert_clean(ctx_for(), check_measured_cells)


def test_a_no_reference_metric_needs_no_record(repo):
    assert_clean(ctx_for(repo_root=repo.root), *RECORD_CHECKS)


def test_a_measured_cell_citing_a_missing_path_is_rejected_naming_metric_and_path(repo):
    write_pbt_record(repo)
    cited = f"{RECORDS_DIR}/benefit-elsewhere.json"
    ctx = with_baseline(PBT, f"measured: see {cited}", repo_root=repo.root)
    assert_rejected(
        ctx,
        *RECORD_CHECKS,
        starts=f"{PBT}.baseline: cites {cited}",
        has=("does not exist",),
    )


def test_a_measured_cell_citing_no_record_path_is_rejected(repo):
    write_pbt_record(repo)
    ctx = with_baseline(PBT, "measured: replayed, no path given", repo_root=repo.root)
    assert_rejected(
        ctx, *RECORD_CHECKS, starts=f"{PBT}.baseline: measured cell cites no path"
    )


@pytest.mark.parametrize(
    "ending", ["/", "."], ids=["trailing-slash", "sentence-period"]
)
def test_a_cited_record_path_can_end_in_punctuation(repo, ending):
    write_pbt_record(repo)
    ctx = with_baseline(
        PBT,
        f"measured: see {RECORDS_DIR}/benefit-{PBT}.json{ending}",
        repo_root=repo.root,
    )
    assert_clean(ctx, *RECORD_CHECKS)


@pytest.mark.parametrize("defect", ["missing", "null"])
@pytest.mark.parametrize(
    ("metric_id", "field_name"),
    [
        (m, f)
        for m in sorted(METRIC_RECORD_FIELDS)
        for f in (*COMMON_RECORD_FIELDS, *METRIC_RECORD_FIELDS[m])
    ],
)
def test_a_record_with_a_missing_or_null_field_is_rejected_naming_record_and_field(
    repo, metric_id, field_name, defect
):
    problems = problems_after_writing(
        repo, metric_id, **{field_name: MISSING if defect == "missing" else None}
    )
    assert any(
        p.startswith(
            f"{record_problem_prefix(metric_id)} field {field_name!r} is {defect}"
        )
        for p in problems
    ), problems


@pytest.mark.parametrize(
    ("metric_id", "field_name", "bad_value"),
    [
        (PBT, "command", 7),
        (PBT, "inputs", "scripts/replay.py"),
        (PBT, "inputs", ["/etc/hosts"]),
        (PBT, "commit", "abc123"),
        (PBT, "date", "13/11/2026"),
        (PBT, "value", True),
        (PBT, "value", "12"),
        (PBT, "generated_properties", True),
        (PBT, "generated_properties", "false"),
        (PBT, "target_ids", [1]),
        (TR_TP, "introduced_by_sha", "abc123"),
        (TR_TP, "fixture_ids", [1]),
    ],
)
def test_a_record_field_of_the_wrong_type_is_rejected_naming_record_and_field(
    repo, metric_id, field_name, bad_value
):
    problems = problems_after_writing(repo, metric_id, **{field_name: bad_value})
    assert any(
        p.startswith(f"{record_problem_prefix(metric_id)} field {field_name!r}")
        and ", expected " in p
        for p in problems
    ), problems


@pytest.mark.parametrize(
    "bad_n", [-1, 2.5, "10", True], ids=["negative", "fraction", "string", "bool"]
)
def test_a_record_with_an_invalid_n_is_rejected_naming_record_and_field(repo, bad_n):
    problems = problems_after_writing(repo, n=bad_n)
    assert any(
        p.startswith(f"{record_problem_prefix()} field 'n'")
        and "expected an integer >= 0" in p
        for p in problems
    ), problems


@pytest.mark.parametrize("metric_id", [PBT, "findings-parity"])
def test_n_below_minimum_n_is_rejected_and_n_at_minimum_n_is_accepted(repo, metric_id):
    minimum_n = good_entries()[metric_id]["minimum_n"]
    problems = problems_after_writing(repo, metric_id, n=minimum_n - 1)
    assert any(
        p.startswith(f"{record_problem_prefix(metric_id)} field 'n'")
        and f"below minimum_n {minimum_n}" in p
        for p in problems
    ), problems
    assert problems_after_writing(repo, metric_id, n=minimum_n) == []


def test_minimum_n_is_read_from_the_pre_registration_entry(repo):
    write_pbt_record(repo, n=39)
    ctx = measured_ctx(repo, PBT)
    ctx.entries[PBT]["minimum_n"] = 40
    assert_rejected(
        ctx, *RECORD_CHECKS, starts=record_problem_prefix(), has=("below minimum_n 40",)
    )


def test_an_unparseable_record_is_rejected_naming_the_record(repo):
    write_record(repo, PBT, "{not json")
    assert_rejected(
        measured_ctx(repo, PBT),
        *RECORD_CHECKS,
        starts=f"{record_problem_prefix()} unparseable record",
    )


def test_a_record_that_is_not_a_json_object_is_rejected(repo):
    write_record(repo, PBT, "[1, 2]")
    assert_rejected(
        measured_ctx(repo, PBT),
        *RECORD_CHECKS,
        starts=f"{record_problem_prefix()} record is not a JSON object",
    )


def test_a_record_that_carries_a_status_field_is_rejected_naming_the_field(repo):
    problems = problems_after_writing(repo, status="measured")
    assert any(
        p.startswith(f"{record_problem_prefix()} field 'status'") for p in problems
    ), problems


@pytest.mark.parametrize(
    "filename", ["benefit-unregistered.json", "benefit-unregistered.JSON"]
)
def test_a_record_for_an_unregistered_id_is_rejected_naming_the_file(repo, filename):
    write_record(repo, "unregistered", build_record(repo, PBT), filename)
    assert_rejected(
        ctx_for(repo_root=repo.root),
        check_records,
        starts=f"{filename}: id 'unregistered' is not",
    )


def test_a_record_for_a_metric_that_is_not_measured_is_rejected_naming_the_file(repo):
    write_pbt_record(repo)
    assert_rejected(
        ctx_for(repo_root=repo.root),
        check_records,
        starts=f"{record_problem_prefix()} stray record",
    )


def test_files_that_are_not_benefit_records_are_ignored(repo):
    write_record(repo, "other", "{not json", "bash-failure-taxonomy-2026-08-27.json")
    assert_clean(ctx_for(repo_root=repo.root), check_records, check_no_private_paths)


def test_a_record_commit_that_does_not_resolve_is_rejected_in_a_full_repository(repo):
    write_pbt_record(repo, commit=UNKNOWN_SHA)
    findings = run_checks(measured_ctx(repo, PBT), *RECORD_CHECKS)
    assert any(
        p.startswith(f"{record_problem_prefix()} field 'commit' ")
        for p in findings.problems
    )
    assert findings.skips == []


@pytest.fixture
def shallow_repo(repo, tmp_path):
    """A depth-1 clone of the shared repository: it holds the head commit and not its parent."""
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo.root}", str(clone))
    (clone / RECORDS_DIR).mkdir(parents=True)
    return SimpleNamespace(root=clone, head=repo.head, parent=repo.parent)


def test_a_record_commit_absent_from_a_shallow_repository_is_skipped_with_a_named_reason(
    shallow_repo,
):
    write_pbt_record(shallow_repo, commit=UNKNOWN_SHA)
    findings = run_checks(measured_ctx(shallow_repo, PBT), *RECORD_CHECKS)
    assert findings.problems == []
    assert any("shallow" in skip for skip in findings.skips)


def test_an_introducing_commit_whose_parent_is_absent_from_a_shallow_repository_is_skipped(
    shallow_repo,
):
    write_record(shallow_repo, TR_TP, build_record(shallow_repo, TR_TP))
    findings = run_checks(measured_ctx(shallow_repo, TR_TP), *RECORD_CHECKS)
    assert findings.problems == []
    assert any(
        "parent check skipped; its parent is absent" in skip for skip in findings.skips
    )


def test_an_unresolved_introducing_commit_is_a_problem_and_not_a_skip_in_a_full_repository(
    repo,
):
    write_record(repo, TR_TP, build_record(repo, TR_TP, introduced_by_sha=UNKNOWN_SHA))
    findings = run_checks(measured_ctx(repo, TR_TP), *RECORD_CHECKS)
    assert any(
        p.startswith(f"{record_problem_prefix(TR_TP)} field 'introduced_by_sha' ")
        for p in findings.problems
    )
    assert findings.skips == []


def test_an_unresolved_introducing_commit_in_a_shallow_repository_skips_its_parent_check(
    shallow_repo,
):
    write_record(
        shallow_repo,
        TR_TP,
        build_record(
            shallow_repo, TR_TP, introduced_by_sha=UNKNOWN_SHA, commit=shallow_repo.head
        ),
    )
    findings = run_checks(measured_ctx(shallow_repo, TR_TP), *RECORD_CHECKS)
    assert findings.problems == []
    assert any(
        "introduced_by_sha parent check skipped; the commit is absent" in skip
        for skip in findings.skips
    )


def test_introduced_by_sha_whose_parent_is_not_the_commit_is_rejected(repo):
    problems = problems_after_writing(repo, TR_TP, commit=repo.head)
    assert any(
        p.startswith(f"{record_problem_prefix(TR_TP)} field 'commit' is not the parent")
        for p in problems
    ), problems


# --- private paths and user names ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "/Users/someone/work/file.json",
        "see /home/someone/file",
        "/private/var/folders/x",
        "/var/folders/ab/T/scratch",
        "run in /tmp/scratch/x",
        "/root/.config/x",
        "C:\\Users\\someone\\file",
        "/USERS/someone/file",
        ".claude/projects/abc",
        "file:///Users/someone/x",
        "file:///tmp/x",
        "/private/tmp/x",
    ],
    ids=[
        "users",
        "home",
        "private-var",
        "var-folders",
        "tmp",
        "root-home",
        "windows-users",
        "upper-case",
        "transcript",
        "file-url-users",
        "file-url-tmp",
        "private-tmp",
    ],
)
def test_a_baseline_cell_with_an_absolute_or_transcript_path_is_rejected_naming_metric_and_field(
    text,
):
    ctx = with_baseline("skip-rate", f"by-definition: reference at {text}")
    assert_rejected(
        ctx,
        check_no_private_paths,
        starts="skip-rate.baseline: contains the absolute or transcript path",
    )


def test_a_repo_relative_path_with_a_directory_named_users_is_accepted():
    ctx = with_baseline(
        "skip-rate",
        "by-definition: reference in docs/users/guide.md, src/home/x, tools/tmp/y and docs/root/z",
    )
    assert_clean(ctx, check_no_private_paths)


def test_an_absolute_path_in_the_document_prose_is_rejected_naming_the_line(tmp_path):
    ctx = ctx_for(doc_text="fine\nrun /Users/someone/tool\n", repo_root=tmp_path)
    assert_rejected(
        ctx,
        check_no_private_paths,
        starts="preregistration line 2: contains the absolute or transcript path",
    )


def test_a_record_field_with_an_absolute_path_is_rejected_naming_record_and_field(repo):
    write_pbt_record(repo, inputs=["/Users/someone/repo/file.py"])
    assert_rejected(
        ctx_for(repo_root=repo.root),
        check_no_private_paths,
        starts=f"{record_problem_prefix()} field 'inputs' contains the absolute",
    )


def test_an_unparseable_record_is_still_scanned_for_private_paths(repo):
    write_record(repo, PBT, "{ /Users/someone/x")
    assert_rejected(
        ctx_for(repo_root=repo.root),
        check_no_private_paths,
        starts=f"{record_problem_prefix()} field '(file)' contains the absolute",
    )


def test_a_record_path_that_cannot_be_read_is_reported_by_the_record_rule_and_skipped_by_the_path_scan(
    repo,
):
    (repo.root / RECORDS_DIR / f"benefit-{PBT}.json").mkdir()
    ctx = measured_ctx(repo, PBT)
    assert_clean(ctx, check_no_private_paths)
    assert_rejected(
        ctx, check_records, starts=f"{record_problem_prefix()} unparseable record"
    )


def test_the_user_name_of_the_person_running_the_test_is_rejected_without_being_stored_in_the_test():
    name = "synthetic-operator"
    ctx = with_baseline(
        "skip-rate", f"by-definition: measured by {name.upper()}", usernames=(name,)
    )
    assert_rejected(
        ctx,
        check_no_private_paths,
        starts="skip-rate.baseline: contains the user name of the person running the test",
    )
    assert (
        name.lower() not in "\n".join(problems_for(ctx, check_no_private_paths)).lower()
    )


def test_a_user_name_inside_a_longer_word_is_accepted():
    ctx = with_baseline(
        "skip-rate",
        "by-definition: the carols collection covers it",
        usernames=("carol",),
    )
    assert_clean(ctx, check_no_private_paths)


@pytest.mark.parametrize(
    ("os_user", "git_user", "expected"),
    [
        ("ab", "xy", []),
        ("abc", "xyz", ["abc", "xyz"]),
        ("os-user", "Git User", ["os-user", "Git User"]),
        ("os-user", "", ["os-user"]),
    ],
    ids=["too-short", "exactly-three", "both-names", "unset-git-name"],
)
def test_current_usernames_keeps_the_names_of_three_or_more_characters(
    os_user, git_user, expected
):
    assert (
        current_usernames(getuser=lambda: os_user, git_name=lambda: git_user)
        == expected
    )


@pytest.mark.parametrize(
    "error", [OSError("no such user"), KeyError("uid")], ids=["os-error", "key-error"]
)
def test_current_usernames_survives_an_os_user_that_cannot_be_read(error):
    def failing_getuser():
        raise error

    assert current_usernames(getuser=failing_getuser, git_name=lambda: "Git User") == [
        "Git User"
    ]


@pytest.mark.parametrize(
    ("os_user", "git_user"),
    [("runner", "Admin"), ("UBUNTU", "builder"), ("Root", "test"), ("user", "ci")],
    ids=["runner-admin", "ubuntu-builder", "root-test", "user-ci"],
)
def test_current_usernames_leaves_out_generic_account_names_in_any_case(
    os_user, git_user
):
    assert current_usernames(getuser=lambda: os_user, git_name=lambda: git_user) == []


def test_current_usernames_keeps_a_real_name_beside_a_generic_account():
    assert current_usernames(
        getuser=lambda: "runner", git_name=lambda: "Carol Diaz"
    ) == ["Carol Diaz"]
