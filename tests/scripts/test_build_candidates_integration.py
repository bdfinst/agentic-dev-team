"""Integration tests for build_candidates.py (#2273) against temporary git
repositories: reconcile (merge, suite gate, branch restore) and, with
rank and cleanup, the whole candidate lifecycle. build_wave_reconcile.py runs
for real through the `reconcile` subcommand.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from _build_candidates_test_helpers import (
    SCRIPTS_DIR,
    apply_hermetic_env,
    commit_all,
    git_output,
    init_repo,
    make_candidate,
    python_command,
    run_cli,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import build_candidates

BUILD = "build"
SUITE_PASSES = python_command("pass")
SUITE_FAILS = python_command("raise SystemExit(1)")


def _candidate_branch(repo, name: str, base: str, files: dict[str, str | None]) -> None:
    """Create branch `name` from `base` with one commit that writes the given
    files (None deletes), then return to the build branch."""
    git_output(repo, "checkout", "-q", "-b", name, base)
    for rel, content in files.items():
        if content is None:
            (repo / rel).unlink()
        else:
            (repo / rel).write_text(content, encoding="utf-8")
    commit_all(repo, f"{name} work")
    git_output(repo, "checkout", "-q", BUILD)


@pytest.fixture(autouse=True)
def _hermetic_git_for_in_process_calls(monkeypatch) -> None:
    """`restore_branch` is exercised in-process below; its git calls must see
    the same hermetic environment the subprocess helpers use."""
    apply_hermetic_env(monkeypatch)


@pytest.fixture
def build_repo(tmp_path):
    """Repo on branch `build`: tracked.txt, shared.txt, gone.txt committed as
    the base, then one more build commit (`pre`) that rewrites shared.txt."""
    repo = tmp_path / "repo"
    init_repo(repo)
    git_output(repo, "checkout", "-q", "-b", BUILD)
    for name in ("tracked.txt", "shared.txt", "gone.txt"):
        (repo / name).write_text("base\n", encoding="utf-8")
    commit_all(repo, "base")
    base = git_output(repo, "rev-parse", "HEAD")
    (repo / "shared.txt").write_text("build side\n", encoding="utf-8")
    commit_all(repo, "build moves on")
    return {"repo": repo, "base": base, "pre": git_output(repo, "rev-parse", "HEAD")}


def _reconcile(fx, branch: str, test_cmd: str):
    return run_cli(
        "reconcile",
        "--repo",
        str(fx["repo"]),
        "--into",
        BUILD,
        "--base",
        fx["base"],
        "--test-cmd",
        test_cmd,
        branch,
    )


def _files_in_head(repo) -> set[str]:
    return set(git_output(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())


def _head(repo) -> str:
    return git_output(repo, "rev-parse", "HEAD")


def _merge_head(repo):
    return repo / ".git" / "MERGE_HEAD"


def test_reconcile_restores_the_build_branch_when_the_suite_fails_after_the_merge(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    r = _reconcile(build_repo, "c1", SUITE_FAILS)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert (out["merged"], out["pre_merge_sha"]) == (False, build_repo["pre"])
    assert _head(repo) == build_repo["pre"]
    assert not _merge_head(repo).exists()


def test_reconcile_keeps_uncommitted_edits_when_it_restores_the_branch(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    (repo / "tracked.txt").write_text("uncommitted plan edit\n", encoding="utf-8")
    _reconcile(build_repo, "c1", SUITE_FAILS)
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == (
        "uncommitted plan edit\n"
    )


def test_reconcile_merges_the_next_candidate_after_a_failed_one(build_repo) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    _candidate_branch(repo, "c2", build_repo["base"], {"c2.txt": "c2\n"})
    _reconcile(build_repo, "c1", SUITE_FAILS)
    r = _reconcile(build_repo, "c2", SUITE_PASSES)
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (0, True)
    assert out["head"] == _head(repo)
    assert "c2.txt" in _files_in_head(repo)
    assert "c1.txt" not in _files_in_head(repo)


def test_reconcile_reports_a_merge_conflict_without_running_the_suite(
    build_repo, tmp_path
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c3", build_repo["base"], {"shared.txt": "c3 side\n"})
    marker = tmp_path / "suite-ran"
    suite = python_command(f"import pathlib; pathlib.Path({str(marker)!r}).touch()")
    r = _reconcile(build_repo, "c3", suite)
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (1, False)
    assert _head(repo) == build_repo["pre"]
    assert "shared.txt" in r.stderr
    assert not marker.exists()
    assert not _merge_head(repo).exists()


def test_reconcile_exits_two_naming_the_pre_merge_sha_when_the_restore_fails(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    pre = build_repo["pre"]
    _candidate_branch(repo, "c4", build_repo["base"], {"gone.txt": None})
    suite = python_command(
        "import pathlib; pathlib.Path('gone.txt').write_text('x'); raise SystemExit(1)"
    )
    r = _reconcile(build_repo, "c4", suite)
    assert (r.returncode, r.stdout) == (2, "")
    assert f"git reset --keep {pre}" in r.stderr
    assert _head(repo) != pre


def test_reconcile_merged_result_names_branch_head_and_pre_merge_sha(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    out = json.loads(_reconcile(build_repo, "c1", SUITE_PASSES).stdout)
    assert out == {
        "branch": "c1",
        "head": _head(repo),
        "merged": True,
        "pre_merge_sha": build_repo["pre"],
    }


def test_reconcile_refuses_a_worktree_that_is_not_on_the_build_branch(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    git_output(repo, "checkout", "-q", "c1")
    r = _reconcile(build_repo, "c1", SUITE_PASSES)
    assert (r.returncode, r.stdout) == (1, "")
    assert "not on build branch 'build'" in r.stderr
    assert git_output(repo, "rev-parse", "--abbrev-ref", "HEAD") == "c1"


def test_reconcile_reports_not_merged_for_a_branch_that_does_not_exist(
    build_repo,
) -> None:
    r = _reconcile(build_repo, "no-such-branch", SUITE_PASSES)
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (1, False)
    assert _head(build_repo["repo"]) == build_repo["pre"]


def test_reconcile_keeps_a_local_edit_the_merge_would_overwrite(build_repo) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"tracked.txt": "c1 side\n"})
    (repo / "tracked.txt").write_text("uncommitted plan edit\n", encoding="utf-8")
    r = _reconcile(build_repo, "c1", SUITE_PASSES)
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (1, False)
    assert _head(repo) == build_repo["pre"]
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == (
        "uncommitted plan edit\n"
    )


# --- restore_branch (the public seam of reconcile's recovery) ---------------


def _start_conflicting_merge(fx) -> None:
    """Leave `fx['repo']` in the middle of a conflicted merge of c3."""
    repo = fx["repo"]
    _candidate_branch(repo, "c3", fx["base"], {"shared.txt": "c3 side\n"})
    with pytest.raises(subprocess.CalledProcessError):  # the conflict is the setup
        git_output(repo, "merge", "--no-edit", "c3")
    assert _merge_head(repo).exists()


def test_restore_aborts_a_merge_left_in_progress_before_resetting(build_repo) -> None:
    """A merge can be left half-done when the reconcile script dies mid-merge
    (for example on its timeout); `reset --keep` alone refuses unmerged paths."""
    repo = build_repo["repo"]
    _start_conflicting_merge(build_repo)
    build_candidates.restore_branch(str(repo), build_repo["pre"])
    assert not _merge_head(repo).exists()
    assert _head(repo) == build_repo["pre"]


def test_restore_fails_when_the_merge_cannot_be_aborted_even_though_head_is_unmoved(
    build_repo,
) -> None:
    """A conflicted merge never moves HEAD, so HEAD == pre alone would
    report a restore that did not happen."""
    repo = build_repo["repo"]
    _start_conflicting_merge(build_repo)
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    with pytest.raises(build_candidates.RestoreFailedError, match="git reset --keep"):
        build_candidates.restore_branch(str(repo), build_repo["pre"])


def test_restore_fails_when_a_conflict_free_merge_cannot_be_aborted(build_repo) -> None:
    """No unmerged path to give the failure away: only the merge still being
    in progress shows the branch was not restored."""
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    git_output(repo, "merge", "--no-ff", "--no-commit", "c1")
    assert _merge_head(repo).exists()
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    with pytest.raises(build_candidates.RestoreFailedError):
        build_candidates.restore_branch(str(repo), build_repo["pre"])


def test_restore_fails_when_unmerged_paths_remain_without_a_merge_in_progress(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    blob = git_output(repo, "rev-parse", "HEAD:tracked.txt")
    stages = "".join(f"100644 {blob} {stage}\ttracked.txt\n" for stage in (1, 2, 3))
    git_output(repo, "update-index", "--index-info", stdin=stages)
    assert git_output(repo, "diff", "--name-only", "--diff-filter=U") == "tracked.txt"
    with pytest.raises(build_candidates.RestoreFailedError):
        build_candidates.restore_branch(str(repo), build_repo["pre"])


def test_restore_names_the_pre_merge_sha_in_the_failure_message(build_repo) -> None:
    repo = build_repo["repo"]
    _start_conflicting_merge(build_repo)
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    with pytest.raises(build_candidates.RestoreFailedError) as raised:
        build_candidates.restore_branch(str(repo), build_repo["pre"])
    assert build_repo["pre"] in str(raised.value)


# --- lifecycle --------------------------------------------------------------


def _worktree_candidate(repo, tmp_path, candidate_id: int, base: str) -> str:
    """Create candidate `candidate_id` on its own worktree branch with one
    commit that adds `cand<id>.txt`; return the branch name."""
    branch = f"cand-{candidate_id}"
    path = tmp_path / f"wt-{candidate_id}"
    git_output(repo, "worktree", "add", "-q", "-b", branch, str(path), base)
    (path / f"cand{candidate_id}.txt").write_text(
        f"candidate {candidate_id}\n", encoding="utf-8"
    )
    commit_all(path, f"candidate {candidate_id} work")
    return branch


def test_the_whole_lifecycle_merges_the_winner_and_leaves_the_repository_clean(
    build_repo, tmp_path
) -> None:
    repo = build_repo["repo"]
    branches = {
        i: _worktree_candidate(repo, tmp_path, i, build_repo["base"]) for i in (1, 2)
    }
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "candidates": [
                    make_candidate(1, met=3, branch=branches[1], diff_lines=1),
                    make_candidate(2, met=5, branch=branches[2], diff_lines=1),
                ]
            }
        ),
        encoding="utf-8",
    )

    ranked_run = run_cli("rank", "--candidates-json", str(candidates))
    assert ranked_run.returncode == 0, ranked_run.stderr
    ranked = json.loads(ranked_run.stdout)
    assert ranked["winner"] == 2, "the candidate meeting more scenarios must win"

    merged = _reconcile(build_repo, branches[ranked["winner"]], SUITE_PASSES)
    assert merged.returncode == 0, merged.stderr
    assert json.loads(merged.stdout)["merged"] is True
    assert "cand2.txt" in _files_in_head(repo), (
        "the winner's work is on the build branch"
    )
    assert "cand1.txt" not in _files_in_head(repo), "the loser's work is not"

    cleaned = run_cli(
        "cleanup", "--repo", str(repo), "--remove", branches[1], branches[2]
    )
    assert cleaned.returncode == 0, cleaned.stderr
    assert json.loads(cleaned.stdout) == {
        "absent": [],
        "removed": [branches[1], branches[2]],
    }

    worktrees = [
        line
        for line in git_output(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]
    assert len(worktrees) == 1, "only the build worktree remains"
    assert git_output(repo, "branch", "--format=%(refname:short)").split() == [BUILD]
    assert git_output(repo, "status", "--porcelain") == "", "the tree is clean"
