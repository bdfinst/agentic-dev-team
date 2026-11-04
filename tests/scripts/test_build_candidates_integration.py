"""Integration tests for build_candidates.py (#2273) against temporary git
repositories: reconcile (merge, suite gate, branch restore) and, with
cleanup, the whole candidate lifecycle. build_wave_reconcile.py runs for real
through the `reconcile` subcommand.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from test_build_candidates import _commit_all, _git, _init_repo, _run

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import build_candidates

BUILD = "build"


def _candidate_branch(repo, name: str, base: str, files: dict[str, str | None]) -> None:
    """Create branch `name` from `base` with one commit that writes the given
    files (None deletes), then return to the build branch."""
    _git(repo, "checkout", "-q", "-b", name, base)
    for rel, content in files.items():
        if content is None:
            (repo / rel).unlink()
        else:
            (repo / rel).write_text(content, encoding="utf-8")
    _commit_all(repo, f"{name} work")
    _git(repo, "checkout", "-q", BUILD)


@pytest.fixture
def build_repo(tmp_path):
    """Repo on branch `build`: tracked.txt, shared.txt, gone.txt committed as
    the base, then one more build commit (`pre`) that rewrites shared.txt."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "checkout", "-q", "-b", BUILD)
    for name in ("tracked.txt", "shared.txt", "gone.txt"):
        (repo / name).write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "shared.txt").write_text("build side\n", encoding="utf-8")
    _commit_all(repo, "build moves on")
    return {"repo": repo, "base": base, "pre": _git(repo, "rev-parse", "HEAD")}


def _reconcile(fx, branch: str, test_cmd: str):
    return _run(
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
    return set(_git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())


def test_reconcile_restores_the_build_branch_when_the_suite_fails_after_the_merge(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    r = _reconcile(build_repo, "c1", "false")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert (out["merged"], out["pre_merge_sha"]) == (False, build_repo["pre"])
    assert _git(repo, "rev-parse", "HEAD") == build_repo["pre"]
    assert not (repo / ".git" / "MERGE_HEAD").exists()


def test_reconcile_keeps_uncommitted_edits_when_it_restores_the_branch(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    (repo / "tracked.txt").write_text("uncommitted plan edit\n", encoding="utf-8")
    _reconcile(build_repo, "c1", "false")
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == (
        "uncommitted plan edit\n"
    )


def test_reconcile_merges_the_next_candidate_after_a_failed_one(build_repo) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    _candidate_branch(repo, "c2", build_repo["base"], {"c2.txt": "c2\n"})
    _reconcile(build_repo, "c1", "false")
    r = _reconcile(build_repo, "c2", "true")
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (0, True)
    assert out["head"] == _git(repo, "rev-parse", "HEAD")
    assert {"c2.txt"} <= _files_in_head(repo)
    assert "c1.txt" not in _files_in_head(repo)


def test_reconcile_reports_a_merge_conflict_without_running_the_suite(
    build_repo, tmp_path
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c3", build_repo["base"], {"shared.txt": "c3 side\n"})
    marker = tmp_path / "suite-ran"
    r = _reconcile(build_repo, "c3", f"touch {marker}")
    out = json.loads(r.stdout)
    assert (r.returncode, out["merged"]) == (1, False)
    assert _git(repo, "rev-parse", "HEAD") == build_repo["pre"]
    assert "shared.txt" in r.stderr
    assert not marker.exists()
    assert not (repo / ".git" / "MERGE_HEAD").exists()


def test_reconcile_exits_two_naming_the_pre_merge_sha_when_the_restore_fails(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c4", build_repo["base"], {"gone.txt": None})
    r = _reconcile(build_repo, "c4", "echo x > gone.txt; exit 1")
    assert (r.returncode, r.stdout) == (2, "")
    assert build_repo["pre"] in r.stderr


def test_reconcile_merged_result_names_branch_head_and_pre_merge_sha(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    out = json.loads(_reconcile(build_repo, "c1", "true").stdout)
    assert out == {
        "branch": "c1",
        "head": _git(repo, "rev-parse", "HEAD"),
        "merged": True,
        "pre_merge_sha": build_repo["pre"],
    }


def test_reconcile_refuses_a_worktree_that_is_not_on_the_build_branch(
    build_repo,
) -> None:
    repo = build_repo["repo"]
    _candidate_branch(repo, "c1", build_repo["base"], {"c1.txt": "c1\n"})
    _git(repo, "checkout", "-q", "c1")
    r = _reconcile(build_repo, "c1", "true")
    assert (r.returncode, r.stdout) == (1, "")
    assert "build" in r.stderr
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "c1"


def test_restore_aborts_a_merge_left_in_progress_before_resetting(build_repo) -> None:
    """A merge can be left half-done when the reconcile script dies mid-merge
    (for example on its timeout); `reset --keep` alone refuses unmerged paths."""
    repo = build_repo["repo"]
    _candidate_branch(repo, "c3", build_repo["base"], {"shared.txt": "c3 side\n"})
    with pytest.raises(subprocess.CalledProcessError):  # the conflict is the setup
        _git(repo, "merge", "--no-edit", "c3")
    assert (repo / ".git" / "MERGE_HEAD").exists()
    build_candidates._restore_branch(str(repo), build_repo["pre"])
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert _git(repo, "rev-parse", "HEAD") == build_repo["pre"]


def _worktree_candidate(repo, tmp_path, cid: int, base: str) -> str:
    """Create candidate `cid` on its own worktree branch with one commit that
    adds `cand<cid>.txt`; return the branch name."""
    branch = f"cand-{cid}"
    path = tmp_path / f"wt-{cid}"
    _git(repo, "worktree", "add", "-q", "-b", branch, str(path), base)
    (path / f"cand{cid}.txt").write_text(f"candidate {cid}\n", encoding="utf-8")
    _commit_all(path, f"candidate {cid} work")
    return branch


def _candidate_entry(cid: int, branch: str, met: int) -> dict:
    return {
        "id": cid,
        "branch": branch,
        "suite_green": True,
        "scenarios_total": 5,
        "scenarios_unmet": 5 - met,
        "errors": 0,
        "warnings": 0,
        "diff_lines": 1,
        "cost_usd": 0.5,
        "screening": "ok",
    }


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
                    _candidate_entry(1, branches[1], met=3),
                    _candidate_entry(2, branches[2], met=5),
                ]
            }
        ),
        encoding="utf-8",
    )

    ranked = json.loads(_run("rank", "--candidates", str(candidates)).stdout)
    winner = branches[ranked["winner"]]
    merged = _reconcile(build_repo, winner, "true")
    cleaned = _run("cleanup", "--repo", str(repo), "--remove", branches[1], branches[2])

    assert (ranked["winner"], merged.returncode, cleaned.returncode) == (2, 0, 0)
    assert {"cand2.txt"} <= _files_in_head(repo)
    assert "cand1.txt" not in _files_in_head(repo)
    assert _git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1
    assert _git(repo, "branch", "--format=%(refname:short)").split() == [BUILD]
