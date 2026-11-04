"""Tests for the `lane.py integrate` check engine (`collect_refusals`).

The `test_collect_*` tests drive the checks through `collect_refusals` and
print what it returns with `lane_core.emit_refusals`. The tests from "the
integrate command" on run `main(["integrate", ...])`. A refused run changes
nothing, which every row checks with `unchanged_state` on both worktrees and
the gate file.

Every test runs in-process against real git repositories built by
`lane_fixtures`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from lane_fixtures import (
    GATE_DISPATCH_AGENTS,
    GATE_RELATIVE_PATH,
    LEDGER_RELATIVE_PATH,
    ComposedLane,
    add_linked_worktree,
    advance_origin,
    advance_trunk,
    append_ledger,
    argv_spy,
    build_repo_with_origin,
    build_repo_without_remote,
    commit_file,
    composed_gated_lane,
    covers,
    dispatch_row,
    enforce_covers,
    gate_hash_of,
    git,
    git_succeeds,
    hermetic_process_env,
    is_ancestor,
    ledger_row,
    parse_blocks,
    parse_output,
    plain_directory,
    repo_with_origin,
    repo_without_remote,
    run_main,
    seed_gate,
    unchanged_state,
    write_gate_file,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core
import review_agent_registry

NOT_IN_A_LANE = "not in a lane"
UNCOMMITTED = "lane has uncommitted changes"
REVIEW_GATE = "review gate stale or missing"
PR_HOOK_PATH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"


def claude_snapshot(worktree: Path) -> list[tuple[str, bool, bytes | None]]:
    """Every entry under `<worktree>/.claude`: (relative path, is a directory, bytes).

    `unchanged_state` collapses an ignored directory to one status line, so it
    cannot see a file written or changed inside `.claude/`; this can.
    """
    root = worktree / ".claude"
    if not root.exists():
        return []
    return sorted(
        (
            str(entry.relative_to(root)),
            entry.is_dir(),
            None if entry.is_dir() else entry.read_bytes(),
        )
        for entry in root.rglob("*")
    )


def observed_state(composed: ComposedLane) -> dict[str, object]:
    """What must be equal before and after a refused run: both worktrees (git
    state and everything under their `.claude/`), and the gate file's bytes
    (None when absent)."""
    gate = composed.path / GATE_RELATIVE_PATH
    return {
        "lane": unchanged_state(composed.path),
        "trunk": unchanged_state(composed.repo.path),
        "lane .claude": claude_snapshot(composed.path),
        "trunk .claude": claude_snapshot(composed.repo.path),
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
    local_trunk: bool = False,
) -> list[lane_core.Refusal]:
    """The refusals for `composed`, with its own identities unless overridden."""
    return lane.collect_refusals(
        trunk,
        expected_trunk or composed.expected_trunk,
        expected_tree or composed.expected_tree,
        cwd or composed.path,
        local_trunk=local_trunk,
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


# --- check 2: the review gate -------------------------------------------------


def load_pr_hook():
    """The PR hook module, loaded here independently of `lane.py`."""
    spec = importlib.util.spec_from_file_location("pr_hook_under_parity", PR_HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)  # the hook puts its own lib directory first
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
    return module


def test_loading_the_hook_for_parity_leaves_sys_path_as_it_was():
    before = list(sys.path)

    load_pr_hook()

    assert sys.path == before


def hook_exit_code(composed: ComposedLane, monkeypatch) -> int:
    """The PR hook's own `main()` on a `gh pr create` payload run in the lane."""
    payload = {"tool_input": {"command": "gh pr create"}, "cwd": str(composed.path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return load_pr_hook().main()


def hook_block_rule(composed: ComposedLane) -> str:
    """The `matched_rule` the hook logged for its last block in the lane."""
    log = (composed.path / LEDGER_RELATIVE_PATH).read_text(encoding="utf-8")
    blocks = [
        json.loads(line)
        for line in log.splitlines()
        if '"pre_pr_review"' in line and '"block"' in line
    ]
    return blocks[-1]["matched_rule"]


def review_gate_blocks(composed: ComposedLane, capsys) -> list[dict[str, str]]:
    """The printed review-gate blocks among the checks' refusals for `composed`."""
    refusals = [item for item in collect(composed) if item.what == REVIEW_GATE]
    return printed_blocks(refusals, capsys) if refusals else []


@covers("review gate stale or missing")
def test_collect_a_deleted_gate_file_is_the_review_gate_block_alone(
    composed_with_origin, capsys
):
    (composed_with_origin.path / GATE_RELATIVE_PATH).unlink()

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "/code-review --since origin/main" in block["how"]
    assert "(rule: pre-pr-review)" in block["why"]


def test_a_gate_that_passes_is_left_in_place(composed_with_origin):
    gate = composed_with_origin.path / GATE_RELATIVE_PATH
    before = gate.read_bytes()

    assert collect(composed_with_origin) == []

    assert gate.read_bytes() == before


# Seeds for the parity table below: each leaves the lane in one gate state.
def seed_missing(composed, trunk_hash):
    pass


def seed_different_content(composed, trunk_hash):
    write_gate_file(composed.path, "f" * 64)


def seed_hash_only(composed, trunk_hash):
    write_gate_file(composed.path, trunk_hash)


def seed_hash_and_empty_ledger(composed, trunk_hash):
    seed_hash_only(composed, trunk_hash)
    ledger = composed.path / LEDGER_RELATIVE_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("", encoding="utf-8")


def seed_one_dispatch(composed, trunk_hash):
    seed_hash_only(composed, trunk_hash)
    append_ledger(composed.path, [dispatch_row("security-review", trunk_hash, 60)])


def seed_two_dispatches(composed, trunk_hash):
    seed_gate(composed.path, composed.trunk_ref)


def seed_old_dispatches(composed, trunk_hash):
    seed_hash_only(composed, trunk_hash)
    age = load_pr_hook().WINDOW_SECONDS + 120
    append_ledger(
        composed.path, [dispatch_row(a, trunk_hash, age) for a in GATE_DISPATCH_AGENTS]
    )


def seed_doc_only_exemption(composed, trunk_hash):
    seed_hash_only(composed, trunk_hash)
    append_ledger(
        composed.path,
        [ledger_row("code-review", "bypass", "doc-only-review-exempt", trunk_hash, 60)],
    )


def seed_dispatches_for_other_content(composed, trunk_hash):
    seed_hash_only(composed, trunk_hash)
    append_ledger(
        composed.path,
        [dispatch_row(agent, "e" * 64, 60) for agent in GATE_DISPATCH_AGENTS],
    )


def seed_dispatch_failure(composed, trunk_hash):
    seed_two_dispatches(composed, trunk_hash)
    append_ledger(
        composed.path,
        [
            ledger_row(
                "code-review", "dispatch-failure", "security-review", trunk_hash, 30
            )
        ],
    )


def seed_gate_is_a_directory(composed, trunk_hash):
    (composed.path / GATE_RELATIVE_PATH).mkdir(parents=True)


def seed_binary_garbage(composed, trunk_hash):
    gate = composed.path / GATE_RELATIVE_PATH
    gate.parent.mkdir(parents=True)
    gate.write_bytes(b"\xff\xfe\x00\x80 not a hash \x00")


#: id -> (seed, lane file, hook matched_rule or None when the hook accepts)
GATE_STATES = {
    "missing gate file": (seed_missing, "lane.txt", "pre-pr-review"),
    "gate hash for different content": (
        seed_different_content,
        "lane.txt",
        "pre-pr-review",
    ),
    "right hash, no dispatches": (
        seed_hash_and_empty_ledger,
        "lane.txt",
        "dispatch-evidence-missing",
    ),
    "right hash, no ledger file": (
        seed_hash_only,
        "lane.txt",
        "dispatch-ledger-read-failure",
    ),
    "right hash, one dispatch": (seed_one_dispatch, "lane.txt", None),
    "right hash, two distinct dispatches": (seed_two_dispatches, "lane.txt", None),
    "right hash, dispatches older than the window": (
        seed_old_dispatches,
        "lane.txt",
        "dispatch-evidence-stale",
    ),
    "right hash, doc-only exemption": (seed_doc_only_exemption, "notes.md", None),
    "right hash, dispatches for other content": (
        seed_dispatches_for_other_content,
        "lane.txt",
        "dispatch-evidence-different-content",
    ),
    "right hash, dispatch-failure veto": (
        seed_dispatch_failure,
        "lane.txt",
        "dispatch-failure-veto",
    ),
    "gate file is a directory": (
        seed_gate_is_a_directory,
        "lane.txt",
        "pre-pr-review",
    ),
    "gate file is binary garbage": (seed_binary_garbage, "lane.txt", "pre-pr-review"),
}


def assert_gate_parity(composed, hook_rule, capsys, monkeypatch) -> None:
    """The lane's gate check and the hook's `main()` decide alike on `composed`.

    `hook_rule` is the `matched_rule` the hook logs when it blocks, None when it
    accepts. An accepting hook removes the gate file (so it got as far as
    `_evaluate_gate`); a rejecting one leaves it as it was.
    """
    gate = composed.path / GATE_RELATIVE_PATH
    had_gate = gate.exists()
    before = observed_state(composed)

    lane_blocks = review_gate_blocks(composed, capsys)
    assert observed_state(composed) == before
    hook_code = hook_exit_code(composed, monkeypatch)

    assert (hook_code == 0) == (hook_rule is None)
    assert (lane_blocks == []) == (hook_code == 0)
    if hook_rule is None:
        assert not gate.exists()
        return
    assert gate.exists() == had_gate
    assert hook_block_rule(composed) == hook_rule
    (block,) = lane_blocks
    assert f"(rule: {hook_rule})" in block["why"]
    assert "PR_GATE_BYPASS_REASON" not in block["why"] + block["how"]
    assert "gh pr create" not in block["why"] + block["how"]


@pytest.mark.parametrize("state", sorted(GATE_STATES))
def test_collect_the_gate_decision_equals_the_pr_hooks_decision(
    state, repo_with_origin, monkeypatch, capsys
):
    seed, lane_file, hook_rule = GATE_STATES[state]
    composed = composed_gated_lane(
        repo_with_origin, capsys, gate=False, lane_file=lane_file
    )
    seed(composed, gate_hash_of(composed.path, composed.trunk_ref))

    assert_gate_parity(composed, hook_rule, capsys, monkeypatch)


def test_collect_a_registry_that_cannot_be_read_is_the_hooks_registry_failure(
    repo_with_origin, monkeypatch, capsys
):
    composed = composed_gated_lane(repo_with_origin, capsys)
    monkeypatch.setattr(
        review_agent_registry, "read_registered_review_agent_names", lambda _dir: None
    )

    assert_gate_parity(composed, "registry-read-failure", capsys, monkeypatch)


@covers("review gate stale or missing")
def test_collect_a_gate_in_the_legacy_location_reads_as_missing_and_is_not_migrated(
    composed_with_origin, capsys
):
    lane_path = composed_with_origin.path
    gate = lane_path / GATE_RELATIVE_PATH
    legacy = lane_path / "memory" / ".pr-review-passed"
    legacy.parent.mkdir()
    legacy.write_bytes(gate.read_bytes())
    gate.unlink()
    before = legacy.read_bytes()

    blocks = review_gate_blocks(composed_with_origin, capsys)

    assert [block["refused"] for block in blocks] == [REVIEW_GATE]
    assert legacy.read_bytes() == before
    assert not gate.exists()


@covers("review gate stale or missing")
def test_collect_an_empty_lane_says_it_has_no_diff_against_trunk(
    repo_with_origin, capsys
):
    composed = composed_gated_lane(repo_with_origin, capsys, gate=False, lane_file=None)

    block = only_block(composed, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "no diff against trunk origin/main" in block["why"]


@covers("review gate stale or missing")
def test_collect_an_unloadable_gate_module_is_a_refusal_not_a_traceback(
    composed_with_origin, monkeypatch, capsys
):
    def raise_import_error(*_args, **_kwargs):
        raise ImportError("no such hook")

    monkeypatch.setattr(importlib.util, "spec_from_file_location", raise_import_error)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "ImportError" in block["why"]
    assert "/code-review --since" in block["how"]


def stand_in_hook(**overrides):
    """What `_load_pr_hook` returns instead of the hook: the public names it
    uses are the real ones unless overridden."""
    import review_gate_hash

    hook = types.SimpleNamespace(
        branch_diff_gate_hash=review_gate_hash.branch_diff_gate_hash,
        _GATE_FILE_NAME=".pr-review-passed",
        _evaluate_gate=lambda *_args: types.SimpleNamespace(passed=True),
    )
    for name, value in overrides.items():
        setattr(hook, name, value)
    return hook


@covers("review gate stale or missing")
def test_collect_a_gate_evaluator_that_raises_is_a_refusal(
    composed_with_origin, monkeypatch, capsys
):
    def explode(*_args):
        raise RuntimeError("evaluator broke")

    hook = stand_in_hook(_evaluate_gate=explode)
    monkeypatch.setattr(lane, "_load_pr_hook", lambda: hook)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "RuntimeError: evaluator broke" in block["why"]


@covers("review gate stale or missing")
def test_collect_a_hook_that_loaded_degraded_cannot_vouch_for_the_gate(
    composed_with_origin, monkeypatch, capsys
):
    hook = stand_in_hook(branch_diff_gate_hash=lambda *_args, **_kwargs: "")
    monkeypatch.setattr(lane, "_load_pr_hook", lambda: hook)

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "degraded" in block["why"]


@covers("review gate stale or missing")
def test_collect_the_hooks_bypass_variable_is_ignored(
    composed_with_origin, monkeypatch, capsys
):
    monkeypatch.setenv("PR_GATE_BYPASS_REASON", "urgent")
    (composed_with_origin.path / GATE_RELATIVE_PATH).unlink()

    block = only_block(composed_with_origin, capsys)

    assert block["refused"] == REVIEW_GATE
    assert "PR_GATE_BYPASS_REASON" not in block["why"] + block["how"]


def private_attribute_users(source: str, receiver: str) -> dict[str, set[str]]:
    """Function name -> private attributes it reads off a variable named `receiver`."""
    users: dict[str, set[str]] = {}
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == receiver
                and node.attr.startswith("_")
            ):
                users.setdefault(function.name, set()).add(node.attr)
    return users


def test_the_hooks_private_names_are_used_in_one_function_only():
    source = (SCRIPTS_DIR / "lane.py").read_text(encoding="utf-8")

    assert private_attribute_users(source, "hook") == {
        "_gate_verdict": {"_evaluate_gate", "_GATE_FILE_NAME"}
    }


def gate_verdict_rules(source: str) -> set[str]:
    """The `matched_rule` literal of every rejecting `GateVerdict(...)` call.

    Fails on a call whose rule is not a string constant: a rule given by
    keyword, by variable, or left out (two positional arguments) would escape
    the wording table unseen. The one-argument accepting form
    `GateVerdict(True)` is the only call without a rule.
    """
    rules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "GateVerdict"
        ):
            continue
        accepting = (
            len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value is True
        )
        if accepting:
            continue
        rule = node.args[2] if len(node.args) >= 3 else None
        assert (
            rule is not None
            and not node.keywords
            and isinstance(rule, ast.Constant)
            and isinstance(rule.value, str)
        ), f"GateVerdict rule is not a string constant: {ast.unparse(node)}"
        rules.add(rule.value)
    return rules


@pytest.mark.parametrize(
    "call",
    [
        'GateVerdict(False, "m", rule)',
        'GateVerdict(False, "m", matched_rule="r")',
        'GateVerdict(False, "m")',
        "GateVerdict(passed=False)",
        "GateVerdict(False)",
    ],
)
def test_the_rule_scan_rejects_a_verdict_whose_rule_is_not_a_constant(call):
    with pytest.raises(AssertionError, match="not a string constant"):
        gate_verdict_rules(call)


def test_every_rule_the_hook_can_log_has_lane_wording():
    rules = gate_verdict_rules(PR_HOOK_PATH.read_text(encoding="utf-8"))

    assert rules == {
        "pre-pr-review",
        "gate-setup-failure-empty-digest",
        "registry-read-failure",
        "dispatch-failure-veto",
        "dispatch-ledger-read-failure",
        "dispatch-evidence-insufficient",
        "dispatch-evidence-stale",
        "dispatch-evidence-different-content",
        "dispatch-evidence-missing",
    }
    assert rules <= set(lane.GATE_RULE_WORDING)


def test_an_unknown_rule_still_names_the_rule():
    assert "(rule: brand-new-rule)" in lane._gate_rejection_why("brand-new-rule")


def test_the_gate_file_name_is_the_hooks():
    assert load_pr_hook()._GATE_FILE_NAME == GATE_RELATIVE_PATH.name


def other_repository(tmp_path) -> Path:
    path = tmp_path / "other-root"
    path.mkdir()
    return build_repo_without_remote(path).path


def test_the_gate_verdict_ignores_an_exported_git_dir(
    composed_with_origin, tmp_path, monkeypatch
):
    other = other_repository(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    assert collect(composed_with_origin) == []


def test_the_gate_verdict_restores_the_environment_it_swapped(
    composed_with_origin, tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    before = dict(os.environ)

    collect(composed_with_origin)

    assert dict(os.environ) == before


def test_the_gate_verdict_restores_the_environment_when_the_evaluation_raises(
    composed_with_origin, tmp_path, monkeypatch
):
    def explode(*_args):
        raise RuntimeError("evaluator broke")

    hook = stand_in_hook(_evaluate_gate=explode)
    monkeypatch.setattr(lane, "_load_pr_hook", lambda: hook)
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    before = dict(os.environ)

    collect(composed_with_origin)

    assert dict(os.environ) == before


def test_the_gate_verdicts_changed_file_list_runs_filtered_and_with_a_timeout(
    composed_with_origin, tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_DIR", str(other_repository(tmp_path) / ".git"))
    seen: list[tuple[dict, str | None]] = []
    real = lane.git_safe_diff.run_safe_git_diff

    def spy(*args, **kwargs):
        seen.append((kwargs, os.environ.get("GIT_DIR")))
        return real(*args, **kwargs)

    monkeypatch.setattr(lane.git_safe_diff, "run_safe_git_diff", spy)

    collect(composed_with_origin)

    ((kwargs, git_dir),) = seen
    assert kwargs["timeout"] == lane_core.GIT_TIMEOUT_SECONDS
    assert git_dir is None


@covers("tree mismatch")
@covers("review gate stale or missing")
@covers("trunk moved")
def test_collect_tree_mismatch_stale_gate_and_moved_trunk_are_reported_together(
    composed_with_origin, capsys
):
    old_tree = composed_with_origin.expected_tree
    old_trunk = composed_with_origin.expected_trunk
    commit_file(composed_with_origin.path, "later.txt", "later\n", "later work")
    live_tree = git(composed_with_origin.path, "rev-parse", "HEAD^{tree}")
    new_trunk = advance_origin(composed_with_origin.repo)
    before = observed_state(composed_with_origin)

    blocks = printed_blocks(collect(composed_with_origin), capsys)

    assert [block["refused"] for block in blocks] == [
        "tree mismatch",
        REVIEW_GATE,
        "trunk moved",
    ]
    assert f"expected: {old_tree}" in blocks[0]["why"]
    assert f"live: {live_tree}" in blocks[0]["why"]
    assert f"expected: {old_trunk}" in blocks[2]["why"]
    assert f"live: {new_trunk}" in blocks[2]["why"]
    assert observed_state(composed_with_origin) == before


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


# --- check 6: not a PR repository ------------------------------------------

PR_REPOSITORY = "PR repository"
GITHUB_URL = "https://github.com/acme/widgets.git"
PR_REPOSITORY_URLS = {
    "https with .git": GITHUB_URL,
    "ssh": "ssh://git@github.com/acme/widgets.git",
    "scp-like git@": "git@github.com:acme/widgets.git",
}


def composed_with_origin_kind(tmp_path, capsys, origin: str, url: str | None = None):
    """A composed, gated lane whose origin is `github`, `other` or `none`."""
    if origin == "none":
        return composed_gated_lane(build_repo_without_remote(tmp_path), capsys)
    repo = build_repo_with_origin(tmp_path)
    composed = composed_gated_lane(repo, capsys)
    if origin == "github":
        git(repo.path, "remote", "set-url", "origin", url or GITHUB_URL)
    return composed


@pytest.mark.parametrize("local_trunk", [False, True], ids=["no-flag", "local-trunk"])
@pytest.mark.parametrize("origin", ["github", "other", "none"])
def test_collect_the_pr_repository_block_by_origin_kind_and_flag(
    origin, local_trunk, tmp_path, capsys
):
    composed = composed_with_origin_kind(tmp_path, capsys, origin)
    before = observed_state(composed)

    refusals = collect(composed, local_trunk=local_trunk)

    printed = origin == "github" and not local_trunk
    assert [r.what for r in refusals] == ([PR_REPOSITORY] if printed else [])
    if printed:
        (block,) = printed_blocks(refusals, capsys)
        assert "/pr" in block["how"]
        assert "--local-trunk" in block["how"]
    assert observed_state(composed) == before


@covers("PR repository")
@pytest.mark.parametrize("form", sorted(PR_REPOSITORY_URLS))
def test_collect_every_github_url_form_is_a_pr_repository(form, tmp_path, capsys):
    composed = composed_with_origin_kind(
        tmp_path, capsys, "github", PR_REPOSITORY_URLS[form]
    )

    block = only_block(composed, capsys)

    assert block["refused"] == PR_REPOSITORY
    assert "github.com" not in block["why"] + block["how"]


def test_collect_a_non_github_host_that_only_looks_like_one_is_not_a_pr_repository(
    tmp_path, capsys
):
    composed = composed_with_origin_kind(
        tmp_path, capsys, "other", "https://notgithub.example.com/acme/w.git"
    )

    assert collect(composed) == []


def printed_with_note(refusals, capsys) -> list[str]:
    """The lines `emit_integrate_refusals` writes to stderr."""
    assert lane.emit_integrate_refusals(refusals) == 1
    return capsys.readouterr().err.splitlines()


@covers("PR repository")
@covers("lane has uncommitted changes")
def test_collect_a_pr_repository_refusal_with_others_ends_with_the_note_line(
    tmp_path, capsys
):
    composed = composed_with_origin_kind(tmp_path, capsys, "github")
    leave_untracked_file(composed.path)

    refusals = collect(composed)
    lines = printed_with_note(refusals, capsys)

    assert [r.what for r in refusals] == [UNCOMMITTED, PR_REPOSITORY]
    assert lines[-1].startswith("note: ")
    assert "/pr" in lines[-1]
    assert lines[-2] == ""
    assert [line for line in lines if line.startswith("refused: ")] == [
        f"refused: {UNCOMMITTED}",
        f"refused: {PR_REPOSITORY}",
    ]


@covers("PR repository")
def test_collect_a_lone_pr_repository_refusal_has_no_note(tmp_path, capsys):
    composed = composed_with_origin_kind(tmp_path, capsys, "github")

    lines = printed_with_note(collect(composed), capsys)

    assert not any(line.startswith("note:") for line in lines)


@covers("lane has uncommitted changes")
@covers("trunk moved")
def test_collect_several_refusals_without_a_pr_repository_have_no_note(
    composed_with_origin, capsys
):
    leave_untracked_file(composed_with_origin.path)
    advance_origin(composed_with_origin.repo)

    refusals = collect(composed_with_origin)
    lines = printed_with_note(refusals, capsys)

    assert [r.what for r in refusals] == ["trunk moved", UNCOMMITTED]
    assert not any(line.startswith("note:") for line in lines)


def fail_git_text_once_the_lane_is_entered(monkeypatch, prefix: list[str]) -> None:
    """`lane_core.git_text` raises for a call starting with `prefix`, from the moment
    `_enter_lane` has returned (entering a lane itself lists remotes)."""
    real_enter = lane._enter_lane
    real = lane_core.git_text
    entered: list[bool] = []

    def enter(*args):
        result = real_enter(*args)
        entered.append(True)
        return result

    def failing(args, cwd):
        if entered and list(args[: len(prefix)]) == prefix:
            raise lane_core.RefusalError(
                lane_core.git_command_failed_refusal("git remote", "fatal: injected")
            )
        return real(args, cwd)

    monkeypatch.setattr(lane, "_enter_lane", enter)
    monkeypatch.setattr(lane_core, "git_text", failing)


@covers("git command failed")
@pytest.mark.parametrize("failing", [["remote"], ["remote", "get-url"]])
def test_collect_a_failed_origin_lookup_on_a_github_repository_still_refuses(
    failing, tmp_path, monkeypatch, capsys
):
    composed = composed_with_origin_kind(tmp_path, capsys, "github")
    fail_git_text_once_the_lane_is_entered(monkeypatch, failing)
    before = observed_state(composed)

    (block,) = printed_blocks(collect(composed), capsys)

    assert block["refused"] == "git command failed"
    assert "fatal: injected" in block["why"]
    assert observed_state(composed) == before


def test_collect_local_trunk_does_not_read_the_origin(tmp_path, monkeypatch, capsys):
    composed = composed_with_origin_kind(tmp_path, capsys, "github")
    fail_git_text_once_the_lane_is_entered(monkeypatch, ["remote"])

    assert collect(composed, local_trunk=True) == []


def test_there_is_one_origin_lookup_in_lane():
    source = (SCRIPTS_DIR / "lane.py").read_text(encoding="utf-8")

    assert source.count("lane_core.origin_url(") == 1
    assert source.count("git_origin_host.classify(") == 1


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


# --- the integrate command: identity arguments -------------------------------

INVALID_IDENTITY = "invalid identity argument"
ABBREVIATED_SHA = "a" * 12
WRONG_SHA = "0" * 40


def integrate_argv(
    composed: ComposedLane, *extra: str, **identities: str | None
) -> list[str]:
    """`integrate` with the composed identities; `expected_trunk=` / `expected_tree=`
    override one (a value of None leaves its flag out)."""
    given = {
        "expected_trunk": composed.expected_trunk,
        "expected_tree": composed.expected_tree,
        **identities,
    }
    argv = ["integrate"]
    for key, flag in (
        ("expected_trunk", "--expected-trunk"),
        ("expected_tree", "--expected-tree"),
    ):
        if given[key] is not None:
            argv += [flag, given[key]]
    return [*argv, *extra]


def run_integrate(composed: ComposedLane, capsys, *extra: str, cwd=None, **identities):
    """`main(["integrate", ...])` in the lane; `(exit code, stdout, stderr)`."""
    argv = integrate_argv(composed, *extra, **identities)
    return run_main(argv, cwd or composed.path, capsys)


@covers("invalid identity argument")
@pytest.mark.parametrize(
    ("flag", "key", "value"),
    [
        ("--expected-tree", "expected_tree", ABBREVIATED_SHA),
        ("--expected-tree", "expected_tree", "UPPER"),
        ("--expected-trunk", "expected_trunk", ABBREVIATED_SHA),
        ("--expected-trunk", "expected_trunk", "UPPER"),
    ],
    ids=["tree-abbreviated", "tree-uppercase", "trunk-abbreviated", "trunk-uppercase"],
)
def test_integrate_a_malformed_identity_is_one_invalid_identity_block(
    flag, key, value, composed_with_origin, capsys
):
    composed = composed_with_origin
    if value == "UPPER":
        value = getattr(composed, key).upper()
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys, **{key: value})

    assert (code, out) == (1, "")
    (block,) = parse_blocks(err)
    assert block["refused"] == INVALID_IDENTITY
    assert flag in block["why"]
    assert "40-hex" in block["how"]
    assert observed_state(composed) == before


@covers("invalid identity argument")
def test_integrate_two_malformed_identities_are_still_one_block(
    composed_with_origin, capsys
):
    code, _, err = run_integrate(
        composed_with_origin,
        capsys,
        expected_trunk=ABBREVIATED_SHA,
        expected_tree="ZZ",
    )

    (block,) = parse_blocks(err)
    assert code == 1
    assert "--expected-trunk" in block["why"]
    assert "--expected-tree" in block["why"]


@pytest.mark.parametrize("key", ["expected_trunk", "expected_tree"])
def test_integrate_an_omitted_identity_flag_is_a_usage_error(
    key, composed_with_origin, capsys
):
    before = observed_state(composed_with_origin)

    code, out, err = run_integrate(composed_with_origin, capsys, **{key: None})

    assert (code, out) == (2, "")
    assert "--" + key.replace("_", "-") in err
    assert observed_state(composed_with_origin) == before


@covers("tree mismatch")
def test_integrate_a_valid_but_wrong_tree_is_a_tree_mismatch(
    composed_with_origin, capsys
):
    before = observed_state(composed_with_origin)

    code, out, err = run_integrate(
        composed_with_origin, capsys, expected_tree=WRONG_SHA
    )

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == "tree mismatch"
    assert f"expected: {WRONG_SHA}" in block["why"]
    assert observed_state(composed_with_origin) == before


@covers("trunk moved")
def test_integrate_a_valid_but_wrong_trunk_is_trunk_moved(composed_with_origin, capsys):
    before = observed_state(composed_with_origin)

    code, out, err = run_integrate(
        composed_with_origin, capsys, expected_trunk=WRONG_SHA
    )

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == "trunk moved"
    assert f"expected: {WRONG_SHA}" in block["why"]
    assert observed_state(composed_with_origin) == before


def test_help_lists_open_compose_and_integrate(capsys):
    code, out, _ = run_main(["--help"], Path.cwd(), capsys)

    assert code == 0
    for command in ("open", "compose", "integrate"):
        assert f"\n    {command}" in out


# --- the integrate command: success -------------------------------------------


def branch_exists_in(repo_path: Path, branch: str) -> bool:
    return git_succeeds(
        repo_path, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"
    )


def assert_integrated(
    composed: ComposedLane, out: str, former_trunk: str
) -> dict[str, str]:
    """The lane's former HEAD is the trunk branch's tip by fast-forward alone; the
    gate file, worktree and branch are gone; the output says where to go on."""
    printed = parse_output(out)
    repo_path = composed.repo.path
    former_head = printed["former-head"]
    assert git(repo_path, "rev-parse", "main") == former_head
    assert git(repo_path, "rev-parse", "HEAD") == former_head
    assert git(repo_path, "rev-list", "--merges", f"{former_trunk}..main") == ""
    assert is_ancestor(repo_path, former_trunk, former_head)
    assert not (composed.path / GATE_RELATIVE_PATH).exists()
    assert not composed.path.exists()
    assert str(composed.path) not in git(repo_path, "worktree", "list", "--porcelain")
    assert not branch_exists_in(repo_path, composed.name)
    return printed


def test_integrate_without_a_remote_fast_forwards_trunk_and_removes_the_lane(
    composed_without_remote, capsys
):
    composed = composed_without_remote
    lane_head = git(composed.path, "rev-parse", "HEAD")

    code, out, err = run_integrate(composed, capsys)

    assert (code, err) == (0, "")
    printed = assert_integrated(composed, out, composed.expected_trunk)
    assert printed["former-head"] == lane_head
    assert printed["now-at"] == lane_head
    assert printed["trunk"] == "main"
    assert printed["continue-in"] == str(composed.repo.path.resolve())
    assert printed["recover"] == f"git branch {composed.name} {lane_head}"
    assert printed["pushed"] == "nothing; run git push yourself if wanted"
    assert out.splitlines()[-1].startswith("pushed: nothing")


def test_integrate_on_a_remote_tracking_trunk_moves_only_the_local_branch(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    origin_refs = git(composed.repo.origin, "for-each-ref")
    tracking = git(composed.repo.path, "rev-parse", "origin/main")

    code, out, err = run_integrate(composed, capsys, "--local-trunk")

    assert (code, err) == (0, "")
    printed = assert_integrated(composed, out, composed.expected_trunk)
    assert printed["continue-in"] == str(composed.repo.path.resolve())
    assert git(composed.repo.origin, "for-each-ref") == origin_refs
    assert git(composed.repo.path, "rev-parse", "origin/main") == tracking
    assert printed["former-head"] != tracking


@covers("git command failed")
def test_integrate_never_overwrites_an_ignored_file_in_the_trunk_worktree(
    composed_without_remote, capsys
):
    composed = composed_without_remote
    trunk_worktree = composed.repo.path
    exclude = Path(git(trunk_worktree, "rev-parse", "--git-path", "info/exclude"))
    exclude = trunk_worktree / exclude if not exclude.is_absolute() else exclude
    exclude.write_text("lane.txt\n", encoding="utf-8")
    precious = trunk_worktree / "lane.txt"
    precious.write_text("precious\n", encoding="utf-8")
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == "git command failed"
    assert "merge --ff-only" in block["why"]
    assert precious.read_text(encoding="utf-8") == "precious\n"
    assert observed_state(composed) == before
    assert composed.path.exists()
    assert branch_exists_in(trunk_worktree, composed.name)


# --- the integrate command: each check refuses alone, through main ------------


def fault_tree_mismatch(composed) -> list[str]:
    commit_file(composed.path, "later.txt", "later\n", "later work")
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
    git(composed.repo.path, "remote", "set-url", "origin", GITHUB_URL)
    return []


SINGLE_FAULTS = {
    "tree mismatch": (fault_tree_mismatch, "tree mismatch", ["expected:", "live:"]),
    "gate deleted": (
        fault_gate_deleted,
        REVIEW_GATE,
        ["/code-review --since"],
    ),
    "trunk moved": (fault_trunk_moved, "trunk moved", ["expected:", "live:"]),
    "dirty lane": (fault_untracked_file_in_lane, UNCOMMITTED, ["scratch.txt"]),
    "not an ancestor": (fault_local_trunk_ahead, FAST_FORWARD, ["not an ancestor"]),
    "checked out nowhere": (
        fault_trunk_checked_out_nowhere,
        FAST_FORWARD,
        ["checked out nowhere"],
    ),
    "dirty trunk worktree": (
        fault_dirty_trunk_worktree,
        FAST_FORWARD,
        ["has uncommitted changes"],
    ),
    "trunk is a tag": (fault_trunk_is_a_tag, FAST_FORWARD, ["does not exist"]),
    "github origin": (fault_github_origin, "PR repository", ["/pr"]),
}


@pytest.mark.parametrize(
    "fault",
    [
        pytest.param(fault, marks=covers(SINGLE_FAULTS[fault][1]))
        for fault in sorted(SINGLE_FAULTS)
    ],
)
def test_integrate_each_fault_refuses_alone_and_changes_nothing(
    fault, composed_with_origin, capsys
):
    composed = composed_with_origin
    inject, what, pinned = SINGLE_FAULTS[fault]
    extra = inject(composed)
    gate = composed.path / GATE_RELATIVE_PATH
    gate_before = gate.read_bytes() if gate.exists() else None
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys, *extra)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == what
    text = " ".join(block.values())
    assert all(fragment in text for fragment in pinned)
    assert observed_state(composed) == before
    assert (gate.read_bytes() if gate.exists() else None) == gate_before
    assert composed.path.exists()
    assert branch_exists_in(composed.repo.path, composed.name)


def test_integrate_the_github_origin_row_integrates_with_local_trunk(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    fault_github_origin(composed)

    code, out, _ = run_integrate(composed, capsys, "--local-trunk")

    assert code == 0
    assert (
        git(composed.repo.path, "rev-parse", "main") == parse_output(out)["former-head"]
    )


def test_integrate_a_fault_with_no_remote_reports_trunk_moved_then_fast_forward(
    composed_without_remote, capsys
):
    advance_trunk(composed_without_remote.repo)
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(composed_without_remote, capsys)

    blocks = parse_blocks(err)
    assert (code, out) == (1, "")
    assert [block["refused"] for block in blocks] == ["trunk moved", FAST_FORWARD]
    assert observed_state(composed_without_remote) == before


@covers("tree mismatch")
@covers(REVIEW_GATE)
@covers("trunk moved")
def test_integrate_three_faults_are_reported_together_in_order(
    composed_with_origin, capsys
):
    composed = composed_with_origin
    commit_file(composed.path, "later.txt", "later\n", "later work")
    advance_origin(composed.repo)
    before = observed_state(composed)

    code, out, err = run_integrate(composed, capsys)

    blocks = parse_blocks(err)
    assert (code, out) == (1, "")
    assert [block["refused"] for block in blocks] == [
        "tree mismatch",
        REVIEW_GATE,
        "trunk moved",
    ]
    assert observed_state(composed) == before


@covers("PR repository")
@covers(UNCOMMITTED)
def test_integrate_a_pr_repository_refusal_alongside_others_ends_with_the_note(
    composed_with_origin, capsys
):
    fault_github_origin(composed_with_origin)
    leave_untracked_file(composed_with_origin.path)

    code, _, err = run_integrate(composed_with_origin, capsys)

    assert code == 1
    assert [block["refused"] for block in parse_blocks(err)] == [
        UNCOMMITTED,
        "PR repository",
    ]
    assert err.rstrip().splitlines()[-1].startswith("note: this is a PR repository")


# --- the integrate command: where it runs -------------------------------------


@covers(NOT_IN_A_LANE)
def test_integrate_the_primary_checkout_on_trunk_is_not_a_lane(
    composed_without_remote, capsys
):
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(
        composed_without_remote, capsys, cwd=composed_without_remote.repo.path
    )

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == NOT_IN_A_LANE
    assert "lane.py open" in block["how"]
    assert observed_state(composed_without_remote) == before


@covers(NOT_IN_A_LANE)
def test_integrate_a_detached_head_in_a_linked_worktree_is_not_a_lane(
    composed_without_remote, capsys
):
    detached = add_linked_worktree(composed_without_remote.repo, "scratch")
    git(detached, "switch", "-q", "--detach")
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(composed_without_remote, capsys, cwd=detached)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == NOT_IN_A_LANE
    assert observed_state(composed_without_remote) == before


@covers(NOT_IN_A_LANE)
def test_integrate_a_linked_worktree_on_the_trunk_branch_is_not_a_lane(
    composed_without_remote, capsys
):
    repo = composed_without_remote.repo
    git(repo.path, "switch", "-q", "-c", "elsewhere")
    on_trunk = add_linked_worktree(repo, "main-copy", start="main")
    git(on_trunk, "switch", "-q", "main")
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(composed_without_remote, capsys, cwd=on_trunk)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == NOT_IN_A_LANE
    assert observed_state(composed_without_remote) == before


@covers("trunk ref cannot be resolved")
def test_integrate_an_unresolvable_trunk_is_exactly_one_block(
    composed_without_remote, capsys
):
    leave_untracked_file(composed_without_remote.path)
    before = observed_state(composed_without_remote)

    code, out, err = run_integrate(
        composed_without_remote, capsys, "--trunk", "nonexistent-ref"
    )

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == "trunk ref cannot be resolved"
    assert "nonexistent-ref" in block["why"]
    assert observed_state(composed_without_remote) == before


@covers("not a git repository")
def test_integrate_outside_a_repository_is_a_block_not_a_traceback(
    composed_without_remote, plain_directory, capsys
):
    code, out, err = run_integrate(composed_without_remote, capsys, cwd=plain_directory)

    (block,) = parse_blocks(err)
    assert (code, out) == (1, "")
    assert block["refused"] == "not a git repository"
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


# --- the integrate command: the apply sequence --------------------------------


def apply_trace(composed: ComposedLane, capsys, monkeypatch):
    """Run integrate; return what each apply call saw: `(subcommand words, cwd,
    gate file present, lane directory present)` at the moment it started."""
    gate = composed.path / GATE_RELATIVE_PATH
    seen = []
    real = lane_core._run

    def recording(argv, cwd):
        seen.append((list(argv[1:]), cwd, gate.exists(), composed.path.exists()))
        return real(argv, cwd)

    monkeypatch.setattr(lane_core, "_run", recording)
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

    assert [call[0] for call in trace if call[0][0] != "rev-parse"] == [
        ["merge", "--ff-only", "--no-overwrite-ignore", lane_head],
        ["worktree", "remove", str(composed.path)],
        ["branch", "-d", composed.name],
    ]
    assert {call[1] for call in trace} == {trunk}
    ff, remove, delete = (call for call in trace if call[0][0] != "rev-parse")
    # (gate present, lane present) when each step started
    assert (ff[2], ff[3]) == (True, True)
    assert (remove[2], remove[3]) == (False, True)
    assert (delete[2], delete[3]) == (False, False)


def test_the_gate_file_name_integrate_removes_is_the_hooks():
    assert lane.GATE_FILE_NAME == load_pr_hook()._GATE_FILE_NAME
