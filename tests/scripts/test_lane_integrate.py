"""Tests for the `lane.py integrate` check engine (`collect_refusals`).

The `integrate` subcommand does not exist yet, so every test drives the
checks through `collect_refusals` and prints what it returns with
`lane_core.emit_refusals`, the renderer `main` uses. Assertions are scoped to
the checks registered so far: a refused run changes nothing, which every row
checks with `unchanged_state` on both worktrees and the gate file.

Every test runs in-process against real git repositories built by
`lane_fixtures`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    GATE_RELATIVE_PATH,
    ComposedLane,
    add_linked_worktree,
    advance_origin,
    advance_trunk,
    argv_spy,
    build_repo_without_remote,
    commit_file,
    composed_gated_lane,
    covers,
    enforce_covers,
    git,
    hermetic_process_env,
    parse_blocks,
    plain_directory,
    repo_with_origin,
    repo_without_remote,
    seed_gate,
    unchanged_state,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core

NOT_IN_A_LANE = "not in a lane"
UNCOMMITTED = "lane has uncommitted changes"


def observed_state(composed: ComposedLane) -> dict[str, object]:
    """What must be equal before and after a refused run: both worktrees, and
    the gate file's bytes (None when absent)."""
    gate = composed.path / GATE_RELATIVE_PATH
    return {
        "lane": unchanged_state(composed.path),
        "trunk": unchanged_state(composed.repo.path),
        "gate": gate.read_bytes() if gate.is_file() else None,
    }


def leave_untracked_file(worktree: Path) -> None:
    (worktree / "scratch.txt").write_text("x\n", encoding="utf-8")


def edit_tracked_file(worktree: Path) -> None:
    (worktree / "base.txt").write_text("edited\n", encoding="utf-8")


def collect(
    composed: ComposedLane,
    *,
    trunk: str | None = None,
    expected_trunk: str | None = None,
    expected_tree: str | None = None,
    cwd: Path | None = None,
) -> list[lane_core.Refusal]:
    """The refusals for `composed`, with its own identities unless overridden."""
    return lane.collect_refusals(
        trunk,
        expected_trunk or composed.expected_trunk,
        expected_tree or composed.expected_tree,
        cwd or composed.path,
    )


def printed_blocks(refusals, capsys) -> list[dict[str, str]]:
    """Print `refusals` as `main` would and return the parsed blocks."""
    code = lane_core.emit_refusals(refusals)
    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    return parse_blocks(captured.err)


def only_block(composed: ComposedLane, capsys, **overrides) -> dict[str, str]:
    """The single block the checks print for `composed`; nothing else changed."""
    before = observed_state(composed)
    (block,) = printed_blocks(collect(composed, **overrides), capsys)
    assert observed_state(composed) == before
    for field in ("refused", "why", "how"):
        assert block[field].strip() != ""
    return block


@pytest.fixture
def composed_without_remote(repo_without_remote, capsys) -> ComposedLane:
    return composed_gated_lane(repo_without_remote, capsys)


@pytest.fixture
def composed_with_origin(repo_with_origin, capsys) -> ComposedLane:
    return composed_gated_lane(repo_with_origin, capsys)


# --- the engine --------------------------------------------------------------


def test_a_composed_lane_with_an_origin_in_good_standing_has_no_refusals(
    composed_with_origin,
):
    assert collect(composed_with_origin) == []


def test_a_composed_lane_without_a_remote_in_good_standing_has_no_refusals(
    composed_without_remote,
):
    assert collect(composed_without_remote) == []


def test_the_checks_are_registered_in_strictly_increasing_order():
    orders = [check.order for check in lane.CHECKS]

    assert orders == sorted(set(orders))


# --- check 1: the tree is the reviewed tree ----------------------------------


@covers("tree mismatch")
def test_collect_a_lane_commit_after_compose_is_a_tree_mismatch_alone(
    composed_with_origin, capsys
):
    old_tree = composed_with_origin.expected_tree
    commit_file(composed_with_origin.path, "later.txt", "later\n", "later work")
    seed_gate(composed_with_origin.path, composed_with_origin.trunk_ref)
    live_tree = git(composed_with_origin.path, "rev-parse", "HEAD^{tree}")

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == "tree mismatch"
    assert f"expected: {old_tree}" in block["why"]
    assert f"live: {live_tree}" in block["why"]
    assert "/code-review --since origin/main" in block["how"]
    assert "compose again" in block["how"]


# --- check 3: the trunk has not moved ---------------------------------------


@covers("trunk moved")
def test_collect_origin_advanced_by_a_fetch_is_trunk_moved_alone(
    composed_with_origin, capsys
):
    old_trunk = composed_with_origin.expected_trunk
    new_trunk = advance_origin(composed_with_origin.repo)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == "trunk moved"
    assert f"expected: {old_trunk}" in block["why"]
    assert f"live: {new_trunk}" in block["why"]
    assert "origin/main" in block["why"]
    assert "/code-review --since origin/main" in block["how"]


