"""Tests for the `lane.py integrate` command: `main(["integrate", ...])`.

Identity arguments, each check refusing alone through `main`, the success path,
the apply sequence, a failing apply step (what is done, what remains), the races
between the checks and the apply, and the full flows. The checks themselves are
tested in `test_lane_integrate_checks.py`.

A refused run changes nothing, which `assert_refused_unchanged` checks on both
worktrees and the gate file. Every test runs in-process against real git
repositories built by `lane_fixtures` and `lane_fixtures_integrate`; a race is a
real git action driven from the `lane_core._run` seam (`GitFailure`), never a
patched first-party function.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from lane_fixtures import (
    COMPOSE_AGAIN,
    NOT_A_LANE_PLACES,
    TRUNK,
    GitFailure,
    add_linked_worktree,
    advance_origin,
    advance_trunk,
    argv_spy,
    covers,
    enforce_covers,
    fail_unlink_of,
    git,
    git_env,
    hermetic_process_env,
    parse_blocks,
    parse_output,
    plain_directory,
    repo_with_origin,
    repo_without_remote,
    run_main,
    single_refusal,
    use_github_origin,
)
from lane_fixtures_integrate import (
    GATE_RELATIVE_PATH,
    NETWORK_ARGV_PREFIXES,
    OMIT,
    ComposedLane,
    assert_integrated,
    assert_lane_kept,
    assert_refused_unchanged,
    assert_trunk_at_lane_head,
    branch_exists_in,
    build_composed_with_github_origin,
    commit_in,
    composed_gated_lane,
    composed_with_origin,
    composed_without_remote,
    edit_tracked_file,
    hook_exit_code,
    integrate_argv,
    leave_untracked_file,
    observed_state,
    report_lines,
    run_integrate,
    seed_gate,
)

from _repo_root import REPO_ROOT

# `lane_fixtures` puts the lane scripts and `hooks/lib` on `sys.path`; import
# them after it.
# isort: split

import lane
import lane_core

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"

# The `what` strings are written out here, not read from lane_core: the tests
# are an oracle independent of the code they check.
WHAT_NOT_IN_A_LANE = "not in a lane"
WHAT_UNCOMMITTED = "lane has uncommitted changes"
WHAT_REVIEW_GATE = "review gate stale or missing"
WHAT_TREE_MISMATCH = "tree mismatch"
WHAT_TRUNK_MOVED = "trunk moved"
WHAT_FAST_FORWARD = "trunk cannot fast-forward"
WHAT_PR_REPOSITORY = "PR repository"
WHAT_INVALID_IDENTITY = "invalid identity argument"
WHAT_INTEGRATE_STEP_FAILED = "integrate step failed"

WRONG_SHA = "0" * 40


# --- identity arguments -------------------------------------------------------


@covers("invalid identity argument")
@pytest.mark.parametrize(
    ("flag", "name"),
    [("--expected-tree", "expected_tree"), ("--expected-trunk", "expected_trunk")],
)
@pytest.mark.parametrize(
    "value",
    ["a" * 12, "G" * 40, "g" * 40, "a" * 39, "a" * 41, "a" * 64, "", "A" * 40],
    ids=[
        "abbreviated",
        "uppercase non-hex",
        "lowercase non-hex",
        "39 characters",
        "41 characters",
        "64 characters",
        "empty",
        "uppercase hex",
    ],
)
def test_integrate_a_malformed_identity_is_one_invalid_identity_block(
    flag, name, value, composed_with_origin, capsys
):
    block = assert_refused_unchanged(
        composed_with_origin,
        capsys,
        WHAT_INVALID_IDENTITY,
        {"why": [flag], "how": ["40-hex"]},
        **{name: value},
    )

    assert repr(value) in block["why"]


@covers("invalid identity argument")
def test_integrate_two_malformed_identities_are_still_one_block(
    composed_with_origin, capsys
):
    assert_refused_unchanged(
        composed_with_origin,
        capsys,
        WHAT_INVALID_IDENTITY,
        {"why": ["--expected-trunk", "--expected-tree"]},
        expected_trunk="a" * 12,
        expected_tree="ZZ",
    )


@pytest.mark.parametrize(
    ("flag", "name"),
    [("--expected-trunk", "expected_trunk"), ("--expected-tree", "expected_tree")],
)
def test_integrate_an_omitted_identity_flag_is_a_usage_error(
    flag, name, composed_with_origin, capsys
):
    before = observed_state(composed_with_origin)

    code, out, err = run_integrate(composed_with_origin, capsys, **{name: OMIT})

    assert (code, out) == (2, "")
    assert flag in err
    assert observed_state(composed_with_origin) == before


@covers("tree mismatch")
def test_integrate_a_valid_but_wrong_tree_is_a_tree_mismatch(
    composed_with_origin, capsys
):
    assert_refused_unchanged(
        composed_with_origin,
        capsys,
        WHAT_TREE_MISMATCH,
        {"why": [f"expected: {WRONG_SHA}"]},
        expected_tree=WRONG_SHA,
    )


@covers("trunk moved")
def test_integrate_a_valid_but_wrong_trunk_is_trunk_moved(composed_with_origin, capsys):
    assert_refused_unchanged(
        composed_with_origin,
        capsys,
        WHAT_TRUNK_MOVED,
        {"why": [f"expected: {WRONG_SHA}"]},
        expected_trunk=WRONG_SHA,
    )


# --- success -------------------------------------------------------------------


def test_integrate_without_a_remote_fast_forwards_trunk_and_removes_the_lane(
    composed_without_remote, capsys
):
    composed = composed_without_remote
    lane_head = git(composed.path, "rev-parse", "HEAD")

    code, out, err = run_integrate(composed, capsys)

    assert (code, err) == (0, "")
    assert_integrated(composed, lane_head)
    assert parse_output(out) == {
        "trunk": "main",
        "former-head": lane_head,
        "now-at": lane_head,
        "continue-in": str(composed.repo.path.resolve()),
        "recover": f"git branch {composed.name} {lane_head}",
        "pushed": "nothing; run git push yourself if wanted",
    }
    assert out.splitlines()[-1].startswith("pushed: nothing")


def test_integrate_on_a_remote_tracking_trunk_moves_only_the_local_branch(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    lane_head = git(composed.path, "rev-parse", "HEAD")
    origin_refs = git(composed.repo.origin, "for-each-ref")
    tracking = git(composed.repo.path, "rev-parse", "origin/main")

    code, out, err = run_integrate(composed, capsys, "--local-trunk")

    assert (code, err) == (0, "")
    assert_integrated(composed, lane_head)
    assert parse_output(out)["continue-in"] == str(composed.repo.path.resolve())
    assert git(composed.repo.origin, "for-each-ref") == origin_refs
    assert git(composed.repo.path, "rev-parse", "origin/main") == tracking
    assert lane_head != tracking


def ignore_a_file_the_lane_adds(composed: ComposedLane) -> Path:
    """The trunk worktree ignores `lane.txt` and holds a file of that name."""
    trunk_worktree = composed.repo.path
    exclude = Path(git(trunk_worktree, "rev-parse", "--git-path", "info/exclude"))
    exclude = trunk_worktree / exclude if not exclude.is_absolute() else exclude
    exclude.write_text("lane.txt\n", encoding="utf-8")
    precious = trunk_worktree / "lane.txt"
    precious.write_text("precious\n", encoding="utf-8")
    return precious


@covers("integrate step failed")
def test_integrate_never_overwrites_an_ignored_file_in_the_trunk_worktree(
    composed_without_remote, capsys
):
    composed = composed_without_remote
    precious = ignore_a_file_the_lane_adds(composed)
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "merge --ff-only" in block["why"]
    assert precious.read_text(encoding="utf-8") == "precious\n"
    assert observed_state(composed) == before


@covers("integrate step failed")
def test_integrate_never_overwriting_an_ignored_file_keeps_the_lane_and_its_branch(
    composed_without_remote, capsys
):
    composed = composed_without_remote
    ignore_a_file_the_lane_adds(composed)

    run_integrate(composed, capsys)

    assert_lane_kept(composed)


# --- each check refuses alone, through main ------------------------------------------


def fault_tree_mismatch(composed) -> list[str]:
    commit_in(composed.path, "later.txt")
    seed_gate(composed.path, composed.trunk_ref)
    return []


def fault_gate_deleted(composed) -> list[str]:
    (composed.path / GATE_RELATIVE_PATH).unlink()
    return []


def fault_trunk_moved(composed) -> list[str]:
    advance_origin(composed.repo)
    return []


def fault_untracked_file_in_lane(composed) -> list[str]:
    leave_untracked_file(composed.path)
    return []


def fault_local_trunk_ahead(composed) -> list[str]:
    advance_trunk(composed.repo)
    return []


def fault_trunk_checked_out_nowhere(composed) -> list[str]:
    git(composed.repo.path, "switch", "-q", "-c", "elsewhere")
    return []


def fault_dirty_trunk_worktree(composed) -> list[str]:
    edit_tracked_file(composed.repo.path)
    return []


def fault_trunk_is_a_tag(composed) -> list[str]:
    git(composed.repo.path, "tag", "v1", "origin/main")
    return ["--trunk", "v1"]


def fault_github_origin(composed) -> list[str]:
    use_github_origin(composed.repo)
    return []


@dataclass(frozen=True)
class Fault:
    """A fault to inject, the one refusal it gives, and what each field of the
    block must say."""

    inject: Callable[[ComposedLane], list[str]]
    what: str
    pinned: dict[str, tuple[str, ...]]
    gate_kept: bool = True


SINGLE_FAULTS = {
    "tree mismatch": Fault(
        fault_tree_mismatch,
        WHAT_TREE_MISMATCH,
        {"why": ("expected:", "live:"), "how": (COMPOSE_AGAIN,)},
    ),
    "gate deleted": Fault(
        fault_gate_deleted,
        WHAT_REVIEW_GATE,
        {"why": ("(rule: pre-pr-review)",), "how": ("/code-review --since",)},
        gate_kept=False,
    ),
    "trunk moved": Fault(
        fault_trunk_moved,
        WHAT_TRUNK_MOVED,
        {"why": ("expected:", "live:"), "how": (COMPOSE_AGAIN,)},
    ),
    "dirty lane": Fault(
        fault_untracked_file_in_lane,
        WHAT_UNCOMMITTED,
        {"why": ("scratch.txt",), "how": ("commit or stash",)},
    ),
    "not an ancestor": Fault(
        fault_local_trunk_ahead,
        WHAT_FAST_FORWARD,
        {"why": ("not an ancestor",), "how": ("run compose",)},
    ),
    "checked out nowhere": Fault(
        fault_trunk_checked_out_nowhere,
        WHAT_FAST_FORWARD,
        {"why": ("checked out nowhere",), "how": ("git switch main",)},
    ),
    "dirty trunk worktree": Fault(
        fault_dirty_trunk_worktree,
        WHAT_FAST_FORWARD,
        {"why": ("has uncommitted changes",), "how": ("clean the trunk worktree",)},
    ),
    "trunk is a tag": Fault(
        fault_trunk_is_a_tag,
        WHAT_FAST_FORWARD,
        {"why": ("does not exist",), "how": ("pass --trunk <branch>",)},
    ),
    "github origin": Fault(
        fault_github_origin,
        WHAT_PR_REPOSITORY,
        {"how": ("with /pr", "--local-trunk")},
    ),
}


@pytest.mark.parametrize(
    "fault_id",
    [
        pytest.param(fault_id, marks=covers(SINGLE_FAULTS[fault_id].what))
        for fault_id in sorted(SINGLE_FAULTS)
    ],
)
def test_integrate_each_fault_refuses_alone_and_changes_nothing(
    fault_id, composed_with_origin, capsys
):
    composed = composed_with_origin
    fault = SINGLE_FAULTS[fault_id]
    extra = fault.inject(composed)

    assert_refused_unchanged(composed, capsys, fault.what, fault.pinned, *extra)

    assert_lane_kept(composed, gate_kept=fault.gate_kept)


def test_integrate_a_fault_with_no_remote_reports_trunk_moved_then_fast_forward(
    composed_without_remote, capsys
):
    advance_trunk(composed_without_remote.repo)
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(composed_without_remote, capsys)

    blocks = parse_blocks(err)
    assert (code, out) == (1, "")
    assert [block["refused"] for block in blocks] == [
        WHAT_TRUNK_MOVED,
        WHAT_FAST_FORWARD,
    ]
    assert observed_state(composed_without_remote) == before


@covers("tree mismatch")
@covers("review gate stale or missing")
@covers("trunk moved")
def test_integrate_three_faults_are_reported_together_in_order(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    commit_in(composed.path, "later.txt")
    advance_origin(composed.repo)
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys)

    blocks = parse_blocks(err)
    assert (code, out) == (1, "")
    assert [block["refused"] for block in blocks] == [
        WHAT_TREE_MISMATCH,
        WHAT_REVIEW_GATE,
        WHAT_TRUNK_MOVED,
    ]
    assert observed_state(composed) == before


@covers("PR repository")
@covers("lane has uncommitted changes")
def test_integrate_a_pr_repository_refusal_alongside_others_ends_with_the_note(
    composed_with_origin, capsys
):
    fault_github_origin(composed_with_origin)
    leave_untracked_file(composed_with_origin.path)

    code, _, err = run_integrate(composed_with_origin, capsys)

    assert code == 1
    assert [block["refused"] for block in parse_blocks(err)] == [
        WHAT_UNCOMMITTED,
        WHAT_PR_REPOSITORY,
    ]
    assert err.rstrip().splitlines()[-1].startswith("note: this is a PR repository")


# --- where it runs ------------------------------------------------------------------


@pytest.mark.parametrize("place", NOT_A_LANE_PLACES)
@covers("not in a lane")
def test_integrate_a_place_that_is_not_a_lane_is_a_not_in_a_lane_block(
    place, composed_without_remote, capsys
):
    assert_refused_unchanged(
        composed_without_remote,
        capsys,
        WHAT_NOT_IN_A_LANE,
        {"how": ("lane.py open",)},
        cwd=place(composed_without_remote.repo),
    )


@covers("trunk ref cannot be resolved")
def test_integrate_an_unresolvable_trunk_is_exactly_one_block(
    composed_without_remote, capsys
):
    leave_untracked_file(composed_without_remote.path)

    assert_refused_unchanged(
        composed_without_remote,
        capsys,
        "trunk ref cannot be resolved",
        {"why": ("nonexistent-ref",)},
        "--trunk",
        "nonexistent-ref",
    )


@covers("not a git repository")
def test_integrate_outside_a_repository_is_a_block_not_a_traceback(
    composed_without_remote, plain_directory, capsys
):
    code, out, err = run_integrate(composed_without_remote, capsys, cwd=plain_directory)

    block = single_refusal(code, out, err, "not a git repository")
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


# --- the apply sequence --------------------------------------------------------------


def apply_trace(composed: ComposedLane, capsys, monkeypatch):
    """Run integrate; return what each git call saw: `(git arguments, cwd, gate
    file present, lane directory present)` at the moment it started, from the
    fast-forward on."""
    gate = composed.path / GATE_RELATIVE_PATH
    seen = []
    GitFailure(
        monkeypatch,
        [],
        nth=None,
        then=lambda argv, cwd: seen.append(
            (argv[1:], cwd.resolve(), gate.exists(), composed.path.exists())
        ),
    )
    code, _, err = run_integrate(composed, capsys)
    assert (code, err) == (0, "")
    start = next(
        i for i, call in enumerate(seen) if call[0][:2] == ["merge", "--ff-only"]
    )
    return seen[start:]


def test_integrate_applies_fast_forward_then_gate_then_worktree_then_branch(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    trunk = composed.repo.path.resolve()
    lane_head = git(composed.path, "rev-parse", "HEAD")

    trace = apply_trace(composed, capsys, monkeypatch)

    steps = [
        call for call in trace if call[0][0] in ("merge", "worktree", "update-ref")
    ]
    assert [call[0] for call in steps] == [
        ["merge", "--ff-only", "--no-overwrite-ignore", lane_head],
        ["worktree", "remove", str(composed.path)],
        ["update-ref", "-d", f"refs/heads/{composed.name}", lane_head],
    ]
    assert {call[1] for call in trace} == {trunk}
    ff, remove, delete = steps
    # (gate present, lane present) when each step started
    assert (ff[2], ff[3]) == (True, True)
    assert (remove[2], remove[3]) == (False, True)
    assert (delete[2], delete[3]) == (False, False)


# --- the apply is bound to what the checks saw ------------------------------------------

#: The lane's HEAD is read once by the checks and once more by the plan; these
#: are the arguments of that read, and the plan's is the second.
READ_LANE_HEAD = ["rev-parse", "--verify", "HEAD^{commit}"]
PLAN_READS_THE_LANE_HEAD_SECOND = 2


@covers("tree mismatch")
def test_integrate_a_lane_that_moved_after_the_checks_is_refused_untouched(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    trunk_before = git(composed.repo.path, "rev-parse", TRUNK)
    raced = GitFailure(
        monkeypatch,
        READ_LANE_HEAD,
        nth=PLAN_READS_THE_LANE_HEAD_SECOND,
        cwd=composed.path,
        then=lambda _argv, _cwd: commit_in(composed.path),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert len(raced.matching) == PLAN_READS_THE_LANE_HEAD_SECOND, "no race"
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_TREE_MISMATCH
    assert f"expected: {composed.expected_tree}" in block["why"]
    assert git(composed.repo.path, "rev-parse", TRUNK) == trunk_before
    assert_lane_kept(composed)


@covers("tree mismatch")
def test_integrate_a_lane_commit_with_the_reviewed_tree_says_the_commit_moved(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    checked_head = git(composed.path, "rev-parse", "HEAD")
    GitFailure(
        monkeypatch,
        READ_LANE_HEAD,
        nth=PLAN_READS_THE_LANE_HEAD_SECOND,
        cwd=composed.path,
        then=lambda _argv, _cwd: git(
            composed.path, "commit", "-q", "--allow-empty", "-m", "same tree"
        ),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_TREE_MISMATCH
    assert "HEAD commit moved" in block["why"]
    assert checked_head in block["why"]
    assert "expected:" not in block["why"], "equal trees must not be called a mismatch"
    assert git(composed.repo.path, "rev-parse", TRUNK) == composed.expected_trunk


@covers("trunk moved")
def test_integrate_a_trunk_ref_that_moved_after_the_checks_is_refused_untouched(
    composed_with_origin, capsys, monkeypatch
):
    composed = composed_with_origin
    checks_resolve_the_trunk_first_and_the_plan_second = 2
    raced = GitFailure(
        monkeypatch,
        ["rev-parse", "--verify", "--quiet", "origin/main^{commit}"],
        nth=checks_resolve_the_trunk_first_and_the_plan_second,
        then=lambda _argv, _cwd: advance_origin(composed.repo),
    )
    main_before = git(composed.repo.path, "rev-parse", TRUNK)

    code, out, err = run_integrate(composed, capsys, "--local-trunk")

    (block,) = parse_blocks(err)
    assert len(raced.matching) == checks_resolve_the_trunk_first_and_the_plan_second
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_TRUNK_MOVED
    assert f"expected: {composed.expected_trunk}" in block["why"]
    assert git(composed.repo.path, "rev-parse", TRUNK) == main_before
    assert_lane_kept(composed)


@covers("integrate step failed")
def test_integrate_a_commit_added_after_the_plan_is_kept_on_the_lane_branch(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    lane_head = git(composed.path, "rev-parse", "HEAD")
    sneaked: list[str] = []
    GitFailure(
        monkeypatch,
        ["merge", "--ff-only"],
        then=lambda _argv, _cwd: sneaked.append(commit_in(composed.path)),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "update-ref" in block["why"]
    assert git(composed.repo.path, "rev-parse", TRUNK) == lane_head, (
        "trunk got the commit"
    )
    assert (
        git(composed.repo.path, "rev-parse", f"refs/heads/{composed.name}")
        == sneaked[0]
    )
    assert report_lines(err, "done") == [
        "fast-forward",
        "gate file removal",
        "worktree removal",
    ]


@covers("trunk cannot fast-forward")
def test_integrate_a_second_lane_whose_trunk_moved_during_its_checks_is_told_to_compose(
    repo_without_remote, capsys, monkeypatch
):
    repo = repo_without_remote
    first = composed_gated_lane(repo, capsys, name="first", lane_file="first.txt")
    second = composed_gated_lane(repo, capsys, name="second", lane_file="second.txt")
    first_head = git(first.path, "rev-parse", "HEAD")
    second_head = git(second.path, "rev-parse", "HEAD")
    second_status = git(second.path, "status", "--porcelain=v1", "--ignored")

    def first_lane_integrates_meanwhile(_argv, _cwd):
        code, _, err = run_integrate(first, capsys)
        assert (code, err) == (0, "")

    raced = GitFailure(
        monkeypatch,
        ["merge", "--ff-only"],
        cwd=repo.path,
        then=first_lane_integrates_meanwhile,
    )

    code, out, err = run_integrate(second, capsys)

    (block,) = parse_blocks(err)
    assert len(raced.matching) >= 1
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_FAST_FORWARD
    assert "not an ancestor" in block["why"]
    assert "run compose" in block["how"]
    assert report_lines(err, "done") == []
    assert report_lines(err, "remaining") == []
    assert git(repo.path, "rev-parse", TRUNK) == first_head
    assert second.path.exists()
    assert branch_exists_in(repo.path, second.name)
    assert git(second.path, "rev-parse", "HEAD") == second_head
    assert git(second.path, "status", "--porcelain=v1", "--ignored") == second_status
    assert (second.path / GATE_RELATIVE_PATH).exists()


@covers("trunk cannot fast-forward")
def test_integrate_a_trunk_worktree_switched_before_the_fast_forward_is_refused_untouched(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    main_before = git(composed.repo.path, "rev-parse", TRUNK)
    raced = GitFailure(
        monkeypatch,
        ["symbolic-ref", "-q", "HEAD"],
        cwd=composed.repo.path,
        then=lambda _argv, _cwd: git(composed.repo.path, "switch", "-q", "-c", "other"),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert len(raced.matching) == 1, "no race"
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_FAST_FORWARD
    assert "no longer has main checked out" in block["why"]
    assert report_lines(err, "done") == []
    assert git(composed.repo.path, "rev-parse", TRUNK) == main_before
    assert git(composed.repo.path, "rev-parse", "other") == main_before
    assert_lane_kept(composed)


@covers("integrate step failed")
def test_integrate_a_trunk_worktree_switched_during_the_fast_forward_deletes_nothing(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    lane_head = git(composed.path, "rev-parse", "HEAD")
    main_before = git(composed.repo.path, "rev-parse", TRUNK)
    GitFailure(
        monkeypatch,
        ["merge", "--ff-only"],
        cwd=composed.repo.path,
        then=lambda _argv, _cwd: git(composed.repo.path, "switch", "-q", "-c", "other"),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert f"main is at {main_before}" in block["why"]
    assert report_lines(err, "remaining") == [], "no command is safe to run by hand"
    assert report_lines(err, "recover") == [recover_command(composed, lane_head)]
    assert git(composed.repo.path, "rev-parse", TRUNK) == main_before
    assert git(composed.repo.path, "rev-parse", "other") == lane_head
    assert_lane_kept(composed)


# --- branch deletion: ancestry, not upstream; guarded by the old value --------------


def set_upstream_behind_the_lane(composed) -> None:
    """The lane tracks `origin/<lane>`, a remote-tracking ref that lacks its
    commit: what `git push -u` leaves behind, made without a push."""
    repo = composed.repo.path
    base = git(repo, "rev-parse", "origin/main")
    git(repo, "config", f"branch.{composed.name}.remote", "origin")
    git(repo, "config", f"branch.{composed.name}.merge", f"refs/heads/{composed.name}")
    git(repo, "update-ref", f"refs/remotes/origin/{composed.name}", base)


def test_integrate_deletes_a_lane_branch_whose_upstream_does_not_contain_it(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    lane_head = git(composed.path, "rev-parse", "HEAD")
    set_upstream_behind_the_lane(composed)

    code, _out, err = run_integrate(composed, capsys, "--local-trunk")

    assert (code, err) == (0, "")
    assert_integrated(composed, lane_head)


@covers("integrate step failed")
def test_integrate_does_not_delete_a_lane_branch_that_moved_after_the_plan(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    repo = composed.repo.path
    elsewhere = git(repo, "rev-parse", TRUNK)
    GitFailure(
        monkeypatch,
        ["update-ref", "-d"],
        then=lambda _argv, _cwd: git(
            repo, "update-ref", f"refs/heads/{composed.name}", elsewhere
        ),
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "update-ref" in block["why"]
    assert git(repo, "rev-parse", f"refs/heads/{composed.name}") == elsewhere


@covers("integrate step failed")
def test_integrate_does_not_delete_a_branch_the_trunk_does_not_contain(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    repo = composed.repo.path
    lane_head = git(composed.path, "rev-parse", "HEAD")
    # The trunk branch is put back where it was, after the fast-forward ran.
    GitFailure(
        monkeypatch,
        ["worktree", "remove"],
        then=lambda _argv, _cwd: git(
            repo, "update-ref", f"refs/heads/{TRUNK}", composed.expected_trunk
        ),
    )
    deletions = GitFailure(
        monkeypatch, ["update-ref", "-d"], nth=None, then=lambda _argv, _cwd: None
    )

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "is not contained in main" in block["why"]
    assert "kept because the trunk branch does not contain" in block["how"]
    assert git(repo, "rev-parse", f"refs/heads/{composed.name}") == lane_head
    assert deletions.matching == [], "the deletion was attempted"
    assert report_lines(err, "done") == [
        "fast-forward",
        "gate file removal",
        "worktree removal",
    ]
    assert report_lines(err, "remaining") == [], "no command would be safe to run"
    assert report_lines(err, "recover") == [recover_command(composed, lane_head)]


def test_integrate_checks_the_trunk_branch_not_the_branch_the_trunk_worktree_holds_now(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    repo = composed.repo.path
    GitFailure(
        monkeypatch,
        ["worktree", "remove"],
        then=lambda _argv, _cwd: git(
            repo, "switch", "-q", "-c", "behind", composed.expected_trunk
        ),
    )
    lane_head = git(composed.path, "rev-parse", "HEAD")

    code, _out, err = run_integrate(composed, capsys)

    assert (code, err) == (0, "")
    assert git(repo, "rev-parse", TRUNK) == lane_head
    assert not branch_exists_in(repo, composed.name)


# --- success lines come from git: control characters are shown escaped --------------


# These two call the printing functions directly, because a control character in
# a path cannot be made through a real lane: `lane_core` reads the paths of
# `git rev-parse` line by line, so a lane whose repository path holds a newline
# fails before it gets here.


def test_the_success_lines_show_control_characters_escaped(capsys):
    plan = lane.IntegratePlan(
        lane_path=Path("/lane"),
        lane_branch="feature\x1b[2Jx",
        trunk_ref="main",
        trunk_branch="ma\nin",
        trunk_worktree=Path("/trunk\nwhere"),
        former_head="a" * 40,
        gate_file=Path("/lane/gate"),
    )

    lane._print_integrated(plan)

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\x1b[2J" in out
    assert "continue-in: /trunk\\x0awhere" in out
    assert len(out.splitlines()) == 6
    assert out.splitlines()[-1].startswith("pushed: nothing")


def test_the_done_and_remaining_lines_show_control_characters_escaped(capsys):
    refusal = lane_core.integrate_step_failed_refusal("worktree removal", "git x", "no")
    failed = lane.ApplyFailed(
        refusal,
        done=["fast-forward"],
        remaining=["git -C /trunk\nremaining: forged"],
        recover="git branch a\nrecover: forged b",
    )

    assert lane._emit_apply_failure(failed) == 1

    err = capsys.readouterr().err
    assert report_lines(err, "remaining") == ["git -C /trunk\\x0aremaining: forged"]
    assert report_lines(err, "recover") == ["git branch a\\x0arecover: forged b"]


# --- the gate file: only inside the lane; a failure is a step failure ---------------


def move_memory_outside_the_lane(composed: ComposedLane, tmp_path: Path) -> Path:
    """`.claude/memory` becomes a symlink to a directory outside the lane; the
    gate file is then someone else's. Returns that directory."""
    memory = composed.path / ".claude" / "memory"
    outside = tmp_path / "shared-memory"
    memory.rename(outside)
    memory.symlink_to(outside, target_is_directory=True)
    return outside


