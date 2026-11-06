"""Tests for the `lane.py integrate` check engine (`lane.check_lane`).

The `test_refusals_for_*` tests drive the checks through `refusals_for` (the refusals
`check_lane` gives) and print them with `lane_core.emit_refusals`. A check
changes nothing. The gate parity table runs the PR hook's own `main()` beside the
lane's gate check.

Every test runs in-process against real git repositories built by
`lane_fixtures` and `lane_fixtures_integrate`. The `integrate` command itself is
tested in `test_lane_integrate_command.py`, and the source-text pins in
`test_lane_structure.py`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from lane_fixtures import (
    COMPOSE_AGAIN,
    GITHUB_URL,
    NOT_A_LANE_PLACES,
    TRUNK,
    GitFailure,
    add_linked_worktree,
    advance_origin,
    advance_trunk,
    argv_spy,
    build_repo_without_remote,
    covers,
    enforce_covers,
    git,
    git_calls_since,
    hermetic_process_env,
    plain_directory,
    repo_with_origin,
    repo_without_remote,
)
from lane_fixtures_integrate import (
    GATE_RELATIVE_PATH,
    LOOKALIKE_URL,
    ComposedLane,
    build_composed_with_github_origin,
    build_composed_with_other_origin,
    build_composed_without_remote,
    commit_in,
    composed_gated_lane,
    composed_with_origin,
    composed_without_remote,
    edit_tracked_file,
    gate_hash_of,
    hook_block_rule,
    hook_exit_code,
    leave_untracked_file,
    load_pr_hook,
    observed_state,
    only_block,
    printed_blocks,
    refusals_for,
    seed_binary_garbage,
    seed_different_content,
    seed_dispatch_failure,
    seed_dispatches_for_other_content,
    seed_doc_only_exemption,
    seed_gate,
    seed_gate_is_a_directory,
    seed_hash_and_empty_ledger,
    seed_hash_only,
    seed_legacy_location_only,
    seed_missing,
    seed_old_dispatches,
    seed_one_dispatch,
    seed_two_dispatches,
)

from _repo_root import REPO_ROOT

# `lane_fixtures` puts the lane scripts and `hooks/lib` on `sys.path`; import
# them after it.
# isort: split

import lane
import lane_core
import review_agent_registry

# The `what` strings are written out here, not read from lane_core: the tests
# are an oracle independent of the code they check.
WHAT_NOT_IN_A_LANE = "not in a lane"
WHAT_UNCOMMITTED = "lane has uncommitted changes"
WHAT_REVIEW_GATE = "review gate stale or missing"
WHAT_TREE_MISMATCH = "tree mismatch"
WHAT_TRUNK_MOVED = "trunk moved"
WHAT_FAST_FORWARD = "trunk cannot fast-forward"
WHAT_PR_REPOSITORY = "PR repository"
WHAT_GIT_FAILED = "git command failed"

#: How a git call that cannot answer at all looks.
GIT_CANNOT_ANSWER = {"exit_code": 128, "stderr": "fatal: injected\n"}


@pytest.fixture
def stand_in_hook(tmp_path, monkeypatch):
    """Install a file as the PR hook wherever `lane.py` loads it.

    The hook is loaded by path from a constant, so a file on disk stands in for
    it: a failure only the hook can have is then real code running, not a
    patched function. The preamble gives the stand-in the names `lane.py` reads.
    """
    preamble = (
        "from review_gate_hash import branch_diff_gate_hash\n"
        '_GATE_FILE_NAME = ".pr-review-passed"\n'
    )

    def install(body: str, with_preamble: bool = True) -> None:
        path = tmp_path / "stand_in_pr_hook.py"
        path.write_text((preamble if with_preamble else "") + body, encoding="utf-8")
        monkeypatch.setattr(lane, "PR_HOOK_PATH", path)

    return install


# --- the engine --------------------------------------------------------------


def test_a_composed_lane_with_an_origin_in_good_standing_has_no_refusals(
    composed_with_origin,
):
    assert refusals_for(composed_with_origin) == []


def test_a_composed_lane_without_a_remote_in_good_standing_has_no_refusals(
    composed_without_remote,
):
    assert refusals_for(composed_without_remote) == []


def test_the_checks_are_registered_in_strictly_increasing_order():
    orders = [check.order for check in lane.CHECKS]

    assert orders == sorted(set(orders))


# --- check 1: the tree is the reviewed tree ----------------------------------


@covers("tree mismatch")
def test_refusals_for_a_lane_commit_after_compose_is_a_tree_mismatch_alone(
    composed_with_origin, capsys
):
    old_tree = composed_with_origin.expected_tree
    commit_in(composed_with_origin.path, "later.txt")
    seed_gate(composed_with_origin.path, composed_with_origin.trunk_ref)
    live_tree = git(composed_with_origin.path, "rev-parse", "HEAD^{tree}")

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_TREE_MISMATCH
    assert f"expected: {old_tree}" in block["why"]
    assert f"live: {live_tree}" in block["why"]
    assert "/code-review --since origin/main" in block["how"]
    assert COMPOSE_AGAIN in block["how"]


def test_refusals_for_check_1_compares_the_tree_of_the_head_it_read_once(
    composed_without_remote, monkeypatch
):
    composed = composed_without_remote
    head_read = git(composed.path, "rev-parse", "HEAD")
    # The lane gains a commit after its HEAD was read, before check 1 asks for
    # the tree of that commit.
    raced = GitFailure(
        monkeypatch,
        ["rev-parse", "--verify", f"{head_read}^{{tree}}"],
        then=lambda _argv, _cwd: commit_in(composed.path),
    )

    refusals = refusals_for(composed)

    assert len(raced.matching) == 1, "the race did not happen"
    assert git(composed.path, "rev-parse", "HEAD") != head_read
    assert WHAT_TREE_MISMATCH not in [refusal.what for refusal in refusals]


# --- check 2: the review gate -------------------------------------------------


def test_loading_the_hook_for_parity_leaves_sys_path_as_it_was():
    before = list(sys.path)

    load_pr_hook()

    assert sys.path == before


def test_the_checks_leave_sys_path_as_it_was(composed_with_origin):
    before = list(sys.path)

    refusals_for(composed_with_origin)

    assert sys.path == before


@covers("review gate stale or missing")
def test_refusals_for_a_deleted_gate_file_is_the_review_gate_block_alone(
    composed_with_origin, capsys
):
    (composed_with_origin.path / GATE_RELATIVE_PATH).unlink()

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "/code-review --since origin/main" in block["how"]
    assert "(rule: pre-pr-review)" in block["why"]


def test_a_gate_that_passes_is_left_in_place(composed_with_origin):
    gate = composed_with_origin.path / GATE_RELATIVE_PATH
    before = gate.read_bytes()

    assert refusals_for(composed_with_origin) == []

    assert gate.read_bytes() == before


@dataclass(frozen=True)
class GateState:
    """One state of the gate: how to seed it, the one lane file, and the hook's
    `matched_rule` when it blocks (None when it accepts)."""

    seed: Callable[[ComposedLane, str], None]
    lane_file: str
    hook_rule: str | None


#: The hook blocks, and the lane's check blocks with the same rule.
BLOCKING_GATE_STATES = {
    "missing gate file": GateState(seed_missing, "lane.txt", "pre-pr-review"),
    "gate hash for different content": GateState(
        seed_different_content, "lane.txt", "pre-pr-review"
    ),
    "right hash, no dispatches": GateState(
        seed_hash_and_empty_ledger, "lane.txt", "dispatch-evidence-missing"
    ),
    "right hash, no ledger file": GateState(
        seed_hash_only, "lane.txt", "dispatch-ledger-read-failure"
    ),
    "right hash, dispatches older than the window": GateState(
        seed_old_dispatches, "lane.txt", "dispatch-evidence-stale"
    ),
    "right hash, dispatches for other content": GateState(
        seed_dispatches_for_other_content,
        "lane.txt",
        "dispatch-evidence-different-content",
    ),
    "right hash, dispatch-failure veto": GateState(
        seed_dispatch_failure, "lane.txt", "dispatch-failure-veto"
    ),
    "gate file is a directory": GateState(
        seed_gate_is_a_directory, "lane.txt", "pre-pr-review"
    ),
    "gate file is binary garbage": GateState(
        seed_binary_garbage, "lane.txt", "pre-pr-review"
    ),
}

#: The hook accepts, and the lane's check accepts.
ACCEPTING_GATE_STATES = {
    "right hash, one dispatch": GateState(seed_one_dispatch, "lane.txt", None),
    "right hash, two distinct dispatches": GateState(
        seed_two_dispatches, "lane.txt", None
    ),
    "right hash, doc-only exemption": GateState(
        seed_doc_only_exemption, "notes.md", None
    ),
}

LEGACY_GATE_PATH = Path("memory") / ".pr-review-passed"


def seeded_lane(repo, capsys, state: GateState) -> ComposedLane:
    """A composed lane with no gate, then `state` seeded on it."""
    composed = composed_gated_lane(repo, capsys, gate=False, lane_file=state.lane_file)
    state.seed(composed, gate_hash_of(composed.path, composed.trunk_ref))
    return composed


def review_gate_blocks(composed: ComposedLane, capsys) -> list[dict[str, str]]:
    """The printed review-gate blocks among the checks' refusals for `composed`."""
    refusals = [
        item for item in refusals_for(composed) if item.what == WHAT_REVIEW_GATE
    ]
    return printed_blocks(refusals, capsys)


