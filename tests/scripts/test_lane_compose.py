"""Tests for `lane.py compose`: merge trunk into the lane, print the identities.

Every test runs in-process against real git repositories built by
`lane_fixtures`. The command line and `open` are tested in `test_lane.py`; the
refusal registry and the git seam in `test_lane_core.py`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    FAILING_MERGE_NUMBER,
    GIT_FAILED,
    HOOK_SENTINEL,
    REJECT_HOOK,
    add_linked_worktree,
    advance_origin,
    advance_trunk,
    argv_spy,
    build_repo_with_origin,
    build_repo_without_remote,
    commit_file,
    conflicting_lane,
    covers,
    default_lane_dir,
    enforce_covers,
    fail_git_ok_for,
    git,
    has_unfinished_merge,
    hermetic_process_env,
    install_hook,
    is_ancestor,
    lane_with_commit,
    merge_argvs,
    open_origin_lane,
    parse_output,
    plain_directory,
    rejecting_nth_merge_hook,
    repo_with_origin,
    repo_without_remote,
    run_main,
    single_refusal,
    stub_git_call,
    unchanged_state,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core

#: The `merge` arguments before the target: a fast-forward is wanted, and an
#: editor is never opened.
#: `--no-overwrite-ignore`: a tracked file never arrives over an ignored local file.
MERGE_ARGS = ["git", "merge", "--ff", "--no-edit", "--no-overwrite-ignore"]


def commit_of(cwd: Path, ref: str) -> str:
    return git(cwd, "rev-parse", f"{ref}^{{commit}}")


def raise_boom() -> None:
    raise lane_core.RefusalError(lane_core.git_command_failed_refusal("git x", "boom"))


# --- merge and identity output -----------------------------------------------


def test_compose_merges_a_moved_trunk_into_the_lane(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)

    code, _, err = run_main(["compose"], lane_path, capsys)

    assert (code, err) == (0, "")
    assert is_ancestor(lane_path, trunk_tip, "HEAD")
    assert (lane_path / "trunk.txt").is_file()
    assert (lane_path / "lane.txt").is_file()


def test_compose_prints_the_trunk_commit_and_the_head_tree_as_identities(
    repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)

    _, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert printed["expected-trunk"] == trunk_tip
    assert printed["expected-tree"] == git(lane_path, "rev-parse", "HEAD^{tree}")
    assert (printed["lane"], printed["trunk"]) == ("feature", "main")


def test_compose_prints_a_ready_to_run_integrate_line(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)

    _, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert printed["next"] == (
        f"lane.py integrate --expected-trunk {printed['expected-trunk']}"
        f" --expected-tree {printed['expected-tree']}"
    )


def test_compose_repeats_trunk_in_the_next_line_only_when_it_was_given(
    repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)

    _, out, _ = run_main(["compose", "--trunk", "main"], lane_path, capsys)

    assert parse_output(out)["next"].endswith(" --trunk main")


def test_compose_is_a_no_op_when_the_lane_already_contains_trunk(
    repo_without_remote, capsys, argv_spy
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    first = run_main(["compose"], lane_path, capsys)
    head_after_first = git(lane_path, "rev-parse", "HEAD")
    records_before = len(argv_spy.records)

    second = run_main(["compose"], lane_path, capsys)

    assert first[0] == second[0] == 0
    assert second[1] == first[1]
    assert git(lane_path, "rev-parse", "HEAD") == head_after_first
    assert merge_argvs(argv_spy, records_before) == []


def test_a_lane_that_is_only_behind_fast_forwards_without_a_merge_commit(
    repo_without_remote, capsys
):
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    trunk_tip = advance_trunk(repo_without_remote)

    code, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert code == 0
    assert git(lane_path, "rev-parse", "HEAD") == trunk_tip
    assert printed["expected-tree"] == git(
        repo_without_remote.path, "rev-parse", "main^{tree}"
    )
    assert git(lane_path, "rev-list", "--merges", "--count", "HEAD") == "0"


# --- the fast-forward policy is compose's own, not the user's ---------------


@pytest.mark.parametrize("configured", ["false", "only"])
def test_a_behind_only_lane_fast_forwards_whatever_merge_ff_is_configured(
    configured, repo_without_remote, capsys
):
    git(repo_without_remote.path, "config", "--local", "merge.ff", configured)
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    trunk_tip = advance_trunk(repo_without_remote)

    code, _, err = run_main(["compose"], lane_path, capsys)

    assert (code, err) == (0, "")
    assert git(lane_path, "rev-parse", "HEAD") == trunk_tip
    assert git(lane_path, "rev-list", "--merges", "--count", "HEAD") == "0"


@pytest.mark.parametrize("configured", ["false", "only"])
def test_a_diverged_lane_merges_whatever_merge_ff_is_configured(
    configured, repo_without_remote, capsys
):
    git(repo_without_remote.path, "config", "--local", "merge.ff", configured)
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)

    code, _, err = run_main(["compose"], lane_path, capsys)

    assert (code, err) == (0, "")
    assert is_ancestor(lane_path, trunk_tip, "HEAD")
    assert git(lane_path, "rev-list", "--merges", "--count", "HEAD") == "1"


def test_compose_merges_the_resolved_trunk_commit_with_fast_forward_allowed(
    repo_without_remote, capsys, argv_spy
):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)
    records_before = len(argv_spy.records)

    run_main(["compose"], lane_path, capsys)

    assert merge_argvs(argv_spy, records_before) == [[*MERGE_ARGS, trunk_tip]]


# --- the trunk compose merges is the trunk it prints ------------------------


def test_compose_also_merges_a_local_trunk_branch_that_is_ahead_of_the_trunk_ref(
    repo_with_origin, capsys
):
    lane_path = open_origin_lane(repo_with_origin)
    origin_tip = git(repo_with_origin.path, "rev-parse", "origin/main")
    local_tip = advance_trunk(repo_with_origin, "local.txt")

    code, out, _ = run_main(["compose"], lane_path, capsys)

    assert code == 0
    assert is_ancestor(lane_path, local_tip, "HEAD")
    assert (lane_path / "local.txt").is_file()
    printed = parse_output(out)
    assert printed["trunk"] == "origin/main"
    assert printed["expected-trunk"] == origin_tip


def test_compose_merges_the_trunk_commit_then_the_local_branch_when_they_diverged(
    repo_with_origin, capsys, argv_spy
):
    lane_path = open_origin_lane(repo_with_origin)
    origin_tip = advance_origin(repo_with_origin)
    local_tip = advance_trunk(repo_with_origin, "local.txt")
    records_before = len(argv_spy.records)

    code, out, _ = run_main(["compose"], lane_path, capsys)

    assert code == 0
    assert is_ancestor(lane_path, origin_tip, "HEAD")
    assert is_ancestor(lane_path, local_tip, "HEAD")
    assert parse_output(out)["expected-trunk"] == origin_tip
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == [origin_tip, local_tip]


def test_expected_trunk_is_the_commit_merged_even_when_the_trunk_moves_mid_compose(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = open_origin_lane(repo_with_origin)
    resolved_tip = advance_origin(repo_with_origin)
    real_attempt = lane_core.git_attempt
    moved: list[str] = []

    def trunk_moves_before_the_merge(args, cwd):
        if args[:1] == ["merge"] and not moved:
            moved.append(advance_origin(repo_with_origin, "later.txt"))
        return real_attempt(args, cwd)

    monkeypatch.setattr(lane_core, "git_attempt", trunk_moves_before_the_merge)

    code, out, _ = run_main(["compose"], lane_path, capsys)

    assert code == 0
    assert parse_output(out)["expected-trunk"] == resolved_tip
    assert is_ancestor(lane_path, resolved_tip, "HEAD")
    assert not is_ancestor(lane_path, moved[0], "HEAD")


# --- refusals outside a usable lane ----------------------------------------


def primary_on_trunk(repo):
    return repo.path


def detached_linked_worktree(repo):
    lane_path = add_linked_worktree(repo, "feature")
    git(lane_path, "switch", "-q", "--detach")
    return lane_path


def linked_worktree_on_trunk(repo):
    git(repo.path, "switch", "-q", "-c", "elsewhere")
    path = default_lane_dir(repo, "on-main")
    git(repo.path, "worktree", "add", "-q", str(path), "main")
    return path


@pytest.mark.parametrize(
    "place",
    [primary_on_trunk, detached_linked_worktree, linked_worktree_on_trunk],
    ids=["primary-on-trunk", "detached-head", "linked-worktree-on-trunk"],
)
@covers("not in a lane")
def test_compose_refuses_outside_a_lane(place, repo_without_remote, capsys):
    cwd = place(repo_without_remote)
    before = unchanged_state(cwd)

    code, out, err = run_main(["compose"], cwd, capsys)

    block = single_refusal(code, out, err, "not in a lane")
    assert str(cwd) in block["why"]
    assert "lane.py open <name>" in block["how"]
    assert unchanged_state(cwd) == before


def make_staged(lane_path):
    (lane_path / "staged.txt").write_text("staged\n")
    git(lane_path, "add", "--", "staged.txt")
    return "staged.txt"


def make_unstaged(lane_path):
    (lane_path / "base.txt").write_text("edited\n")
    return "base.txt"


def make_untracked(lane_path):
    (lane_path / "untracked.txt").write_text("new\n")
    return "untracked.txt"


@pytest.mark.parametrize(
    "make_dirty", [make_staged, make_unstaged, make_untracked], ids=lambda f: f.__name__
)
@covers("lane has uncommitted changes")
def test_compose_refuses_a_lane_with_any_uncommitted_change(
    make_dirty, repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    dirty_path = make_dirty(lane_path)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "lane has uncommitted changes")
    assert dirty_path in block["why"]
    assert "commit or stash" in block["how"]
    assert "add .claude/ to .gitignore" in block["how"]
    assert "/setup" in block["how"]
    assert (lane_path / dirty_path).exists()
    assert unchanged_state(lane_path) == before


@covers("lane has uncommitted changes")
def test_compose_refuses_a_lane_with_a_merge_in_progress_and_leaves_it_alone(
    repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    # Tree, index and working tree equal HEAD's; only MERGE_HEAD says a merge is open.
    git(lane_path, "merge", "-s", "ours", "--no-commit", "--no-ff", "main")
    assert git(lane_path, "status", "--porcelain=v1") == ""
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "lane has uncommitted changes")
    assert "merge in progress" in block["why"]
    assert "git merge --abort" in block["how"]
    assert "git commit" in block["how"]
    assert has_unfinished_merge(lane_path)
    assert unchanged_state(lane_path) == before


@covers("trunk ref cannot be resolved")
def test_compose_refuses_a_trunk_that_does_not_resolve(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose", "--trunk", "missing-ref"], lane_path, capsys)

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'missing-ref'" in block["why"]
    assert unchanged_state(lane_path) == before


@covers("not a git repository")
def test_compose_outside_a_repository_is_a_refusal_block(plain_directory, capsys):
    plain = plain_directory

    code, out, err = run_main(["compose"], plain, capsys)

    block = single_refusal(code, out, err, "not a git repository")
    assert str(plain) in block["why"]
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


# --- a merge that cannot complete --------------------------------------------


@covers("compose conflict")
def test_a_merge_conflict_leaves_the_lane_as_it_was(repo_without_remote, capsys):
    lane_path = conflicting_lane(repo_without_remote)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert "merging main into the lane" in block["why"]
    assert "base.txt" in block["why"]
    assert "the lane was restored to its state before compose" in block["why"]
    assert "merge main by hand" in block["how"]
    assert "compose again" in block["how"]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("compose conflict")
def test_a_conflict_on_the_local_trunk_merge_undoes_the_first_merge_too(
    repo_with_origin, capsys, argv_spy
):
    lane_path = conflicting_lane(repo_with_origin, with_origin=True)
    before = unchanged_state(lane_path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert "merging main into the lane" in block["why"]
    assert "base.txt" in block["why"]
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == [
        commit_of(lane_path, "origin/main"),
        commit_of(lane_path, "refs/heads/main"),
    ]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("compose merge failed")
def test_a_rejected_merge_leaves_the_lane_as_it_was(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)
    install_hook(repo_without_remote, "pre-merge-commit", REJECT_HOOK)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert HOOK_SENTINEL in block["why"]
    assert f"{' '.join(MERGE_ARGS)} {trunk_tip}" in block["why"]
    assert "the lane was restored to its state before compose" in block["why"]
    assert "resolve" in block["how"]
    assert "compose again" in block["how"]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("compose merge failed")
def test_a_rejected_second_merge_restores_the_lane_to_before_the_first(
    repo_with_origin, tmp_path, capsys
):
    lane_path = open_origin_lane(repo_with_origin)
    advance_origin(repo_with_origin)
    advance_trunk(repo_with_origin, "local.txt")
    hook_call_log = tmp_path / "hook-calls"
    install_hook(
        repo_with_origin,
        "pre-merge-commit",
        rejecting_nth_merge_hook(hook_call_log),
    )
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert len(hook_call_log.read_text().splitlines()) == FAILING_MERGE_NUMBER
    assert "could not merge main:" in block["why"]
    assert HOOK_SENTINEL in block["why"]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("compose merge failed")
def test_a_merge_failure_whose_unmerged_paths_cannot_be_listed_still_restores_the_lane(
    repo_without_remote, capsys, monkeypatch
):
    lane_path = conflicting_lane(repo_without_remote)
    before = unchanged_state(lane_path)
    stub_git_call(monkeypatch, "git_text", [["diff", "--name-only"]], raise_boom)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert "could not merge main" in block["why"]
    assert "could not list the unmerged paths" in block["why"]
    assert "boom" in block["why"]
    assert "the lane was restored to its state before compose" in block["why"]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


# --- a restore that cannot be verified ---------------------------------------


@covers("compose restore unverified")
def test_a_conflict_whose_restore_does_not_take_effect_is_reported_as_unverified(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = conflicting_lane(repo_with_origin, with_origin=True)
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    fail_git_ok_for(monkeypatch, ["reset"])

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert pre_compose in block["why"]
    assert "base.txt" in block["why"]
    assert "was restored to its state" not in block["why"]
    assert block["why"].count("could not be verified") == 1
    assert f"git reset --hard {pre_compose}" in block["how"]
    assert "save any edits" in block["how"]
    assert git(lane_path, "rev-parse", "HEAD") != pre_compose


@covers("compose restore unverified")
def test_a_rejected_merge_whose_restore_does_not_take_effect_is_reported_as_unverified(
    repo_with_origin, tmp_path, capsys, monkeypatch
):
    lane_path = open_origin_lane(repo_with_origin)
    advance_origin(repo_with_origin)
    advance_trunk(repo_with_origin, "local.txt")
    install_hook(
        repo_with_origin,
        "pre-merge-commit",
        rejecting_nth_merge_hook(tmp_path / "hook-calls"),
    )
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    fail_git_ok_for(monkeypatch, ["reset"])

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert pre_compose in block["why"]
    assert HOOK_SENTINEL in block["why"]
    assert "was restored to its state" not in block["why"]
    assert f"git reset --hard {pre_compose}" in block["how"]


@pytest.fixture
def restore_commands_do_nothing(monkeypatch):
    """`merge --abort` and `reset` report failure and change nothing."""
    fail_git_ok_for(monkeypatch, ["reset"], ["merge", "--abort"])


def test_the_restore_undoes_a_merged_index_that_has_no_merge_head(
    repo_without_remote,
):
    """Git 2.x keeps MERGE_HEAD after a rejected merge; the restore must not rely on it."""
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    before = unchanged_state(lane_path)
    git(lane_path, "merge", "--no-commit", "--no-ff", "main")
    merge_head = lane_path / git(lane_path, "rev-parse", "--git-path", "MERGE_HEAD")
    merge_head.unlink()
    assert unchanged_state(lane_path) != before

    assert lane._restore_verified(snapshot, lane_path)

    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


def test_the_restore_is_unverified_while_a_merge_is_still_in_progress(
    repo_without_remote, restore_commands_do_nothing
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    # Tree, index and working tree equal HEAD's; only MERGE_HEAD is left over.
    git(lane_path, "merge", "-s", "ours", "--no-commit", "--no-ff", "main")
    assert git(lane_path, "status", "--porcelain=v1") == ""

    assert not lane._restore_verified(snapshot, lane_path)


def test_the_restore_is_unverified_while_the_working_tree_is_dirty(
    repo_without_remote, restore_commands_do_nothing
):
    lane_path = lane_with_commit(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    (lane_path / "base.txt").write_text("edited\n")

    assert not lane._restore_verified(snapshot, lane_path)


def test_the_restore_is_unverified_when_a_check_cannot_run(
    repo_without_remote, monkeypatch
):
    lane_path = lane_with_commit(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    monkeypatch.setattr(lane_core, "dirty_paths", lambda _path: raise_boom())

    assert not lane._restore_verified(snapshot, lane_path)


def test_a_restore_that_worked_is_verified(repo_without_remote):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    git(lane_path, "merge", "-q", "--no-edit", "main")

    assert lane._restore_verified(snapshot, lane_path)
    assert git(lane_path, "rev-parse", "HEAD") == snapshot.head


# --- any failure after the first merge undoes it -----------------------------


def lane_needing_two_merges(repo):
    """A lane that lacks both origin's main and a diverged local main."""
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    advance_trunk(repo, "local.txt")
    return lane_path