# --- check 5: the trunk can fast-forward ------------------------------------

FAST_FORWARD = "trunk cannot fast-forward"


@covers("trunk cannot fast-forward")
def test_collect_a_local_trunk_commit_the_lane_lacks_is_not_an_ancestor(
    composed_with_origin, capsys
):
    advance_trunk(composed_with_origin.repo)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == FAST_FORWARD
    assert "not an ancestor" in block["why"]
    assert "run compose" in block["how"]
    assert "/code-review --since origin/main" in block["how"]


@covers("trunk cannot fast-forward")
def test_collect_trunk_checked_out_nowhere_is_named(composed_with_origin, capsys):
    git(composed_with_origin.repo.path, "switch", "-q", "-c", "elsewhere")

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == FAST_FORWARD
    assert "checked out nowhere" in block["why"]
    assert "git switch main" in block["how"]


@covers("trunk cannot fast-forward")
def test_collect_an_uncommitted_change_in_the_trunk_worktree_is_named(
    composed_with_origin, capsys
):
    edit_tracked_file(composed_with_origin.repo.path)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == FAST_FORWARD
    assert "has uncommitted changes" in block["why"]
    assert "base.txt" in block["why"]
    assert "clean the trunk worktree" in block["how"]


@covers("trunk cannot fast-forward")
def test_collect_a_tag_as_trunk_has_no_branch_to_fast_forward(
    composed_with_origin, capsys
):
    git(composed_with_origin.repo.path, "tag", "v1", "origin/main")

    block = only_block(composed_with_origin, capsys, trunk="v1")

    assert block["refused"] == FAST_FORWARD
    assert "does not exist" in block["why"]
    assert "pass --trunk <branch>" in block["how"]
    assert "git branch" not in block["how"]


@covers("trunk cannot fast-forward")
def test_collect_a_remote_trunk_without_a_local_branch_does_not_exist(
    composed_with_origin, capsys
):
    primary = composed_with_origin.repo.path
    git(primary, "switch", "-q", "-c", "elsewhere")
    git(primary, "branch", "-d", "main")

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == FAST_FORWARD
    assert "local trunk branch main" in block["why"]
    assert "does not exist" in block["why"]
    assert "pass --trunk <branch>" in block["how"]
    assert "or create it: git branch main origin/main" in block["how"]


@covers("trunk cannot fast-forward")
def test_collect_reports_the_first_failing_condition_when_several_fail(
    composed_with_origin, capsys
):
    advance_trunk(composed_with_origin.repo)
    edit_tracked_file(composed_with_origin.repo.path)

    block = only_block(composed_with_origin, capsys)

    assert "not an ancestor" in block["why"]


@covers("trunk moved")
@covers("trunk cannot fast-forward")
def test_collect_a_trunk_moved_after_compose_with_no_remote_fails_both_checks(
    composed_without_remote, capsys
):
    new_trunk = advance_trunk(composed_without_remote.repo)
    before = observed_state(composed_without_remote)

    refusals = collect(composed_without_remote)

    first, second = printed_blocks(refusals, capsys)
    assert first["refused"] == "trunk moved"
    assert f"live: {new_trunk}" in first["why"]
    assert second["refused"] == FAST_FORWARD
    assert "not an ancestor" in second["why"]
    assert observed_state(composed_without_remote) == before


@covers("trunk cannot fast-forward")
def test_collect_an_unfinished_merge_in_the_trunk_worktree_is_named(
    composed_with_origin, capsys
):
    primary = composed_with_origin.repo.path
    merge_head = primary / git(primary, "rev-parse", "--git-path", "MERGE_HEAD")
    merge_head.write_text(git(primary, "rev-parse", "HEAD") + "\n", encoding="utf-8")
    assert git(primary, "status", "--porcelain=v1") == ""

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == "trunk cannot fast-forward"
    assert "has uncommitted changes" in block["why"]
    assert "a merge is in progress (MERGE_HEAD exists)" in block["why"]
    assert "git merge --abort" in block["how"]


def fail_git_for(monkeypatch, prefix: list[str], cwd: Path | None = None) -> None:
    """`lane_core._git` exits 128 for a call whose arguments start with `prefix`
    (in `cwd` when given); every other call runs for real."""
    real = lane_core._git

    def failing(args, where):
        if list(args[: len(prefix)]) == prefix and (
            cwd is None or Path(where).resolve() == cwd.resolve()
        ):
            return subprocess.CompletedProcess(args, 128, "", "fatal: injected")
        return real(args, where)

    monkeypatch.setattr(lane_core, "_git", failing)