def assert_hook_accepts_and_lane_agrees(composed, capsys, monkeypatch) -> None:
    """The hook's `main()` accepts (and so consumes the gate file, which proves it
    got as far as the evaluation); the lane's gate check finds nothing to refuse."""
    gate = composed.path / GATE_RELATIVE_PATH
    before = observed_state(composed)

    lane_blocks = review_gate_blocks(composed, capsys)
    assert observed_state(composed) == before, "the lane's check changed something"

    assert hook_exit_code(composed, monkeypatch) == 0, "the hook blocked"
    assert lane_blocks == [], "the lane refused what the hook accepts"
    assert not gate.exists(), "an accepting hook consumes the gate file"


def assert_hook_blocks_and_lane_agrees(
    composed, hook_rule, capsys, monkeypatch
) -> None:
    """The hook's `main()` blocks with `hook_rule` and leaves the gate file as it
    was; the lane's gate check gives one block that names the same rule, in the
    lane's words."""
    gate = composed.path / GATE_RELATIVE_PATH
    had_gate = gate.exists()
    before = observed_state(composed)

    lane_blocks = review_gate_blocks(composed, capsys)
    assert observed_state(composed) == before, "the lane's check changed something"

    assert hook_exit_code(composed, monkeypatch) != 0, "the hook accepted"
    assert gate.exists() == had_gate, "a blocking hook changed the gate file"
    assert hook_block_rule(composed) == hook_rule
    (block,) = lane_blocks
    assert f"(rule: {hook_rule})" in block["why"]
    assert "PR_GATE_BYPASS_REASON" not in block["why"] + block["how"]
    assert "gh pr create" not in block["why"] + block["how"]