def fail_once_a_merge_has_succeeded(monkeypatch, name: str) -> None:
    """`lane_core.<name>` raises from the first call after a successful `merge`."""
    real_attempt = lane_core.git_attempt
    real = getattr(lane_core, name)
    merged: list[bool] = []

    def attempt(args, cwd):
        result = real_attempt(args, cwd)
        if args[:1] == ["merge"] and result.ok:
            merged.append(True)
        return result

    def failing(*args, **kwargs):
        if merged:
            raise_boom()
        return real(*args, **kwargs)

    monkeypatch.setattr(lane_core, "git_attempt", attempt)
    monkeypatch.setattr(lane_core, name, failing)


@covers("git command failed")
def test_a_git_failure_between_the_two_merges_restores_the_lane(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = lane_needing_two_merges(repo_with_origin)
    before = unchanged_state(lane_path)
    fail_once_a_merge_has_succeeded(monkeypatch, "is_ancestor")

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "boom" in block["why"]
    assert "the lane was restored to its state before compose" in block["why"]
    assert "compose again" in block["how"]
    assert "run the failed command again" not in block["how"]
    assert unchanged_state(lane_path) == before


@covers("git command failed")
def test_a_failure_reading_the_tree_after_the_merges_restores_the_lane(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = lane_needing_two_merges(repo_with_origin)
    before = unchanged_state(lane_path)
    monkeypatch.setattr(lane_core, "head_tree", lambda _path: raise_boom())

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "the lane was restored to its state before compose" in block["why"]
    assert "compose again" in block["how"]
    assert unchanged_state(lane_path) == before


@covers("compose restore unverified")
def test_a_failure_after_a_merge_with_a_restore_that_fails_is_reported_as_unverified(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = lane_needing_two_merges(repo_with_origin)
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    fail_once_a_merge_has_succeeded(monkeypatch, "is_ancestor")
    fail_git_ok_for(monkeypatch, ["reset"])

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert "boom" in block["why"]
    assert pre_compose in block["why"]
    assert block["why"].startswith("compose failed after merging origin/main (")
    assert "merging origin/main failed" not in block["why"]
    assert f"git reset --hard {pre_compose}" in block["how"]


@covers("compose restore unverified")
def test_the_unverified_report_after_a_non_merge_failure_omits_a_target_it_skipped(
    repo_with_origin, capsys, monkeypatch
):
    advance_origin(repo_with_origin)
    # The lane starts at the advanced origin/main: that target is skipped and
    # only the diverged local main is merged before the failure.
    lane_path = open_origin_lane(repo_with_origin)
    advance_trunk(repo_with_origin, "local.txt")
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    fail_once_a_merge_has_succeeded(monkeypatch, "head_tree")
    fail_git_ok_for(monkeypatch, ["reset"])

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert block["why"].startswith("compose failed after merging main (boom")
    assert "origin/main" not in block["why"]
    assert pre_compose in block["why"]


def fail_the_merge_probe_after_a_failed_merge(monkeypatch, times: int | None) -> None:
    """`lane_core.merge_in_progress` raises (exit 128) from the first call after a
    failed `merge`: `times` calls, or every call when None."""
    real_attempt = lane_core.git_attempt
    real = lane_core.merge_in_progress
    state = {"merge_failed": False, "raised": 0}

    def attempt(args, cwd):
        result = real_attempt(args, cwd)
        if args[:1] == ["merge"] and not result.ok:
            state["merge_failed"] = True
        return result

    def probe(cwd):
        if state["merge_failed"] and (times is None or state["raised"] < times):
            state["raised"] += 1
            raise_boom()
        return real(cwd)

    monkeypatch.setattr(lane_core, "git_attempt", attempt)
    monkeypatch.setattr(lane_core, "merge_in_progress", probe)


@covers("compose conflict")
def test_a_failed_merge_probe_does_not_stop_the_reset_that_restores_the_lane(
    repo_without_remote, capsys, monkeypatch
):
    lane_path = conflicting_lane(repo_without_remote)
    before = unchanged_state(lane_path)
    fail_the_merge_probe_after_a_failed_merge(monkeypatch, times=1)

    code, out, err = run_main(["compose"], lane_path, capsys)

    single_refusal(code, out, err, "compose conflict")
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("compose restore unverified")
def test_a_merge_probe_that_keeps_failing_still_resets_and_reports_unverified(
    repo_without_remote, capsys, monkeypatch
):
    lane_path = conflicting_lane(repo_without_remote)
    before = unchanged_state(lane_path)
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    fail_the_merge_probe_after_a_failed_merge(monkeypatch, times=None)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert f"git reset --hard {pre_compose}" in block["how"]
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


@covers("git command failed")
def test_a_failed_origin_lookup_after_a_merge_restores_the_lane_instead_of_printing_next(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = open_origin_lane(repo_with_origin)
    advance_origin(repo_with_origin)
    before = unchanged_state(lane_path)
    stub_git_call(monkeypatch, "git_text", [["remote", "get-url"]], raise_boom)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "the lane was restored to its state before compose" in block["why"]
    assert unchanged_state(lane_path) == before


@covers("git command failed")
def test_a_failed_origin_lookup_with_nothing_to_merge_prints_no_next_line(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = open_origin_lane(repo_with_origin)
    before = unchanged_state(lane_path)
    stub_git_call(monkeypatch, "git_text", [["remote", "get-url"]], raise_boom)

    code, out, err = run_main(["compose"], lane_path, capsys)

    single_refusal(code, out, err, GIT_FAILED)
    assert unchanged_state(lane_path) == before


def test_an_interrupt_during_the_second_merge_restores_the_lane_and_propagates(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = lane_needing_two_merges(repo_with_origin)
    before = unchanged_state(lane_path)
    real_attempt = lane_core.git_attempt
    merges: list[list[str]] = []

    def interrupted(args, cwd):
        if args[:1] == ["merge"] and "--abort" not in args:
            merges.append(list(args))
            if len(merges) == 2:
                raise KeyboardInterrupt
        return real_attempt(args, cwd)

    monkeypatch.setattr(lane_core, "git_attempt", interrupted)

    with pytest.raises(KeyboardInterrupt):
        lane.main(["compose"], cwd=lane_path)

    assert len(merges) == 2
    assert capsys.readouterr().out == ""
    assert unchanged_state(lane_path) == before


@covers("git command failed")
def test_a_failure_before_any_merge_runs_no_restore(
    repo_without_remote, capsys, monkeypatch, argv_spy
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    git(repo_without_remote.path, "tag", "v1", "main")
    before = unchanged_state(lane_path)
    # A tag has no local branch, so only the merge loop asks about ancestry.
    stub_git_call(monkeypatch, "git_ok", [["merge-base"]], raise_boom)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["compose", "--trunk", "v1"], lane_path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "restored" not in block["why"]
    resets = [a for a in argv_spy.records[records_before:] if a[:2] == ["git", "reset"]]
    assert resets == []
    assert unchanged_state(lane_path) == before


# --- merge targets name a ref for people and a commit for git -----------------


def test_a_merge_target_pairs_the_ref_shown_in_messages_with_the_commit_git_merges(
    repo_with_origin,
):
    lane_path = lane_needing_two_merges(repo_with_origin)

    targets = lane._merge_targets(lane._enter_lane(None, lane_path))

    assert targets == [
        lane.MergeTarget(ref="origin/main", commit=commit_of(lane_path, "origin/main")),
        lane.MergeTarget(ref="main", commit=commit_of(lane_path, "refs/heads/main")),
    ]


# --- refusal text is data, not markup ----------------------------------------

HOSTILE_NAME = "odd\nname\x1b[31m.txt"


def add_add_conflict(repo, name: str) -> Path:
    """The lane and the trunk each add `name` with different content."""
    lane_path = add_linked_worktree(repo, "feature")
    commit_file(lane_path, name, "lane\n", "lane adds it")
    advance_trunk(repo, name, "trunk\n")
    return lane_path


@covers("compose conflict")
def test_a_path_with_a_newline_and_an_escape_cannot_forge_or_hide_a_line(
    repo_without_remote, capsys
):
    lane_path = add_add_conflict(repo_without_remote, HOSTILE_NAME)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert [line.split(":")[0] for line in err.splitlines()] == [
        "refused",
        "why",
        "how",
    ]
    assert "\x1b" not in err
    assert "odd\\x0aname\\x1b[31m.txt" in block["why"]
    assert unchanged_state(lane_path) == before


def test_a_path_that_is_not_utf8_is_shown_not_raised_and_the_lane_is_restored(
    repo_without_remote, capsys
):
    name = os.fsdecode(b"caf\xe9.txt")
    try:
        lane_path = add_add_conflict(repo_without_remote, name)
    except OSError:
        pytest.skip("this file system rejects a file name that is not UTF-8")
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert "caf" in block["why"]
    assert "Traceback" not in err
    assert unchanged_state(lane_path) == before
    assert not has_unfinished_merge(lane_path)


# --- an ignored local file is never written over -----------------------------

IGNORED_NAME = "secret.txt"


def ignore_and_let_trunk_track(repo, lane_path: Path) -> None:
    """`IGNORED_NAME` is ignored and present in the lane; the trunk adds it as tracked.

    `update-index --add` stages an ignored path, which `git add` would refuse.
    """
    common = Path(repo.path, git(repo.path, "rev-parse", "--git-common-dir"))
    (common / "info" / "exclude").write_text(f"{IGNORED_NAME}\n", encoding="utf-8")
    (lane_path / IGNORED_NAME).write_text("local secret\n", encoding="utf-8")
    (repo.path / IGNORED_NAME).write_text("from trunk\n", encoding="utf-8")
    git(repo.path, "update-index", "--add", IGNORED_NAME)
    git(repo.path, "commit", "-q", "-m", "trunk tracks the ignored name")


@covers("compose merge failed")
@pytest.mark.parametrize("lane_has_own_commit", [True, False], ids=["merge", "ff"])
def test_a_tracked_file_arriving_over_an_ignored_local_file_is_refused(
    lane_has_own_commit, repo_without_remote, capsys
):
    repo = repo_without_remote
    lane_path = (
        lane_with_commit(repo)
        if lane_has_own_commit
        else add_linked_worktree(repo, "feature")
    )
    ignore_and_let_trunk_track(repo, lane_path)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert IGNORED_NAME in block["why"]
    assert (lane_path / IGNORED_NAME).read_text() == "local secret\n"
    assert unchanged_state(lane_path) == before


# --- merges only what exists and differs -------------------------------------


def row_local_branch_is_the_trunk(root):
    repo = build_repo_without_remote(root)
    lane_path = lane_with_commit(repo)
    advance_trunk(repo)
    return lane_path, [], ["main"]


def row_trunk_is_a_tag(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "tag", "v1", "origin/main")
    advance_trunk(repo, "local.txt")
    return lane_path, ["--trunk", "v1"], ["v1"]


def row_local_main_contains_origin_main(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "merge", "-q", "--ff-only", "origin/main")
    advance_trunk(repo, "local.txt")
    return lane_path, [], ["refs/heads/main"]


def row_local_main_equals_origin_main(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "merge", "-q", "--ff-only", "origin/main")
    return lane_path, [], ["origin/main"]


def row_origin_main_contains_local_main(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    return lane_path, [], ["origin/main"]


def row_lane_contains_both(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_trunk(repo, "local.txt")
    git(lane_path, "merge", "-q", "--no-edit", "main")
    return lane_path, [], []


@pytest.mark.parametrize(
    "row",
    [
        row_local_branch_is_the_trunk,
        row_trunk_is_a_tag,
        row_local_main_contains_origin_main,
        row_local_main_equals_origin_main,
        row_origin_main_contains_local_main,
        row_lane_contains_both,
    ],
    ids=lambda row: row.__name__.removeprefix("row_"),
)
def test_compose_merges_each_target_at_most_once_and_only_when_it_is_missing(
    row, tmp_path, capsys, argv_spy
):
    lane_path, trunk_args, expected_refs = row(tmp_path)
    expected_commits = [commit_of(lane_path, ref) for ref in expected_refs]
    records_before = len(argv_spy.records)

    code, _, err = run_main(["compose", *trunk_args], lane_path, capsys)

    assert (code, err) == (0, "")
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == expected_commits


# --- open and compose behave the same on every origin ------------------------

GITHUB_URL = "https://github.com/acme/widgets.git"
PR_NEXT_STEP = "open a PR with /pr (or pass --local-trunk to integrate locally)"


def origin_github(root):
    repo = build_repo_with_origin(root)
    git(repo.path, "remote", "set-url", "origin", GITHUB_URL)
    return repo


def open_then_compose(build, tmp_path, capsys):
    """Build a repository, open a lane in it and compose there."""
    repo = build(tmp_path)
    open_code, open_out, _ = run_main(["open", "feat"], repo.path, capsys)
    compose_code, out, err = run_main(
        ["compose"], Path(parse_output(open_out)["worktree"]), capsys
    )
    assert (open_code, compose_code, err) == (0, 0, "")
    return repo, parse_output(out)


@pytest.mark.parametrize(
    "build",
    [origin_github, build_repo_with_origin, build_repo_without_remote],
    ids=["github", "other", "none"],
)
def test_open_then_compose_prints_the_identities_on_every_origin(
    build, tmp_path, capsys
):
    repo, printed = open_then_compose(build, tmp_path, capsys)

    assert printed["expected-trunk"] == git(repo.path, "rev-parse", "main")
    assert printed["expected-tree"] == git(repo.path, "rev-parse", "main^{tree}")


@pytest.mark.parametrize(
    "build",
    [build_repo_with_origin, build_repo_without_remote],
    ids=["other", "none"],
)
def test_compose_prints_an_integrate_command_to_run_next_on_a_non_github_origin(
    build, tmp_path, capsys
):
    repo, printed = open_then_compose(build, tmp_path, capsys)

    assert printed["next"] == (
        f"lane.py integrate --expected-trunk {git(repo.path, 'rev-parse', 'main')}"
        f" --expected-tree {git(repo.path, 'rev-parse', 'main^{tree}')}"
    )


def test_compose_prints_the_pr_step_to_run_next_on_a_github_origin(tmp_path, capsys):
    _, printed = open_then_compose(origin_github, tmp_path, capsys)

    assert printed["next"] == PR_NEXT_STEP


def test_a_github_origin_keeps_the_pr_next_line_when_a_trunk_is_given(tmp_path, capsys):
    repo = origin_github(tmp_path)
    lane_path = add_linked_worktree(repo, "feat", start="origin/main")

    _, out, _ = run_main(["compose", "--trunk", "origin/main"], lane_path, capsys)

    assert parse_output(out)["next"] == PR_NEXT_STEP
