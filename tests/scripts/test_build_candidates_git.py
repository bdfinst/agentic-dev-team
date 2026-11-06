"""Tests for the git-facing build_candidates.py subcommands (#2273): collect
and cleanup, against temporary repositories. The reconcile and lifecycle
scenarios live in test_build_candidates_integration.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from _build_candidates_test_helpers import (
    SCRIPTS_DIR,
    commit_all,
    git_output,
    init_repo,
    run_cli,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import build_candidates
import build_candidates_git

# --- reconcile timeout ------------------------------------------------------

TIMEOUT_ENV = "BUILD_WAVE_RECONCILE_TEST_CMD_TIMEOUT"
DEFAULT_SUITE_TIMEOUT = 1800
MARGIN = 300


def test_reconcile_timeout_defaults_to_the_suite_default_plus_the_margin(
    monkeypatch,
) -> None:
    monkeypatch.delenv(TIMEOUT_ENV, raising=False)
    assert build_candidates_git.reconcile_timeout_seconds() == (
        DEFAULT_SUITE_TIMEOUT + MARGIN
    )


def test_reconcile_timeout_follows_the_suite_timeout_variable(monkeypatch) -> None:
    monkeypatch.setenv(TIMEOUT_ENV, "10")
    assert build_candidates_git.reconcile_timeout_seconds() == 10 + MARGIN


@pytest.mark.parametrize("raw", ["", "soon"], ids=["empty", "not-a-number"])
def test_reconcile_timeout_ignores_an_unusable_suite_timeout_variable(
    monkeypatch, raw
) -> None:
    monkeypatch.setenv(TIMEOUT_ENV, raw)
    assert build_candidates_git.reconcile_timeout_seconds() == (
        DEFAULT_SUITE_TIMEOUT + MARGIN
    )


# --- collect ----------------------------------------------------------------

PLAN = """# Plan: demo

### Slice 1: First

```gherkin
Feature: one
  Scenario: only one here
```

### Slice 2: Second

```gherkin
Feature: two
  # Scenario: a comment is not a scenario
  Scenario: s1
  Scenario: s2
  Scenario: s3
  Scenario Outline: o1
```

#### Step 2.1: do it

### Slice 3: Third

**Depends-on:** none