@covers("review gate stale or missing")
@pytest.mark.parametrize("state_id", sorted(BLOCKING_GATE_STATES))
def test_refusals_for_a_gate_the_hook_blocks_is_blocked_by_the_lane_with_the_same_rule(
    state_id, repo_with_origin, monkeypatch, capsys
):
    state = BLOCKING_GATE_STATES[state_id]
    composed = seeded_lane(repo_with_origin, capsys, state)

    assert_hook_blocks_and_lane_agrees(composed, state.hook_rule, capsys, monkeypatch)


@pytest.mark.parametrize("state_id", sorted(ACCEPTING_GATE_STATES))
def test_refusals_for_a_gate_the_hook_accepts_is_accepted_by_the_lane(
    state_id, repo_with_origin, monkeypatch, capsys
):
    composed = seeded_lane(repo_with_origin, capsys, ACCEPTING_GATE_STATES[state_id])

    assert_hook_accepts_and_lane_agrees(composed, capsys, monkeypatch)


@covers("review gate stale or missing")
def test_refusals_for_a_registry_that_cannot_be_read_is_the_hooks_registry_failure(
    repo_with_origin, monkeypatch, capsys
):
    composed = composed_gated_lane(repo_with_origin, capsys)
    monkeypatch.setattr(
        review_agent_registry, "read_registered_review_agent_names", lambda _dir: None
    )

    assert_hook_blocks_and_lane_agrees(
        composed, "registry-read-failure", capsys, monkeypatch
    )