def test_integrate_leaves_a_gate_file_that_lives_outside_the_lane(
    composed_without_remote, tmp_path, capsys
):
    composed = composed_without_remote
    outside = move_memory_outside_the_lane(composed, tmp_path)
    gate_bytes = (outside / GATE_RELATIVE_PATH.name).read_bytes()

    code, _, err = run_integrate(composed, capsys)

    assert (code, err) == (0, "")
    assert (outside / GATE_RELATIVE_PATH.name).read_bytes() == gate_bytes
    assert not composed.path.exists()


@covers("integrate step failed")
@pytest.mark.parametrize(
    "failure",
    [PermissionError("denied"), IsADirectoryError("is a directory")],
    ids=["permission", "is a directory"],
)
def test_integrate_a_gate_file_that_cannot_be_removed_is_a_step_failure(
    failure, composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    gate = composed.path / GATE_RELATIVE_PATH
    unlink = fail_unlink_of(monkeypatch, gate, failure)

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert str(gate) in block["why"]
    assert str(failure) in block["why"]
    assert unlink.attempts == 1
    assert composed.path.exists()


@covers("integrate step failed")
def test_integrate_a_gate_directory_that_loops_is_a_step_failure_not_a_traceback(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    memory = composed.path / ".claude" / "memory"

    def memory_becomes_a_symlink_loop(_argv, _cwd):
        shutil.rmtree(memory)
        memory.symlink_to("memory")

    GitFailure(monkeypatch, ["merge", "--ff-only"], then=memory_becomes_a_symlink_loop)
    lane_head = git(composed.path, "rev-parse", "HEAD")

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert block["why"].startswith("gate file removal failed")
    assert "Traceback" not in err
    assert report_lines(err, "done") == ["fast-forward"]
    assert git(composed.repo.path, "rev-parse", TRUNK) == lane_head
    assert composed.path.exists()


# --- a failing apply step reports what is done and what remains ---------------------


def apply_commands(composed: ComposedLane, head: str) -> dict[str, str]:
    """Every apply command, as `remaining:` shows it. The branch deletion is
    printed with the containment check `integrate` itself makes first."""
    trunk = composed.repo.path.resolve()
    return {
        "merge": f"git -C {trunk} merge --ff-only --no-overwrite-ignore {head}",
        "rm": f"rm -- {composed.path / GATE_RELATIVE_PATH}",
        "worktree": f"git -C {trunk} worktree remove {composed.path}",
        "update-ref": (
            f"git -C {trunk} merge-base --is-ancestor {head} refs/heads/{TRUNK}"
            f" && git -C {trunk} update-ref -d refs/heads/{composed.name} {head}"
        ),
    }


def recover_command(composed: ComposedLane, head: str) -> str:
    return f"git branch {composed.name} {head}"


def fail_git_step(prefix: list[str]):
    def inject(composed, monkeypatch) -> Callable[[], int]:
        failure = GitFailure(monkeypatch, prefix)
        return lambda: len(failure.matching)

    return inject


def fail_the_gate_removal(composed, monkeypatch) -> Callable[[], int]:
    failure = fail_unlink_of(
        monkeypatch, composed.path / GATE_RELATIVE_PATH, PermissionError("denied")
    )
    return lambda: failure.attempts


def keep_memory_in_the_lane(composed: ComposedLane, tmp_path: Path) -> None:
    """The default arrangement: nothing to prepare."""


def keep_memory_outside_the_lane(composed: ComposedLane, tmp_path: Path) -> None:
    move_memory_outside_the_lane(composed, tmp_path)


@dataclass(frozen=True)
class FailingStep:
    """One row: how a step fails and exactly what the report and the repository
    show afterwards. `remaining` names the commands of `apply_commands`."""

    inject: Callable
    detail: str
    done: tuple[str, ...]
    remaining: tuple[str, ...]
    gate_present: bool
    trunk_moved: bool
    lane_exists: bool
    prepare: Callable[[ComposedLane, Path], None] = keep_memory_in_the_lane


ALL_COMMANDS = ("merge", "rm", "worktree", "update-ref")

FAILING_STEPS = {
    "fast-forward": FailingStep(
        fail_git_step(["merge", "--ff-only"]),
        "injected failure",
        done=(),
        remaining=ALL_COMMANDS,
        gate_present=True,
        trunk_moved=False,
        lane_exists=True,
    ),
    "gate unlink": FailingStep(
        fail_the_gate_removal,
        "denied",
        done=("fast-forward",),
        remaining=("rm", "worktree", "update-ref"),
        gate_present=True,
        trunk_moved=True,
        lane_exists=True,
    ),
    "worktree removal": FailingStep(
        fail_git_step(["worktree", "remove"]),
        "injected failure",
        done=("fast-forward", "gate file removal"),
        remaining=("worktree", "update-ref"),
        gate_present=False,
        trunk_moved=True,
        lane_exists=True,
    ),
    "branch deletion": FailingStep(
        fail_git_step(["update-ref", "-d"]),
        "injected failure",
        done=("fast-forward", "gate file removal", "worktree removal"),
        remaining=("update-ref",),
        gate_present=False,
        trunk_moved=True,
        lane_exists=False,
    ),
    "fast-forward, gate file outside the lane": FailingStep(
        fail_git_step(["merge", "--ff-only"]),
        "injected failure",
        done=(),
        remaining=("merge", "worktree", "update-ref"),
        gate_present=True,
        trunk_moved=False,
        lane_exists=True,
        prepare=keep_memory_outside_the_lane,
    ),
    "worktree removal, gate file outside the lane": FailingStep(
        fail_git_step(["worktree", "remove"]),
        "injected failure",
        done=("fast-forward",),
        remaining=("worktree", "update-ref"),
        gate_present=True,
        trunk_moved=True,
        lane_exists=True,
        prepare=keep_memory_outside_the_lane,
    ),
    # The worktree removal takes the `.claude/memory` symlink with it. The gate
    # step still did nothing, so `done:` must not claim it.
    "branch deletion, gate file outside the lane": FailingStep(
        fail_git_step(["update-ref", "-d"]),
        "injected failure",
        done=("fast-forward", "worktree removal"),
        remaining=("update-ref",),
        gate_present=False,
        trunk_moved=True,
        lane_exists=False,
        prepare=keep_memory_outside_the_lane,
    ),
}


def assert_apply_state(
    composed: ComposedLane,
    err: str,
    head: str,
    row: FailingStep,
    attempts: int,
    failing_step: str,
) -> None:
    """The failure block, the `done:` and `remaining:` lines, and the repository
    all match `row`. Every message names the part that is wrong."""
    commands = apply_commands(composed, head)
    (block,) = parse_blocks(err)
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED, failing_step
    assert "re-running integrate is not the fix" in block["how"], failing_step
    assert row.detail in block["why"], f"{failing_step}: git's own message is missing"
    assert report_lines(err, "done") == (list(row.done) or ["nothing"]), failing_step
    assert report_lines(err, "remaining") == [commands[key] for key in row.remaining], (
        f"{failing_step}: remaining commands"
    )
    assert report_lines(err, "recover") == [recover_command(composed, head)], (
        f"{failing_step}: recover command"
    )
    assert block["why"].count("(command: ") == 1, failing_step
    assert commands[row.remaining[0]] in block["why"], f"{failing_step}: failed command"
    assert attempts == 1, (
        f"{failing_step}: the failing call was attempted {attempts} times"
    )
    gate = composed.path / GATE_RELATIVE_PATH
    assert gate.exists() == row.gate_present, f"{failing_step}: gate file"
    assert (git(composed.repo.path, "rev-parse", TRUNK) == head) == row.trunk_moved, (
        f"{failing_step}: trunk"
    )
    assert composed.path.exists() == row.lane_exists, f"{failing_step}: lane directory"
    assert branch_exists_in(composed.repo.path, composed.name), (
        f"{failing_step}: branch"
    )


@pytest.mark.parametrize(
    "step",
    [
        pytest.param(step, marks=covers("integrate step failed"))
        for step in FAILING_STEPS
    ],
)
def test_integrate_a_failing_step_reports_done_and_remaining(
    step, composed_without_remote, tmp_path, capsys, monkeypatch
):
    composed = composed_without_remote
    row = FAILING_STEPS[step]
    head = git(composed.path, "rev-parse", "HEAD")
    row.prepare(composed, tmp_path)
    attempts = row.inject(composed, monkeypatch)

    code, out, err = run_integrate(composed, capsys)

    assert (code, out) == (1, "")
    assert_apply_state(composed, err, head, row, attempts(), step)


@covers("integrate step failed")
def test_integrate_an_interrupt_during_the_worktree_removal_reports_then_propagates(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    head = git(composed.path, "rev-parse", "HEAD")
    commands = apply_commands(composed, head)
    GitFailure(monkeypatch, ["worktree", "remove"], raises=KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        lane.main(integrate_argv(composed), cwd=composed.path)

    err = capsys.readouterr().err
    (block,) = parse_blocks(err)
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "KeyboardInterrupt" in block["why"]
    assert report_lines(err, "done") == ["fast-forward", "gate file removal"]
    assert report_lines(err, "remaining") == [
        commands["worktree"],
        commands["update-ref"],
    ]
    assert report_lines(err, "recover") == [recover_command(composed, head)]
    assert git(composed.repo.path, "rev-parse", TRUNK) == head


@covers("integrate step failed")
def test_integrate_an_unexpected_error_in_a_step_is_a_step_failure_not_a_traceback(
    composed_without_remote, capsys, monkeypatch
):
    composed = composed_without_remote
    GitFailure(monkeypatch, ["worktree", "remove"], raises=ValueError("odd failure"))

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == WHAT_INTEGRATE_STEP_FAILED
    assert "ValueError: odd failure" in block["why"]
    assert report_lines(err, "done") == ["fast-forward", "gate file removal"]


# --- full flows -------------------------------------------------------------------------


def test_a_second_lane_integrates_after_the_first(repo_with_origin, capsys):
    repo = repo_with_origin
    first = composed_gated_lane(repo, capsys, name="first", lane_file="first.txt")
    code, _, err = run_integrate(first, capsys, "--local-trunk")
    assert (code, err) == (0, "")
    assert git(repo.path, "rev-parse", TRUNK) != git(
        repo.path, "rev-parse", "origin/main"
    )

    second = composed_gated_lane(repo, capsys, name="second", lane_file="second.txt")
    second_head = git(second.path, "rev-parse", "HEAD")
    code, _out, err = run_integrate(second, capsys, "--local-trunk")

    assert (code, err) == (0, "")
    assert_trunk_at_lane_head(second, second_head)
    assert (repo.path / "first.txt").is_file()
    assert (repo.path / "second.txt").is_file()
    assert not second.path.exists()


def test_a_github_origin_integrates_end_to_end_with_local_trunk_and_no_network(
    tmp_path, capsys, argv_spy
):
    composed = build_composed_with_github_origin(tmp_path, capsys)
    lane_head = git(composed.path, "rev-parse", "HEAD")
    start = len(argv_spy.records)

    code, _out, err = run_integrate(composed, capsys, "--local-trunk")

    assert (code, err) == (0, "")
    assert_integrated(composed, lane_head)
    network = [
        argv
        for argv in argv_spy.records[start:]
        for prefix in NETWORK_ARGV_PREFIXES
        if argv[: len(prefix)] == prefix
    ]
    assert network == []


def test_the_real_script_runs_from_inside_the_lane_it_removes(
    composed_without_remote,
):
    """The one test with a real child process: `argv_spy` cannot see its git calls."""
    composed = composed_without_remote
    head = git(composed.path, "rev-parse", "HEAD")
    script = SCRIPTS_DIR / "lane.py"

    done = subprocess.run(
        [sys.executable, str(script), *integrate_argv(composed)],
        cwd=composed.path,
        env=git_env(composed.path),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert (done.returncode, done.stderr) == (0, "")
    assert parse_output(done.stdout)["former-head"] == head
    assert_integrated(composed, head)


def test_the_pr_hook_accepts_a_lane_composed_against_a_bare_origin(
    repo_with_origin, capsys, monkeypatch
):
    composed = composed_gated_lane(repo_with_origin, capsys, gate=False)
    # The trunk is written out, not read from the composed lane: the hook must
    # accept the lane against the real `origin/main`.
    seed_gate(composed.path, "origin/main")

    assert hook_exit_code(composed, monkeypatch) == 0
    assert not (composed.path / GATE_RELATIVE_PATH).exists(), (
        "the hook did not consume the gate"
    )