#### Step 3.1: no gherkin here
"""

SCENARIOS_IN_SLICE_2 = 4
OLD_LINE_COUNT = 10
ADDED_LINES = 12
DELETED_LINES = 3
DIFF_LINES = ADDED_LINES + DELETED_LINES
COST_USD = 1.25
UNMET_SCENARIO_FINDINGS = 2
UNMET_CRITERION_FINDINGS = 1
UNMET_FINDINGS = UNMET_SCENARIO_FINDINGS + UNMET_CRITERION_FINDINGS
CORRECTNESS_ERRORS = 2
CORRECTNESS_WARNINGS = 1

OLD_LINES = [f"old {i}" for i in range(OLD_LINE_COUNT)]


@pytest.fixture
def candidate_repo(tmp_path):
    """A repo whose branch `cand` adds ADDED_LINES lines, deletes
    DELETED_LINES and adds a binary file in one commit on top of `main` (the
    base)."""
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "existing.txt").write_text("\n".join(OLD_LINES) + "\n", encoding="utf-8")
    commit_all(repo, "base")
    base = git_output(repo, "rev-parse", "HEAD")
    git_output(repo, "checkout", "-q", "-b", "cand")
    (repo / "added.txt").write_text(
        "".join(f"new {i}\n" for i in range(ADDED_LINES)), encoding="utf-8"
    )
    (repo / "existing.txt").write_text(
        "\n".join(OLD_LINES[:-DELETED_LINES]) + "\n", encoding="utf-8"
    )
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02\xff" * 64)
    commit_all(repo, "candidate work")
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN, encoding="utf-8")
    return {"repo": repo, "base": base, "plan": plan, "tmp": tmp_path}


def _lens(tmp_path, name: str, issues: list, status: str = "warn") -> str:
    path = tmp_path / name
    path.write_text(json.dumps({"status": status, "issues": issues}), encoding="utf-8")
    return str(path)


def _spec_issues(unmet_scenarios: int, unmet_criteria: int = 0) -> list:
    return (
        [{"category": "uncovered-scenario"}] * unmet_scenarios
        + [{"category": "unmet-criterion"}] * unmet_criteria
        + [{"category": "scope-violation"}]
    )


def _correctness_issues() -> list:
    return [{"severity": s} for s in ("error", "error", "warning", "suggestion")]


def _collect(
    fx,
    *,
    suite_exit="0",
    spec=None,
    correctness=None,
    step="2.1",
    plan=None,
    branch="cand",
):
    return run_cli(
        "collect",
        "--id",
        "2",
        f"--branch={branch}",
        "--worktree",
        str(fx["repo"]),
        f"--base={fx['base']}",
        f"--suite-exit={suite_exit}",
        "--spec-json",
        spec
        or _lens(
            fx["tmp"],
            "spec.json",
            _spec_issues(UNMET_SCENARIO_FINDINGS, UNMET_CRITERION_FINDINGS),
        ),
        "--correctness-json",
        correctness or _lens(fx["tmp"], "corr.json", _correctness_issues()),
        "--plan",
        str(plan or fx["plan"]),
        "--step",
        step,
        "--cost-usd",
        str(COST_USD),
    )


def test_collect_derives_every_count_from_files_and_the_worktree(
    candidate_repo,
) -> None:
    r = _collect(candidate_repo)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {
        "id": 2,
        "branch": "cand",
        "suite_green": True,
        "scenarios_total": SCENARIOS_IN_SLICE_2,
        "scenarios_unmet": UNMET_FINDINGS,
        "errors": CORRECTNESS_ERRORS,
        "warnings": CORRECTNESS_WARNINGS,
        "diff_lines": DIFF_LINES,
        "cost_usd": COST_USD,
        "screening": "ok",
    }


def test_collect_clamps_unmet_findings_to_the_scenario_count(candidate_repo) -> None:
    spec = _lens(candidate_repo["tmp"], "spec6.json", _spec_issues(6))
    out = json.loads(_collect(candidate_repo, spec=spec).stdout)
    assert out["scenarios_unmet"] == out["scenarios_total"] == SCENARIOS_IN_SLICE_2


def test_collect_keeps_a_clamped_candidate_rankable(candidate_repo) -> None:
    spec = _lens(candidate_repo["tmp"], "spec6.json", _spec_issues(6))
    r = _collect(candidate_repo, spec=spec)
    assert r.returncode == 0, r.stderr
    candidate = build_candidates.Candidate.from_dict(json.loads(r.stdout))
    assert not candidate.is_disqualified, candidate.disqualification_reason


def test_collect_rejects_an_empty_branch_for_a_green_suite(candidate_repo) -> None:
    r = _collect(candidate_repo, branch="")
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("collect:")
    assert "branch may be empty only when suite_green is false" in r.stderr


def test_collect_marks_an_unparseable_lens_and_zeroes_its_counts(
    candidate_repo,
) -> None:
    prose = candidate_repo["tmp"] / "prose.json"
    prose.write_text("The code looks fine to me.", encoding="utf-8")
    out = json.loads(_collect(candidate_repo, correctness=str(prose)).stdout)
    assert out["screening"] == "unparseable: correctness-review"
    assert (out["errors"], out["warnings"]) == (0, 0)


def test_collect_keeps_the_other_lens_counts_when_one_lens_is_unparseable(
    candidate_repo,
) -> None:
    prose = candidate_repo["tmp"] / "prose.json"
    prose.write_text("The code looks fine to me.", encoding="utf-8")
    out = json.loads(_collect(candidate_repo, correctness=str(prose)).stdout)
    assert out["scenarios_unmet"] == UNMET_FINDINGS


@pytest.mark.parametrize(
    "content",
    ['{"status": "pass"}', '{"issues": []}', '{"status": 1, "issues": []}', "[]"],
    ids=["no-issues", "no-status", "status-not-string", "root-list"],
)
def test_collect_treats_a_structurally_wrong_spec_lens_as_unparseable(
    candidate_repo, content
) -> None:
    path = candidate_repo["tmp"] / "spec-bad.json"
    path.write_text(content, encoding="utf-8")
    out = json.loads(_collect(candidate_repo, spec=str(path)).stdout)
    assert out["screening"] == "unparseable: spec-compliance-review"
    assert out["scenarios_unmet"] == 0


@pytest.mark.parametrize(
    "category",
    [["uncovered-scenario"], {}, None, 7],
    ids=["list", "dict", "null", "number"],
)
def test_collect_ignores_a_spec_issue_whose_category_is_not_a_string(
    candidate_repo, category
) -> None:
    spec = _lens(candidate_repo["tmp"], "spec-cat.json", [{"category": category}])
    r = _collect(candidate_repo, spec=spec)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["scenarios_unmet"] == 0


def test_collect_treats_a_missing_spec_lens_file_as_unparseable(candidate_repo) -> None:
    missing = str(candidate_repo["tmp"] / "nope.json")
    out = json.loads(_collect(candidate_repo, spec=missing).stdout)
    assert out["screening"] == "unparseable: spec-compliance-review"


def test_collect_reports_the_first_unparseable_lens_when_both_are_bad(
    candidate_repo,
) -> None:
    missing = str(candidate_repo["tmp"] / "nope.json")
    out = json.loads(_collect(candidate_repo, spec=missing, correctness=missing).stdout)
    assert out["screening"] == "unparseable: spec-compliance-review"


@pytest.mark.parametrize(
    "suite_exit,green",
    [("0", True), ("2", False), ("-1", False)],
    ids=["zero", "positive", "negative"],
)
def test_collect_counts_a_green_suite_only_for_exit_zero(
    candidate_repo, suite_exit, green
) -> None:
    r = _collect(candidate_repo, suite_exit=suite_exit)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["suite_green"] is green


def test_collect_rejects_a_non_integer_suite_exit_as_a_usage_error(
    candidate_repo,
) -> None:
    r = _collect(candidate_repo, suite_exit="x")
    assert (r.returncode, r.stdout) == (2, "")
    assert "argument --suite-exit:" in r.stderr


def test_collect_rejects_a_step_whose_slice_has_no_gherkin(candidate_repo) -> None:
    r = _collect(candidate_repo, step="3.1")
    assert (r.returncode, r.stdout) == (1, "")
    assert "slice 3 (step 3.1) has no gherkin block" in r.stderr


def test_collect_rejects_a_step_outside_any_slice(candidate_repo) -> None:
    r = _collect(candidate_repo, step="9.1")
    assert (r.returncode, r.stdout) == (1, "")
    assert "step 9.1 is outside any slice" in r.stderr


def test_collect_rejects_a_missing_plan_file(candidate_repo) -> None:
    r = _collect(candidate_repo, plan=candidate_repo["tmp"] / "no-plan.md")
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("collect: cannot read plan")


def test_collect_rejects_a_plan_that_is_not_utf8(candidate_repo) -> None:
    bad = candidate_repo["tmp"] / "latin1.md"
    bad.write_bytes(b"### Slice 1: caf\xe9\n")
    r = _collect(candidate_repo, plan=bad)
    assert (r.returncode, r.stdout) == (1, "")
    assert "is not valid UTF-8" in r.stderr


def test_collect_rejects_a_base_ref_that_does_not_exist(candidate_repo) -> None:
    r = _collect({**candidate_repo, "base": "no-such-ref"})
    assert (r.returncode, r.stdout) == (1, "")
    assert "base 'no-such-ref' is not a commit" in r.stderr


def test_collect_rejects_a_base_that_would_be_read_as_a_git_option(
    candidate_repo,
) -> None:
    target = candidate_repo["tmp"] / "written-by-git"
    r = _collect({**candidate_repo, "base": f"--output={target}"})
    assert (r.returncode, r.stdout) == (1, "")
    assert "base must not start with '-'" in r.stderr
    assert not target.exists()


def test_collect_rejects_a_malformed_step_as_a_usage_error(candidate_repo) -> None:
    r = _collect(candidate_repo, step="two")
    assert (r.returncode, r.stdout) == (2, "")
    assert "argument --step:" in r.stderr


def test_collect_ignores_uncommitted_edits_in_the_worktree(candidate_repo) -> None:
    (candidate_repo["repo"] / "added.txt").write_text("dirty\n", encoding="utf-8")
    assert json.loads(_collect(candidate_repo).stdout)["diff_lines"] == DIFF_LINES


def test_collect_counts_binary_files_as_zero_diff_lines(candidate_repo) -> None:
    repo = candidate_repo["repo"]
    (repo / "only-binary.bin").write_bytes(b"\x00\xfe" * 32)
    commit_all(repo, "binary only")
    base = git_output(repo, "rev-parse", "HEAD~1")
    out = json.loads(_collect({**candidate_repo, "base": base}).stdout)
    assert out["diff_lines"] == 0


# --- cleanup ----------------------------------------------------------------


@pytest.fixture
def cleanup_repo(tmp_path):
    """Repo on branch `build` with candidate branches c1 and c2 checked out in
    worktrees and an unrelated branch `keep` (also in a worktree)."""
    repo = tmp_path / "repo"
    init_repo(repo)
    git_output(repo, "checkout", "-q", "-b", "build")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    commit_all(repo, "base")
    paths = {}
    for name in ("c1", "c2", "keep"):
        paths[name] = tmp_path / f"wt-{name}"
        git_output(repo, "worktree", "add", "-q", "-b", name, str(paths[name]))
    return {"repo": repo, "paths": paths}


def _cleanup(fx, *branches: str, repo=None):
    return run_cli("cleanup", "--repo", str(repo or fx["repo"]), "--remove", *branches)


def _branches(repo) -> list[str]:
    return git_output(repo, "branch", "--format=%(refname:short)").splitlines()


def test_cleanup_removes_only_the_listed_branches(cleanup_repo) -> None:
    r = _cleanup(cleanup_repo, "c2", "c1")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"absent": [], "removed": ["c1", "c2"]}
    assert sorted(_branches(cleanup_repo["repo"])) == ["build", "keep"]


def test_cleanup_removes_the_worktrees_of_the_listed_branches_and_no_others(
    cleanup_repo,
) -> None:
    _cleanup(cleanup_repo, "c2", "c1")
    paths = cleanup_repo["paths"]
    assert (paths["c1"].exists(), paths["c2"].exists(), paths["keep"].exists()) == (
        False,
        False,
        True,
    )


def test_cleanup_second_run_is_a_no_op_listing_the_branches_as_absent(
    cleanup_repo,
) -> None:
    _cleanup(cleanup_repo, "c1", "c2")
    r = _cleanup(cleanup_repo, "c1", "c2")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"absent": ["c1", "c2"], "removed": []}


def test_cleanup_reports_a_mix_of_removed_and_absent_branches(cleanup_repo) -> None:
    r = _cleanup(cleanup_repo, "c1", "never-existed")
    assert json.loads(r.stdout) == {"absent": ["never-existed"], "removed": ["c1"]}


def test_cleanup_removes_a_worktree_holding_uncommitted_and_untracked_files(
    cleanup_repo,
) -> None:
    (cleanup_repo["paths"]["c1"] / "f.txt").write_text("dirty\n", encoding="utf-8")
    (cleanup_repo["paths"]["c1"] / "new.txt").write_text("new\n", encoding="utf-8")
    r = _cleanup(cleanup_repo, "c1")
    assert r.returncode == 0, r.stderr
    assert not cleanup_repo["paths"]["c1"].exists()


def test_cleanup_removes_a_branch_that_has_no_worktree(cleanup_repo) -> None:
    git_output(cleanup_repo["repo"], "branch", "loose")
    r = _cleanup(cleanup_repo, "loose")
    assert json.loads(r.stdout)["removed"] == ["loose"]


def _add_early_sorting_branch(fx) -> None:
    """A branch that sorts before `build`, so a missing refusal guard would
    remove it before git itself rejects `build`."""
    path = fx["repo"].parent / "wt-aaa"
    git_output(fx["repo"], "worktree", "add", "-q", "-b", "aaa", str(path))


def test_cleanup_refuses_the_current_branch_and_removes_nothing(cleanup_repo) -> None:
    _add_early_sorting_branch(cleanup_repo)
    r = _cleanup(cleanup_repo, "aaa", "build", "c1")
    assert (r.returncode, r.stdout) == (1, "")
    assert "refusing to remove 'build'" in r.stderr
    assert sorted(_branches(cleanup_repo["repo"])) == [
        "aaa",
        "build",
        "c1",
        "c2",
        "keep",
    ]
    assert cleanup_repo["paths"]["c1"].exists()


def test_cleanup_refuses_the_main_worktree_branch_when_run_from_a_worktree(
    cleanup_repo,
) -> None:
    _add_early_sorting_branch(cleanup_repo)
    r = _cleanup(cleanup_repo, "aaa", "build", repo=cleanup_repo["paths"]["c1"])
    assert (r.returncode, r.stdout) == (1, "")
    assert "refusing to remove 'build'" in r.stderr
    assert "aaa" in _branches(cleanup_repo["repo"])


def test_cleanup_refuses_the_branch_of_the_worktree_it_runs_from(cleanup_repo) -> None:
    _add_early_sorting_branch(cleanup_repo)
    r = _cleanup(cleanup_repo, "aaa", "c1", repo=cleanup_repo["paths"]["c1"])
    assert (r.returncode, r.stdout) == (1, "")
    assert "refusing to remove 'c1'" in r.stderr
    assert "aaa" in _branches(cleanup_repo["repo"])
    assert cleanup_repo["paths"]["c1"].exists()


def test_cleanup_names_the_branch_and_command_when_git_cannot_remove_a_worktree(
    cleanup_repo,
) -> None:
    git_output(
        cleanup_repo["repo"], "worktree", "lock", str(cleanup_repo["paths"]["c1"])
    )
    r = _cleanup(cleanup_repo, "c1", "c2")
    assert (r.returncode, r.stdout) == (1, "")
    assert "'c1'" in r.stderr
    assert "worktree remove" in r.stderr


def test_cleanup_keeps_the_earlier_removals_when_a_later_branch_fails(
    cleanup_repo,
) -> None:
    git_output(
        cleanup_repo["repo"], "worktree", "lock", str(cleanup_repo["paths"]["c2"])
    )
    r = _cleanup(cleanup_repo, "c1", "c2")
    branches = _branches(cleanup_repo["repo"])
    assert (r.returncode, r.stdout) == (1, "")
    assert "'c2'" in r.stderr
    assert "worktree remove" in r.stderr
    assert "c1" not in branches
    assert "c2" in branches


def test_cleanup_leaves_the_branch_in_place_when_its_worktree_cannot_be_removed(
    cleanup_repo,
) -> None:
    git_output(
        cleanup_repo["repo"], "worktree", "lock", str(cleanup_repo["paths"]["c1"])
    )
    _cleanup(cleanup_repo, "c1", "c2")
    assert "c1" in _branches(cleanup_repo["repo"])


def test_cleanup_requires_at_least_one_branch(cleanup_repo) -> None:
    r = run_cli("cleanup", "--repo", str(cleanup_repo["repo"]), "--remove")
    assert (r.returncode, r.stdout) == (2, "")
    assert "argument --remove:" in r.stderr


def test_cleanup_on_a_path_that_is_not_a_repository_exits_one(tmp_path) -> None:
    r = run_cli("cleanup", "--repo", str(tmp_path), "--remove", "c1")
    assert (r.returncode, r.stdout) == (1, "")
    assert r.stderr.startswith("cleanup:")


# --- _git and restore_branch failure paths (in-process) -----------------------


def _raising(exc):
    def run(*_args, **_kwargs):
        raise exc

    return run


@pytest.mark.parametrize(
    "exc",
    [OSError("no git"), subprocess.TimeoutExpired(cmd="git", timeout=1)],
    ids=["oserror", "timeout"],
)
def test_git_turns_a_failure_to_run_into_a_git_error(monkeypatch, exc) -> None:
    monkeypatch.setattr(build_candidates_git.subprocess, "run", _raising(exc))
    with pytest.raises(build_candidates_git.GitError, match="could not run in /repo"):
        build_candidates_git._git("/repo", "status")


def test_restore_branch_names_the_pre_merge_sha_when_git_cannot_run(
    monkeypatch,
) -> None:
    # double-waiver: B1 — _git wraps the git subprocess; here git cannot be run
    monkeypatch.setattr(
        build_candidates_git, "_git", _raising(build_candidates_git.GitError("down"))
    )
    with pytest.raises(
        build_candidates_git.RestoreFailedError, match="git reset --keep abc123"
    ):
        build_candidates_git.restore_branch("/repo", "abc123")


def test_git_path_raises_when_rev_parse_fails(monkeypatch) -> None:
    failed = SimpleNamespace(returncode=1, stdout="", stderr="fatal: not a repo")
    # double-waiver: B1 — _git wraps the git subprocess; here its rev-parse fails
    monkeypatch.setattr(build_candidates_git, "_git", lambda *_a: failed)
    with pytest.raises(build_candidates_git.GitError, match="fatal: not a repo"):
        build_candidates_git._git_path("/repo", "MERGE_HEAD")


class _Pipe:
    closed = False

    def close(self) -> None:
        self.closed = True


class _StuckProcess:
    """A killed process whose pipes a descendant outside the group still holds."""

    def __init__(self) -> None:
        self.stdout, self.stderr = _Pipe(), _Pipe()
        self.drain_timeouts: list[float | None] = []

    def communicate(self, timeout=None):
        self.drain_timeouts.append(timeout)
        raise subprocess.TimeoutExpired(cmd="stuck", timeout=timeout)


def test_kill_process_group_gives_up_on_pipes_an_escaped_descendant_holds(
    monkeypatch,
) -> None:
    # double-waiver: B1 — _signal_process_group wraps os.killpg on a process group
    monkeypatch.setattr(build_candidates_git, "_signal_process_group", lambda _p: None)
    process = _StuckProcess()
    drained = build_candidates_git._kill_process_group(process)
    assert process.drain_timeouts == [build_candidates_git._KILL_DRAIN_SECONDS]
    assert (process.stdout.closed, process.stderr.closed) == (True, True)
    assert drained == ""


def test_signal_process_group_treats_a_permission_error_as_already_gone(
    monkeypatch,
) -> None:
    """Darwin reports EPERM for a group that holds only zombies."""
    monkeypatch.setattr(
        os, "killpg", _raising(PermissionError("zombie group")), raising=False
    )
    build_candidates_git._signal_process_group(SimpleNamespace(pid=1))


def test_signal_process_group_treats_a_missing_group_as_already_gone(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        os, "killpg", _raising(ProcessLookupError("gone")), raising=False
    )
    build_candidates_git._signal_process_group(SimpleNamespace(pid=1))