@covers("review gate stale or missing")
def test_refusals_for_a_gate_in_the_legacy_location_only_is_where_the_lane_and_the_hook_differ(
    repo_with_origin, monkeypatch, capsys
):
    """The one row of the parity outline where the two decisions differ, on purpose.

    The hook migrates a gate file from the legacy location (`memory/`) and then
    accepts it; the lane reads the gate with `migrate=False` (it changes
    nothing while checking), so it reads the same state as "missing". The
    lane's refusal is kept; both facts are asserted.
    """
    composed = seeded_lane(
        repo_with_origin,
        capsys,
        GateState(seed_legacy_location_only, "lane.txt", None),
    )
    legacy = composed.path / LEGACY_GATE_PATH
    gate = composed.path / GATE_RELATIVE_PATH
    legacy_bytes = legacy.read_bytes()

    (block,) = review_gate_blocks(composed, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "(rule: pre-pr-review)" in block["why"]
    assert legacy.read_bytes() == legacy_bytes, "the lane migrated the gate file"
    assert not gate.exists()
    assert hook_exit_code(composed, monkeypatch) == 0, "the hook accepts this state"
    assert not legacy.exists(), "the hook migrated and consumed the gate file"


@covers("review gate stale or missing")
def test_refusals_for_an_empty_lane_says_it_has_no_diff_against_trunk(
    repo_with_origin, capsys
):
    composed = composed_gated_lane(repo_with_origin, capsys, gate=False, lane_file=None)

    block = only_block(composed, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "no diff against trunk origin/main" in block["why"]


@covers("review gate stale or missing")
def test_refusals_for_an_unloadable_gate_module_is_a_refusal_not_a_traceback(
    composed_with_origin, stand_in_hook, capsys
):
    stand_in_hook('raise ImportError("no such hook")\n', with_preamble=False)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "ImportError" in block["why"]
    assert "/code-review --since" in block["how"]


@covers("review gate stale or missing")
def test_refusals_for_a_gate_evaluator_that_raises_is_a_refusal(
    composed_with_origin, stand_in_hook, capsys
):
    stand_in_hook(
        'def _evaluate_gate(*_args):\n    raise RuntimeError("evaluator broke")\n'
    )

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "RuntimeError: evaluator broke" in block["why"]


@covers("review gate stale or missing")
def test_refusals_for_a_hook_that_loaded_degraded_cannot_vouch_for_the_gate(
    composed_with_origin, stand_in_hook, capsys
):
    stand_in_hook(
        "def branch_diff_gate_hash(*_args, **_kwargs):\n"
        '    return ""\n'
        "def _evaluate_gate(*_args):\n"
        "    raise AssertionError('a degraded hook must not be asked')\n"
    )

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "degraded" in block["why"]
    assert block["why"].startswith("the review-gate check loaded in degraded mode")
    assert "the PR hook" not in block["why"]


@covers("review gate stale or missing")
def test_refusals_for_a_hook_with_another_gate_file_name_is_refused_not_trusted(
    composed_with_origin, stand_in_hook, capsys
):
    stand_in_hook(
        "from review_gate_hash import branch_diff_gate_hash\n"
        '_GATE_FILE_NAME = ".some-other-gate"\n'
        "def _evaluate_gate(*_args):\n"
        "    raise AssertionError('a hook with another gate file must not be asked')\n",
        with_preamble=False,
    )

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert ".some-other-gate" in block["why"]
    assert ".pr-review-passed" in block["why"]
    assert block["why"].startswith("the review-gate check's gate file is ")
    assert "(from the PR hook)" in block["why"]


@covers("review gate stale or missing")
def test_refusals_for_a_rule_the_lane_has_no_wording_for_still_names_the_rule(
    composed_with_origin, stand_in_hook, capsys
):
    stand_in_hook(
        "class _Verdict:\n"
        "    passed = False\n"
        '    matched_rule = "brand-new-rule"\n'
        "def _evaluate_gate(*_args):\n"
        "    return _Verdict()\n"
    )

    block = only_block(composed_with_origin, capsys)

    assert "(rule: brand-new-rule)" in block["why"]
    assert "the review gate rejected this lane" in block["why"]


@covers("review gate stale or missing")
def test_refusals_for_the_hooks_bypass_variable_is_ignored(
    composed_with_origin, monkeypatch, capsys
):
    monkeypatch.setenv("PR_GATE_BYPASS_REASON", "urgent")
    (composed_with_origin.path / GATE_RELATIVE_PATH).unlink()

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_REVIEW_GATE
    assert "PR_GATE_BYPASS_REASON" not in block["why"] + block["how"]


def other_repository(tmp_path) -> Path:
    path = tmp_path / "other-root"
    path.mkdir()
    return build_repo_without_remote(path).path


def test_the_review_gate_ignores_an_exported_git_dir(
    composed_with_origin, tmp_path, monkeypatch
):
    other = other_repository(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    assert refusals_for(composed_with_origin) == []


def test_the_review_gate_restores_the_environment_it_swapped(
    composed_with_origin, tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    before = dict(os.environ)

    refusals_for(composed_with_origin)

    assert dict(os.environ) == before


def test_the_review_gate_restores_the_environment_when_the_evaluation_raises(
    composed_with_origin, tmp_path, monkeypatch, stand_in_hook
):
    stand_in_hook(
        'def _evaluate_gate(*_args):\n    raise RuntimeError("evaluator broke")\n'
    )
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    before = dict(os.environ)

    refusals_for(composed_with_origin)

    assert dict(os.environ) == before


def test_the_review_gates_changed_file_list_runs_filtered_and_with_a_timeout(
    composed_with_origin, tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    seen: list[tuple[dict, str | None]] = []
    real = lane.git_safe_diff.run_safe_git_diff

    def spy(*args, **kwargs):
        seen.append((kwargs, os.environ.get("GIT_DIR")))
        return real(*args, **kwargs)

    monkeypatch.setattr(lane.git_safe_diff, "run_safe_git_diff", spy)

    refusals_for(composed_with_origin)

    ((kwargs, git_dir),) = seen
    assert kwargs["timeout"] == lane_core.GIT_TIMEOUT_SECONDS
    assert git_dir is None


@covers("tree mismatch")
@covers("review gate stale or missing")
@covers("trunk moved")
def test_refusals_for_tree_mismatch_stale_gate_and_moved_trunk_are_reported_together(
    composed_with_origin, capsys
):
    old_tree = composed_with_origin.expected_tree
    old_trunk = composed_with_origin.expected_trunk
    commit_in(composed_with_origin.path, "later.txt")
    live_tree = git(composed_with_origin.path, "rev-parse", "HEAD^{tree}")
    new_trunk = advance_origin(composed_with_origin.repo)
    before = observed_state(composed_with_origin)

    blocks = printed_blocks(refusals_for(composed_with_origin), capsys)

    assert [block["refused"] for block in blocks] == [
        WHAT_TREE_MISMATCH,
        WHAT_REVIEW_GATE,
        WHAT_TRUNK_MOVED,
    ]
    assert f"expected: {old_tree}" in blocks[0]["why"]
    assert f"live: {live_tree}" in blocks[0]["why"]
    assert f"expected: {old_trunk}" in blocks[2]["why"]
    assert f"live: {new_trunk}" in blocks[2]["why"]
    assert observed_state(composed_with_origin) == before


# --- check 3: the trunk has not moved ---------------------------------------


@covers("trunk moved")
def test_refusals_for_origin_advanced_by_a_fetch_is_trunk_moved_alone(
    composed_with_origin, capsys
):
    old_trunk = composed_with_origin.expected_trunk
    new_trunk = advance_origin(composed_with_origin.repo)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_TRUNK_MOVED
    assert f"expected: {old_trunk}" in block["why"]
    assert f"live: {new_trunk}" in block["why"]
    assert "origin/main" in block["why"]
    assert "/code-review --since origin/main" in block["how"]


# --- check 5: the trunk can fast-forward ------------------------------------


@covers("trunk cannot fast-forward")
def test_refusals_for_a_local_trunk_commit_the_lane_lacks_is_not_an_ancestor(
    composed_with_origin, capsys
):
    advance_trunk(composed_with_origin.repo)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "not an ancestor" in block["why"]
    assert "run compose" in block["how"]
    assert "/code-review --since origin/main" in block["how"]


def test_refusals_for_check_5_tests_the_head_it_read_once_not_the_live_head(
    composed_without_remote, monkeypatch
):
    composed = composed_without_remote
    head_read = git(composed.path, "rev-parse", "HEAD")
    advance_trunk(composed.repo)
    # After the lane's HEAD was read, the lane merges the trunk: the live HEAD
    # now holds the trunk tip, the commit the checks are bound to does not.
    raced = GitFailure(
        monkeypatch,
        ["rev-parse", "--verify", f"{head_read}^{{tree}}"],
        then=lambda _argv, _cwd: git(composed.path, "merge", "-q", "--no-edit", TRUNK),
    )

    refusals = refusals_for(composed)

    assert len(raced.matching) == 1, "the race did not happen"
    assert git(composed.path, "rev-parse", "HEAD") != head_read
    assert WHAT_FAST_FORWARD in [refusal.what for refusal in refusals]


@covers("trunk cannot fast-forward")
def test_refusals_for_trunk_checked_out_nowhere_is_named(composed_with_origin, capsys):
    git(composed_with_origin.repo.path, "switch", "-q", "-c", "elsewhere")

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "checked out nowhere" in block["why"]
    assert "git switch main" in block["how"]


@covers("trunk cannot fast-forward")
def test_refusals_for_an_uncommitted_change_in_the_trunk_worktree_is_named(
    composed_with_origin, capsys
):
    edit_tracked_file(composed_with_origin.repo.path)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "has uncommitted changes" in block["why"]
    assert "base.txt" in block["why"]
    assert "clean the trunk worktree" in block["how"]


@covers("trunk cannot fast-forward")
def test_refusals_for_a_tag_as_trunk_has_no_branch_to_fast_forward(
    composed_with_origin, capsys
):
    git(composed_with_origin.repo.path, "tag", "v1", "origin/main")

    block = only_block(composed_with_origin, capsys, trunk="v1")

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "does not exist" in block["why"]
    assert "pass --trunk <branch>" in block["how"]
    assert "git branch" not in block["how"]


@covers("trunk cannot fast-forward")
def test_refusals_for_a_remote_trunk_without_a_local_branch_does_not_exist(
    composed_with_origin, capsys
):
    primary = composed_with_origin.repo.path
    git(primary, "switch", "-q", "-c", "elsewhere")
    git(primary, "branch", "-d", TRUNK)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "local trunk branch main" in block["why"]
    assert "does not exist" in block["why"]
    assert "pass --trunk <branch>" in block["how"]
    assert "or create it: git branch main origin/main" in block["how"]


@covers("trunk cannot fast-forward")
def test_refusals_for_reports_the_first_failing_condition_when_several_fail(
    composed_with_origin, capsys
):
    advance_trunk(composed_with_origin.repo)
    edit_tracked_file(composed_with_origin.repo.path)

    block = only_block(composed_with_origin, capsys)

    assert "not an ancestor" in block["why"]


@covers("trunk moved")
@covers("trunk cannot fast-forward")
def test_refusals_for_a_trunk_moved_after_compose_with_no_remote_fails_both_checks(
    composed_without_remote, capsys
):
    new_trunk = advance_trunk(composed_without_remote.repo)
    before = observed_state(composed_without_remote)

    refusals = refusals_for(composed_without_remote)

    first, second = printed_blocks(refusals, capsys)
    assert first["refused"] == WHAT_TRUNK_MOVED
    assert f"live: {new_trunk}" in first["why"]
    assert second["refused"] == WHAT_FAST_FORWARD
    assert "not an ancestor" in second["why"]
    assert observed_state(composed_without_remote) == before


@covers("trunk cannot fast-forward")
def test_refusals_for_an_unfinished_merge_in_the_trunk_worktree_is_named(
    composed_with_origin, capsys
):
    primary = composed_with_origin.repo.path
    merge_head = primary / git(primary, "rev-parse", "--git-path", "MERGE_HEAD")
    merge_head.write_text(git(primary, "rev-parse", "HEAD") + "\n", encoding="utf-8")
    assert git(primary, "status", "--porcelain=v1") == ""

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_FAST_FORWARD
    assert "has uncommitted changes" in block["why"]
    assert "a merge is in progress (MERGE_HEAD exists)" in block["why"]
    assert "git merge --abort" in block["how"]


#: check 5's reads: the git arguments that, failing, must read as a git failure
#: and not as a sub-condition, and where the call runs ("lane", "trunk", or anywhere).
CHECK_5_READS = {
    "ancestry": (["merge-base", "--is-ancestor"], "lane"),
    "branch commit": (
        ["rev-parse", "--verify", "--quiet", "refs/heads/main^{commit}"],
        "anywhere",
    ),
    "merge in progress": (["rev-parse", "--verify", "--quiet", "MERGE_HEAD"], "trunk"),
}


@covers("git command failed")
@pytest.mark.parametrize("read", sorted(CHECK_5_READS))
def test_refusals_for_a_git_failure_in_check_5_is_a_git_failure_not_a_sub_condition(
    read, composed_with_origin, monkeypatch, capsys
):
    prefix, where = CHECK_5_READS[read]
    cwd = {
        "lane": composed_with_origin.path,
        "trunk": composed_with_origin.repo.path,
        "anywhere": None,
    }[where]
    GitFailure(monkeypatch, prefix, nth=None, cwd=cwd, **GIT_CANNOT_ANSWER)

    (block,) = printed_blocks(refusals_for(composed_with_origin), capsys)

    assert block["refused"] == WHAT_GIT_FAILED
    assert "fatal: injected" in block["why"]


# --- check 6: not a PR repository ------------------------------------------

PR_REPOSITORY_URLS = {
    "https with .git": GITHUB_URL,
    "ssh": "ssh://git@github.com/acme/widgets.git",
    "scp-like git@": "git@github.com:acme/widgets.git",
}

BUILD_COMPOSED_BY_ORIGIN = {
    "github": build_composed_with_github_origin,
    "other": build_composed_with_other_origin,
    "none": build_composed_without_remote,
}


@pytest.mark.parametrize(
    ("origin", "allow_local_integration", "expected_whats"),
    [
        ("github", False, [WHAT_PR_REPOSITORY]),
        ("github", True, []),
        ("other", False, []),
        ("other", True, []),
        ("none", False, []),
        ("none", True, []),
    ],
)
def test_refusals_for_the_pr_repository_check_by_origin_kind_and_flag(
    origin, allow_local_integration, expected_whats, tmp_path, capsys
):
    composed = BUILD_COMPOSED_BY_ORIGIN[origin](tmp_path, capsys)
    before = observed_state(composed)

    refusals = refusals_for(composed, allow_local_integration=allow_local_integration)

    assert [refusal.what for refusal in refusals] == expected_whats
    assert observed_state(composed) == before


@covers("PR repository")
def test_refusals_for_the_pr_repository_block_points_at_pr_and_at_local_trunk(
    tmp_path, capsys
):
    composed = build_composed_with_github_origin(tmp_path, capsys)

    block = only_block(composed, capsys)

    assert block["refused"] == WHAT_PR_REPOSITORY
    assert "with /pr" in block["how"]
    assert "--local-trunk" in block["how"]


@covers("PR repository")
@pytest.mark.parametrize("form", sorted(PR_REPOSITORY_URLS))
def test_refusals_for_every_github_url_form_is_a_pr_repository(form, tmp_path, capsys):
    composed = build_composed_with_github_origin(
        tmp_path, capsys, PR_REPOSITORY_URLS[form]
    )

    block = only_block(composed, capsys)

    assert block["refused"] == WHAT_PR_REPOSITORY
    assert "github.com" not in block["why"] + block["how"]


def test_refusals_for_a_non_github_host_that_only_looks_like_one_is_not_a_pr_repository(
    tmp_path, capsys
):
    composed = build_composed_with_other_origin(tmp_path, capsys, LOOKALIKE_URL)

    assert refusals_for(composed) == []


def printed_with_note(refusals, capsys) -> list[str]:
    """The lines `emit_integrate_refusals` writes to stderr."""
    assert lane.emit_integrate_refusals(refusals) == 1
    return capsys.readouterr().err.splitlines()


@covers("PR repository")
@covers("lane has uncommitted changes")
def test_refusals_for_a_pr_repository_refusal_with_others_ends_with_the_note_line(
    tmp_path, capsys
):
    composed = build_composed_with_github_origin(tmp_path, capsys)
    leave_untracked_file(composed.path)

    refusals = refusals_for(composed)
    lines = printed_with_note(refusals, capsys)

    assert [r.what for r in refusals] == [WHAT_UNCOMMITTED, WHAT_PR_REPOSITORY]
    assert lines[-1].startswith("note: ")
    assert "/pr" in lines[-1]
    assert lines[-2] == ""
    assert [line for line in lines if line.startswith("refused: ")] == [
        f"refused: {WHAT_UNCOMMITTED}",
        f"refused: {WHAT_PR_REPOSITORY}",
    ]


@covers("PR repository")
def test_refusals_for_a_lone_pr_repository_refusal_has_no_note(tmp_path, capsys):
    composed = build_composed_with_github_origin(tmp_path, capsys)

    lines = printed_with_note(refusals_for(composed), capsys)

    assert not any(line.startswith("note:") for line in lines)


@covers("lane has uncommitted changes")
@covers("trunk moved")
def test_refusals_for_several_refusals_without_a_pr_repository_have_no_note(
    composed_with_origin, capsys
):
    leave_untracked_file(composed_with_origin.path)
    advance_origin(composed_with_origin.repo)

    refusals = refusals_for(composed_with_origin)
    lines = printed_with_note(refusals, capsys)

    assert [r.what for r in refusals] == [WHAT_TRUNK_MOVED, WHAT_UNCOMMITTED]
    assert not any(line.startswith("note:") for line in lines)


@covers("git command failed")
@pytest.mark.parametrize(
    ("failing", "nth"),
    [(["remote"], 2), (["remote", "get-url"], 1)],
    ids=["remote listing", "remote get-url"],
)
def test_refusals_for_a_failed_origin_lookup_on_a_github_repository_still_refuses(
    failing, nth, tmp_path, monkeypatch, capsys
):
    composed = build_composed_with_github_origin(tmp_path, capsys)
    # Entering the lane lists the remotes once (to map origin/main to main): the
    # origin lookup of check 6 is the second `git remote`.
    GitFailure(monkeypatch, failing, nth=nth, **GIT_CANNOT_ANSWER)
    before = observed_state(composed)

    (block,) = printed_blocks(refusals_for(composed), capsys)

    assert block["refused"] == WHAT_GIT_FAILED
    assert "fatal: injected" in block["why"]
    assert observed_state(composed) == before


def test_refusals_for_local_trunk_does_not_read_the_origin(
    tmp_path, monkeypatch, capsys
):
    composed = build_composed_with_github_origin(tmp_path, capsys)
    lookup = GitFailure(
        monkeypatch, ["remote", "get-url"], nth=None, **GIT_CANNOT_ANSWER
    )

    assert refusals_for(composed, allow_local_integration=True) == []
    assert lookup.matching == []


def test_one_run_of_the_checks_reads_the_origin_url_once(tmp_path, capsys, argv_spy):
    composed = build_composed_with_github_origin(tmp_path, capsys)
    start = len(argv_spy.records)

    refusals_for(composed)

    lookups = [
        argv
        for argv in argv_spy.records[start:]
        if argv[:3] == ["git", "remote", "get-url"]
    ]
    assert len(lookups) == 1


# --- check 4: the lane is clean ----------------------------------------------


@covers("lane has uncommitted changes")
def test_refusals_for_an_untracked_file_in_the_lane_is_the_only_refusal(
    composed_with_origin, capsys
):
    leave_untracked_file(composed_with_origin.path)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == WHAT_UNCOMMITTED
    assert "commit or stash" in block["how"]
    assert "scratch.txt" in block["why"]


# --- early stops: one block, no checks ---------------------------------------


@pytest.mark.parametrize("place", NOT_A_LANE_PLACES)
@covers("not in a lane")
def test_refusals_for_a_place_that_is_not_a_lane_is_one_not_in_a_lane_block(
    place, composed_without_remote, capsys
):
    cwd = place(composed_without_remote.repo)
    before = observed_state(composed_without_remote)

    refusals = refusals_for(composed_without_remote, cwd=cwd)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == WHAT_NOT_IN_A_LANE
    assert "lane.py open" in block["how"]
    assert observed_state(composed_without_remote) == before


@covers("trunk ref cannot be resolved")
def test_refusals_for_an_unresolvable_trunk_is_one_block_and_runs_no_check(
    composed_without_remote, capsys
):
    leave_untracked_file(composed_without_remote.path)

    block = only_block(composed_without_remote, capsys, trunk="nonexistent-ref")

    assert block["refused"] == "trunk ref cannot be resolved"
    assert "nonexistent-ref" in block["why"]


@covers("not a git repository")
def test_refusals_for_outside_a_repository_is_one_block(
    composed_without_remote, plain_directory, capsys
):
    refusals = refusals_for(composed_without_remote, cwd=plain_directory)

    (block,) = printed_blocks(refusals, capsys)
    assert block["refused"] == "not a git repository"


# --- .claude not ignored ------------------------------------------------------


@covers("lane has uncommitted changes")
def test_refusals_for_a_repository_that_does_not_ignore_claude_names_setup(
    repo_without_remote, capsys
):
    git(repo_without_remote.path, "rm", "-q", ".gitignore")
    git(repo_without_remote.path, "commit", "-q", "-m", "stop ignoring .claude")
    composed = composed_gated_lane(repo_without_remote, capsys)

    block = only_block(composed, capsys)

    assert block["refused"] == WHAT_UNCOMMITTED
    assert ".claude/memory/.pr-review-passed" in block["why"]
    assert "/setup" in block["how"]


# --- a check that hits a git failure ------------------------------------------


@covers("git command failed")
def test_refusals_for_a_git_failure_in_a_check_is_its_block_and_the_later_checks_do_not_run(
    composed_without_remote, monkeypatch, capsys, argv_spy
):
    composed = composed_without_remote
    # Check 4 would report this file if it ran.
    leave_untracked_file(composed.path)
    head = git(composed.path, "rev-parse", "HEAD")
    # Check 1 asks for the tree of the lane's HEAD commit: that read fails.
    GitFailure(
        monkeypatch,
        ["rev-parse", "--verify", f"{head}^{{tree}}"],
        nth=None,
        exit_code=128,
        stderr="fatal: boom\n",
    )
    calls_before = len(argv_spy.records)

    (block,) = printed_blocks(refusals_for(composed), capsys)

    assert block["refused"] == WHAT_GIT_FAILED
    assert "fatal: boom" in block["why"]
    assert not git_calls_since(argv_spy, calls_before, "status")


@covers("git command failed")
@pytest.mark.parametrize(
    ("behavior", "expected_detail"),
    [
        (
            subprocess.TimeoutExpired(["git", "diff"], lane_core.GIT_TIMEOUT_SECONDS),
            lane_core.GIT_TIMED_OUT_DETAIL,
        ),
        (OSError("git vanished"), "git vanished"),
        (
            subprocess.CompletedProcess(
                ["git", "diff"], 128, stdout="", stderr="fatal: boom\n"
            ),
            "fatal: boom",
        ),
    ],
    ids=["timeout", "launch failure", "non-zero exit"],
)
def test_refusals_for_a_git_failure_in_the_review_gate_changed_files_stops_the_checks(
    composed_without_remote, monkeypatch, capsys, argv_spy, behavior, expected_detail
):
    composed = composed_without_remote
    # Check 4 would report this file if it ran.
    leave_untracked_file(composed.path)

    def failing_diff(*_args, **_kwargs):
        if isinstance(behavior, BaseException):
            raise behavior
        return behavior

    # double-waiver: B1 - `git_safe_diff.run_safe_git_diff` is the seam to the
    # git child process; a timeout, a launch failure or an exit status of it
    # cannot be caused for real at a chosen call.
    monkeypatch.setattr(lane.git_safe_diff, "run_safe_git_diff", failing_diff)
    calls_before = len(argv_spy.records)

    (block,) = printed_blocks(refusals_for(composed), capsys)

    assert block["refused"] == WHAT_GIT_FAILED
    assert expected_detail in block["why"]
    assert "git diff --name-only" in block["why"]
    assert not git_calls_since(argv_spy, calls_before, "status")