@covers("git command failed")
@pytest.mark.parametrize(
    "failing_call",
    ["ancestry", "branch commit", "merge in progress"],
)
def test_collect_a_git_failure_in_check_5_is_a_git_failure_not_a_sub_condition(
    failing_call, composed_with_origin, monkeypatch, capsys
):
    calls = {
        "ancestry": (["merge-base", "--is-ancestor"], composed_with_origin.path),
        "branch commit": (
            ["rev-parse", "--verify", "--quiet", "refs/heads/main^{commit}"],
            None,
        ),
        "merge in progress": (
            ["rev-parse", "--verify", "--quiet", "MERGE_HEAD"],
            composed_with_origin.repo.path,
        ),
    }
    prefix, where = calls[failing_call]
    fail_git_for(monkeypatch, prefix, where)

    (block,) = printed_blocks(collect(composed_with_origin), capsys)

    assert block["refused"] == "git command failed"
    assert "fatal: injected" in block["why"]


# --- check 4: the lane is clean ----------------------------------------------


@covers(UNCOMMITTED)
def test_collect_an_untracked_file_in_the_lane_is_the_only_refusal(
    composed_with_origin, capsys
):
    leave_untracked_file(composed_with_origin.path)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == UNCOMMITTED
    assert "commit or stash" in block["how"]
    assert "scratch.txt" in block["why"]


# --- early stops: one block, no checks ---------------------------------------


@covers(NOT_IN_A_LANE)
def test_collect_the_primary_checkout_on_trunk_is_not_a_lane(
    composed_without_remote, capsys
):
    before = observed_state(composed_without_remote)

    refusals = collect(composed_without_remote, cwd=composed_without_remote.repo.path)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == NOT_IN_A_LANE
    assert "lane.py open" in block["how"]
    assert observed_state(composed_without_remote) == before


@covers(NOT_IN_A_LANE)
def test_collect_a_detached_head_in_a_linked_worktree_is_not_a_lane(
    composed_without_remote, capsys
):
    detached = add_linked_worktree(composed_without_remote.repo, "scratch")
    git(detached, "switch", "-q", "--detach")
    before = observed_state(composed_without_remote)

    refusals = collect(composed_without_remote, cwd=detached)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == NOT_IN_A_LANE
    assert observed_state(composed_without_remote) == before


@covers(NOT_IN_A_LANE)
def test_collect_a_linked_worktree_on_the_trunk_branch_is_not_a_lane(
    composed_without_remote, capsys
):
    repo = composed_without_remote.repo
    git(repo.path, "switch", "-q", "-c", "elsewhere")
    on_trunk = add_linked_worktree(repo, "main-copy", start="main")
    git(on_trunk, "switch", "-q", "main")
    before = observed_state(composed_without_remote)

    refusals = collect(composed_without_remote, cwd=on_trunk)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == NOT_IN_A_LANE
    assert observed_state(composed_without_remote) == before


@covers("trunk ref cannot be resolved")
def test_collect_an_unresolvable_trunk_is_one_block_and_runs_no_check(
    composed_without_remote, capsys
):
    leave_untracked_file(composed_without_remote.path)

    block = only_block(composed_without_remote, capsys, trunk="nonexistent-ref")

    assert block["refused"] == "trunk ref cannot be resolved"
    assert "nonexistent-ref" in block["why"]


@covers("not a git repository")
def test_collect_outside_a_repository_is_one_block(
    composed_without_remote, plain_directory, capsys
):
    refusals = collect(composed_without_remote, cwd=plain_directory)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == "not a git repository"


# --- .claude not ignored ------------------------------------------------------


@covers(UNCOMMITTED)
def test_collect_a_repository_that_does_not_ignore_claude_names_setup(
    repo_without_remote, capsys
):
    git(repo_without_remote.path, "rm", "-q", ".gitignore")
    git(repo_without_remote.path, "commit", "-q", "-m", "stop ignoring .claude")
    composed = composed_gated_lane(repo_without_remote, capsys)

    block = only_block(composed, capsys)

    assert block["refused"] == UNCOMMITTED
    assert ".claude/memory/.pr-review-passed" in block["why"]
    assert "/setup" in block["how"]


# --- a check that hits a git failure ------------------------------------------


@covers("git command failed")
@covers(UNCOMMITTED)
def test_collect_a_git_failure_in_one_check_is_its_refusal_and_the_rest_still_run(
    composed_without_remote, monkeypatch, capsys
):
    leave_untracked_file(composed_without_remote.path)

    def fail(_cwd):
        raise lane_core.RefusalError(
            lane_core.git_command_failed_refusal("git rev-parse HEAD", "fatal: boom")
        )

    monkeypatch.setattr(lane_core, "head_tree", fail)

    first, second = printed_blocks(collect(composed_without_remote), capsys)

    assert first["refused"] == "git command failed"
    assert "fatal: boom" in first["why"]
    assert second["refused"] == UNCOMMITTED
