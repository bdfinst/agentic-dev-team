#!/usr/bin/env python3
"""lane.py -- identity-checked lanes: open, compose, integrate.

`open`, `compose` and `integrate` are the commands. Usage errors exit 2,
refusals exit 1 (blocks on stderr), success 0.

Known limit, tracked as a follow-up: the delegated calls (`branch_diff_gate_hash`,
`project_root`, `default_base_ref`) carry no lane timeout, and `lane_core._run`
kills only the direct git process on a timeout, not its process group.

Import whitelist (pinned by an AST test): the standard library, `lane_core`,
`git_origin_host` and, from the plugin's `hooks/lib`, `artifact_paths`,
`git_safe_diff` and `review_gate_hash`. The PR hook `hooks/pre_pr_review.py`
is loaded by path inside `_review_gate_refusal`, never imported. Stdlib only
otherwise. See ADR 0014 and ADR 0031.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"

# `lane_core` first: it is the one owner of the import-path setup (it puts
# hooks/lib and this directory on sys.path), so the hooks/lib libraries below
# resolve only after it has been imported.
import lane_core

# isort: split

import artifact_paths
import git_origin_host
import git_safe_diff
import review_gate_hash

#: Between the primary checkout's name and the lane name in a default path.
LANE_DIR_INFIX = "-lane-"

NAME_PATTERN_PROBLEM = (
    "it must start with a letter or digit and use only safe characters"
)
NAME_GIT_PROBLEM = "git does not accept it as a branch name"

#: Fast-forward when possible whatever `merge.ff` says, else a merge commit.
#: `--no-overwrite-ignore` guards only the fast-forward case: git's `ort` merge
#: ignores it (checked at runtime against git 2.43). A true merge is guarded by
#: `_merge_attempt`, which refuses first when the merge would write a tracked
#: file over an ignored local file.
MERGE_ARGS = ("merge", "--ff", "--no-edit", "--no-overwrite-ignore")

#: Appended to git's message when the unmerged paths could not be listed.
UNMERGED_UNREADABLE = "could not list the unmerged paths"

#: What `compose` suggests in a PR repository, instead of an `integrate` line.
PR_NEXT_STEP = "open a PR with /pr (or pass --local-trunk to integrate locally)"
ORIGIN_HOST_GITHUB = "github"

#: The PR hook whose review-gate decision `integrate` reuses, loaded by path.
PR_HOOK_PATH = _HOOKS_DIR / "pre_pr_review.py"
PR_HOOK_MODULE = "pre_pr_review"

TRUNK_HELP = "trunk ref (default: origin's default branch, else main or master)"

OPEN_COMMAND = "open"
COMPOSE_COMMAND = "compose"
INTEGRATE_COMMAND = "integrate"

#: What `compose` prints for `expected-trunk` and `expected-tree`: a full SHA-1
#: (40 hex). IDENTITY_PATTERN admits only SHA-1 (40 hex); a SHA-256 repository
#: prints 64 hex and is not supported.
IDENTITY_PATTERN = re.compile(r"[0-9a-f]{40}")
EXPECTED_TRUNK_FLAG = "--expected-trunk"
EXPECTED_TREE_FLAG = "--expected-tree"

#: The keys of `integrate`'s output lines, success and failure.
KEY_TRUNK = "trunk"
KEY_FORMER_HEAD = "former-head"
KEY_NOW_AT = "now-at"
KEY_CONTINUE_IN = "continue-in"
KEY_RECOVER = "recover"
KEY_DONE = "done"
KEY_REMAINING = "remaining"
#: `done:` names this when no step has finished.
NO_STEP_DONE = "nothing"

#: Last line of a successful `integrate`: nothing was published.
PUSHED_NOTHING_LINE = "pushed: nothing; run git push yourself if wanted"

#: The PR hook's gate file, which `integrate` removes with the lane. A test
#: pins it to the hook's own `_GATE_FILE_NAME`.
GATE_FILE_NAME = ".pr-review-passed"

#: Fast-forward only, and never over an ignored file in the trunk worktree.
FAST_FORWARD_ARGS = ("merge", "--ff-only", "--no-overwrite-ignore")


@dataclass(frozen=True)
class Command:
    """One command. `name` is the only place the command's name is written.

    `build_parser` adds the sub-parser under `name` and hands it to
    `configure`. The handler is not attached with `set_defaults`: the tests
    substitute handlers by replacing entries of `COMMANDS`, so dispatch reads
    `COMMANDS` at call time.
    """

    name: str
    help: str
    configure: Callable[[argparse.ArgumentParser], None]
    handler: Callable[[argparse.Namespace, Path], int]


def _add_trunk_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trunk", help=TRUNK_HELP)


def _configure_open(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="branch name for the lane")
    parser.add_argument(
        "--path", help="worktree directory (default: beside the primary checkout)"
    )
    _add_trunk_argument(parser)


def _name_problem(name: str, cwd: Path) -> str | None:
    """Why `name` is unusable, or None. The pattern runs before git sees it."""
    if lane_core.LANE_NAME_PATTERN.fullmatch(name) is None:
        return NAME_PATTERN_PROBLEM
    if not lane_core.git_ok(["check-ref-format", "--branch", name], cwd):
        return NAME_GIT_PROBLEM
    return None


def _validated_name(name: str, cwd: Path) -> str:
    problem = _name_problem(name, cwd)
    if problem is not None:
        raise lane_core.RefusalError(lane_core.invalid_lane_name_refusal(name, problem))
    return name


def _require_free_branch(name: str, cwd: Path) -> None:
    if lane_core.branch_exists(name, cwd):
        raise lane_core.RefusalError(lane_core.branch_exists_refusal(name))


def _lane_path(name: str, path_arg: str | None, cwd: Path) -> Path:
    """`--path` made absolute, else beside the primary checkout (even from a lane)."""
    if path_arg is not None:
        return Path(os.path.normpath(cwd / path_arg))
    primary = lane_core.primary_checkout(cwd)
    return primary.parent / f"{primary.name}{LANE_DIR_INFIX}{name.replace('/', '-')}"


def _require_free_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise lane_core.RefusalError(lane_core.path_exists_refusal(path))


def _print_displayed(lines: Sequence[str]) -> None:
    """Print each line through `display_text`: a branch name or path comes from
    git or the file system, and a control character in one must not forge a
    line or rewrite the terminal."""
    for line in lines:
        print(lane_core.display_text(line))


def cmd_open(args: argparse.Namespace, cwd: Path) -> int:
    name = _validated_name(args.name, cwd)
    lane_core.require_work_tree(cwd)
    _require_free_branch(name, cwd)
    path = _lane_path(name, args.path, cwd)
    _require_free_path(path)
    _, commit = lane_core.resolve_trunk_commit(args.trunk, cwd)
    try:
        lane_core.git_text(
            ["worktree", "add", "--quiet", "-b", name, str(path), commit], cwd
        )
    except lane_core.RefusalError:
        # A concurrent open may have taken the path or the branch since the
        # checks. A failed `worktree add -b` can leave its own new branch
        # behind, so a branch counts as taken only when a worktree holds it.
        if lane_core.branch_checked_out(name, cwd):
            raise lane_core.RefusalError(lane_core.branch_exists_refusal(name))
        _require_free_path(path)
        raise
    _print_displayed([f"worktree: {path}", f"branch: {name}"])
    return lane_core.EXIT_OK


# --- shared by lane commands ------------------------------------------------


@dataclass(frozen=True)
class EnteredLane:
    """The lane a command runs in, and what `--trunk` resolved to."""

    context: lane_core.LaneContext
    trunk_arg: str | None
    trunk_commit: str


def _enter_lane(trunk_arg: str | None, cwd: Path) -> EnteredLane:
    """The lane `cwd` is in and the trunk commit, or a refusal.

    Shared by every command that works inside a lane: a repository, a
    resolvable trunk and a lane, checked in that order.
    """
    lane_core.require_work_tree(cwd)
    trunk_ref, trunk_commit = lane_core.resolve_trunk_commit(trunk_arg, cwd)
    context = lane_core.lane_context(trunk_ref, cwd)
    if context is None:
        raise lane_core.RefusalError(lane_core.not_in_a_lane_refusal(cwd, trunk_ref))
    return EnteredLane(context, trunk_arg, trunk_commit)


def _dirty_refusal(lane_path: Path) -> lane_core.Refusal | None:
    """Why the lane is not clean: uncommitted changes or an unfinished merge."""
    dirty_paths, merge_in_progress = lane_core.worktree_state(lane_path)
    if not dirty_paths and not merge_in_progress:
        return None
    if merge_in_progress:
        return lane_core.unfinished_merge_refusal(dirty_paths)
    return lane_core.lane_has_uncommitted_changes_refusal(dirty_paths)


def _require_clean(lane_path: Path) -> None:
    refusal = _dirty_refusal(lane_path)
    if refusal is not None:
        raise lane_core.RefusalError(refusal)


def _is_pr_repository(lane_path: Path) -> bool:
    """True when the `origin` remote is on GitHub: work lands through a PR.

    The only origin lookup. No `origin` is False; a git failure raises, so a
    failed lookup is never read as "not GitHub".
    """
    host = git_origin_host.classify(lane_core.origin_url(lane_path))
    return host == ORIGIN_HOST_GITHUB


# --- compose ----------------------------------------------------------------


def _configure_compose(parser: argparse.ArgumentParser) -> None:
    _add_trunk_argument(parser)


def _integrate_command(entered: EnteredLane, tree: str) -> str:
    """The `integrate` line a reviewer runs next; `--trunk` only when it was given."""
    command = (
        f"lane.py integrate {EXPECTED_TRUNK_FLAG} {entered.trunk_commit} "
        f"{EXPECTED_TREE_FLAG} {tree}"
    )
    if entered.trunk_arg is None:
        return command
    return f"{command} --trunk {entered.trunk_arg}"


def _next_step(entered: EnteredLane, tree: str) -> str:
    """`integrate`, or `/pr` when origin is on GitHub (`integrate` then needs `--local-trunk`)."""
    if _is_pr_repository(entered.context.lane_path):
        return PR_NEXT_STEP
    return _integrate_command(entered, tree)


@dataclass(frozen=True)
class MergeTarget:
    """What `compose` merges: `ref` for messages, `commit` (a SHA) for git."""

    ref: str
    commit: str


def _merge_targets(entered: EnteredLane) -> list[MergeTarget]:
    """The trunk commit, plus the local trunk branch when it holds work the trunk lacks.

    Both targets are commit SHAs read once here, so what is checked and merged
    is what `expected-trunk` names. The local branch (`main` for `origin/main`)
    joins only when it exists and is not contained in the trunk commit. When it
    contains the trunk commit, it is the only target: merging it brings the
    trunk commit along.
    """
    context = entered.context
    lane_path = context.lane_path
    trunk_ref_target = MergeTarget(context.trunk_ref, entered.trunk_commit)
    if context.trunk_branch is None:
        return [trunk_ref_target]
    trunk_tip = lane_core.branch_commit(context.trunk_branch, lane_path)
    if trunk_tip is None:
        return [trunk_ref_target]
    trunk_branch_target = MergeTarget(context.trunk_branch, trunk_tip)
    if lane_core.is_ancestor(
        trunk_branch_target.commit, trunk_ref_target.commit, lane_path
    ):
        return [trunk_ref_target]
    if lane_core.is_ancestor(
        trunk_ref_target.commit, trunk_branch_target.commit, lane_path
    ):
        return [trunk_branch_target]
    return [trunk_ref_target, trunk_branch_target]


@dataclass(frozen=True)
class Snapshot:
    """The lane as it was before compose touched it."""

    head: str
    tree: str


def _snapshot(lane_path: Path) -> Snapshot:
    head = lane_core.head_commit(lane_path)
    return Snapshot(head=head, tree=lane_core.commit_tree(head, lane_path))


class SettledRefusal(lane_core.RefusalError):
    """A refusal raised once the lane's final state is known.

    The lane was restored, or the refusal says it could not be verified as
    restored. Nothing more is undone for it.
    """


def _restore_verified(snapshot: Snapshot, lane_path: Path) -> bool:
    """Put the lane back to `snapshot`, then check that it is there.

    `reset --hard` also undoes an earlier successful merge and a rejected merge
    that left a merged index without `MERGE_HEAD`. True only when HEAD and its
    tree match, no path is unmerged or dirty and no merge is in progress.

    The unmerged-index and tree checks are deliberate defence in depth: each
    is implied by the dirty-tree and HEAD checks today, and costs one git call
    to stay true if either of those readers changes. The cleanliness read is
    the shared `worktree_state`.
    """
    try:
        if lane_core.merge_in_progress(lane_path):
            lane_core.git_ok(["merge", "--abort"], lane_path)
    except lane_core.RefusalError:
        # The probe failed. `reset --hard` below also ends a merge, and the
        # verification decides whether the lane is back: a failed probe must
        # not leave a failed merge standing.
        pass
    try:
        lane_core.git_ok(["reset", "--hard", snapshot.head], lane_path)
        if _snapshot(lane_path) != snapshot:
            return False
        if lane_core.has_unmerged_entries(lane_path):
            return False
        dirty_paths, merge_in_progress = lane_core.worktree_state(lane_path)
        return not dirty_paths and not merge_in_progress
    except lane_core.RefusalError:
        return False


def _settled(
    snapshot: Snapshot,
    lane_path: Path,
    failed_step: str,
    cause: str,
    refusal_if_restored: lane_core.Refusal,
) -> lane_core.Refusal:
    """`refusal_if_restored` once the restore is verified, else the unverified refusal.

    The one place that states the rule: a refusal claims the lane was restored
    only after a verified restore.
    """
    if _restore_verified(snapshot, lane_path):
        return refusal_if_restored
    return lane_core.compose_restore_unverified_refusal(
        failed_step, snapshot.head, cause
    )


def _failed_merge_refusal(
    target: MergeTarget,
    attempt: lane_core.GitAttempt,
    snapshot: Snapshot,
    lane_path: Path,
) -> lane_core.Refusal:
    """Read why the merge failed, restore the lane, and say which of the two happened.

    The evidence is read before the restore: the restore erases it. The
    "restored" claim in the refusal is made only after the restore is verified.
    """
    detail = attempt.detail
    try:
        unmerged = lane_core.unmerged_paths(lane_path)
    except lane_core.RefusalError as unreadable:
        unmerged = []
        detail = f"{detail}; {UNMERGED_UNREADABLE}: {unreadable.refusal.why}"
    cause = (
        lane_core.compose_conflict_cause(unmerged)
        if unmerged
        else lane_core.compose_merge_failed_cause(attempt.command, detail)
    )
    refusal_if_restored = (
        lane_core.compose_conflict_refusal(target.ref, unmerged)
        if unmerged
        else lane_core.compose_merge_failed_refusal(target.ref, attempt.command, detail)
    )
    return _settled(
        snapshot,
        lane_path,
        lane_core.merge_failure_step(target.ref),
        cause,
        refusal_if_restored,
    )


def _merge_attempt(target: MergeTarget, lane_path: Path) -> lane_core.GitAttempt:
    """Merge `target`, unless that would write over an ignored local file.

    The lane is clean, so a local file at a path the merge adds is one git
    ignores, and git's own merge replaces it silently. The refusal is built as
    a failed attempt, so it takes the same restore path as a failed merge.
    """
    args = [*MERGE_ARGS, target.commit]
    in_the_way = lane_core.local_files_a_merge_would_overwrite(target.commit, lane_path)
    if not in_the_way:
        return lane_core.git_attempt(args, lane_path)
    detail = (
        f"it would overwrite ignored local files: {lane_core.listed_items(in_the_way)}"
    )
    return lane_core.GitAttempt(False, shlex.join(["git", *args]), detail, "")


def _merge_all(
    targets: Sequence[MergeTarget],
    snapshot: Snapshot,
    lane_path: Path,
    merged: list[MergeTarget],
) -> None:
    """Merge each target the lane lacks; on a failed merge, restore and refuse.

    Each target that merged is appended to `merged` at once, so the caller
    knows what was merged when a later step raises.
    """
    for target in targets:
        if lane_core.is_ancestor(target.commit, "HEAD", lane_path):
            continue
        attempt = _merge_attempt(target, lane_path)
        if not attempt.ok:
            raise SettledRefusal(
                _failed_merge_refusal(target, attempt, snapshot, lane_path)
            )
        merged.append(target)


def _head_moved(snapshot: Snapshot, lane_path: Path) -> bool:
    """True when HEAD is not `snapshot.head`, or cannot be read."""
    try:
        return lane_core.head_commit(lane_path) != snapshot.head
    except lane_core.RefusalError:
        return True


def _merge_and_read(
    entered: EnteredLane, targets: Sequence[MergeTarget], snapshot: Snapshot
) -> tuple[str, str]:
    """Merge, then read the `(tree, next step)` to print; restore on any failure.

    Everything between the snapshot and the reads sits in one envelope, so a
    failure between two merges or while reading leaves the lane as it was. A
    git failure that is not a failed merge, after HEAD moved, restores the
    lane and then says so in compose's words; it names only the targets that
    were merged.
    """
    lane_path = entered.context.lane_path
    merged: list[MergeTarget] = []
    try:
        _merge_all(targets, snapshot, lane_path, merged)
        tree = lane_core.head_tree(lane_path)
        return tree, _next_step(entered, tree)
    except SettledRefusal:
        raise
    except lane_core.RefusalError as failure:
        if not _head_moved(snapshot, lane_path):
            raise
        raise SettledRefusal(
            _settled(
                snapshot,
                lane_path,
                _failure_step(merged),
                failure.refusal.why,
                lane_core.compose_restored_refusal(failure.refusal),
            )
        ) from failure
    except BaseException as interruption:
        try:
            verified = _restore_verified(snapshot, lane_path)
        except BaseException:  # noqa: BLE001 - a second interrupt: not verified
            verified = False
        if not verified:
            # Say so before the interrupt propagates: a lane left half merged
            # must not look restored. The bare `raise` re-raises the original.
            lane_core.emit_refusals(
                [
                    lane_core.compose_restore_unverified_refusal(
                        _failure_step(merged),
                        snapshot.head,
                        type(interruption).__name__,
                    )
                ]
            )
        raise


def _failure_step(merged: Sequence[MergeTarget]) -> str:
    """The step a compose failure is reported at: after the merges done so far."""
    return lane_core.compose_failure_step_after([target.ref for target in merged])


def cmd_compose(args: argparse.Namespace, cwd: Path) -> int:
    """Merge trunk into the lane; print the identities a reviewer checks.

    Compose assumes it is the only git process in the lane for the duration of
    the call: it does not lock the lane, and its restore (`reset --hard`)
    discards an edit made to the lane while the merge runs.
    """
    entered = _enter_lane(args.trunk, cwd)
    lane_path = entered.context.lane_path
    _require_clean(lane_path)
    snapshot = _snapshot(lane_path)
    tree, next_step = _merge_and_read(entered, _merge_targets(entered), snapshot)
    _print_displayed(
        [
            f"lane: {entered.context.branch}",
            f"trunk: {entered.context.trunk_ref}",
            f"expected-trunk: {entered.trunk_commit}",
            f"expected-tree: {tree}",
            f"next: {next_step}",
        ]
    )
    return lane_core.EXIT_OK


# --- integrate: the check engine ----------------------------------------------


@dataclass(frozen=True)
class CheckContext:
    """What every integrate check reads: the lane entered, the lane's HEAD
    commit read once when the checks start, and the identities the reviewer
    holds (`expected-trunk`, `expected-tree` as `compose` printed them);
    `allow_local_integration` is `--local-trunk`.

    `head` and `entered.trunk_commit` are the two facts the apply is bound to:
    check 1 compares the tree of this very `head`, check 3 this very trunk
    commit, and `_plan_integrate` carries both on to the apply steps.
    """

    entered: EnteredLane
    head: str
    expected_trunk: str
    expected_tree: str
    allow_local_integration: bool = False


@dataclass(frozen=True)
class Check:
    """One integrate check. `run` returns its refusal, or None when it holds."""

    order: int
    name: str
    run: Callable[[CheckContext], lane_core.Refusal | None]


def _check_tree_matches(ctx: CheckContext) -> lane_core.Refusal | None:
    lane = ctx.entered.context
    live = lane_core.commit_tree(ctx.head, lane.lane_path)
    if live == ctx.expected_tree:
        return None
    return lane_core.tree_mismatch_refusal(ctx.expected_tree, live, lane.trunk_ref)


def _load_pr_hook():
    """The PR hook module, executed from its file. Nothing is registered in `sys.modules`.

    The hook puts its own directories on `sys.path` when it runs; `sys.path`
    is restored afterwards, so repeated loads in one process do not grow it.
    """
    spec = importlib.util.spec_from_file_location(PR_HOOK_MODULE, PR_HOOK_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {PR_HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
    return module


#: The hook's `matched_rule` -> what it means for a lane. The hook's own
#: message is never shown: it says to retry `gh pr create` and offers a bypass
#: variable that `integrate` ignores. A rule missing here still shows its name.
GATE_RULE_WORDING = {
    "pre-pr-review": (
        "the review gate file is missing, unreadable, or was written for "
        "different content than this lane's diff"
    ),
    "gate-setup-failure-empty-digest": (
        "the lane's diff hashed to the empty digest, so no review can be bound to it"
    ),
    "registry-read-failure": (
        "the registered review agents could not be read, so a review-agent "
        "dispatch failure cannot be ruled out"
    ),
    "dispatch-failure-veto": (
        "a review agent failed to dispatch for this content and has not been dispatched again"
    ),
    "dispatch-ledger-read-failure": "the review dispatch ledger could not be read",
    "dispatch-evidence-insufficient": (
        "too few distinct review agents were dispatched for this content"
    ),
    "dispatch-evidence-stale": (
        "the review-agent dispatches for this content are outside the recency window"
    ),
    "dispatch-evidence-different-content": (
        "review agents were dispatched, but for different content than this lane's diff"
    ),
    "dispatch-evidence-missing": (
        "no review-agent dispatch was recorded for this content"
    ),
}
GATE_RULE_FALLBACK_WORDING = "the review gate rejected this lane"
#: Shown as the rule when the hook gave no `matched_rule`.
NO_RULE_NAMED = "none given"


def _gate_rejection_why(matched_rule: str) -> str:
    wording = GATE_RULE_WORDING.get(matched_rule, GATE_RULE_FALLBACK_WORDING)
    return f"{wording} (rule: {matched_rule or NO_RULE_NAMED})"


def _changed_files(lane_path: Path, trunk_ref: str) -> list[str]:
    """The paths of the lane's diff against trunk.

    Raises `RefusalError` (`git command failed`) when git cannot say: a
    timeout, a launch failure or a non-zero exit.
    """
    command = f"git diff --name-only {trunk_ref}...HEAD"
    try:
        completed = git_safe_diff.run_safe_git_diff(
            ["--name-only"],
            cwd=lane_path,
            text=True,
            target=f"{trunk_ref}...HEAD",
            timeout=lane_core.GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as failure:
        raise _git_failed(command, lane_core.GIT_TIMED_OUT_DETAIL) from failure
    except OSError as failure:
        raise _git_failed(command, str(failure)) from failure
    if completed.returncode != 0:
        raise _git_failed(command, lane_core.git_message(completed))
    return [line for line in completed.stdout.splitlines() if line]


def _git_failed(command: str, detail: str) -> lane_core.RefusalError:
    return lane_core.RefusalError(lane_core.git_command_failed_refusal(command, detail))


def _gate_file(lane_path: Path) -> Path:
    """The PR hook's gate file for `lane_path`; the one resolver.

    The check (`_review_gate_refusal`) and the apply (`_plan_integrate`) both
    resolve the gate through this function, so the file that was checked is the
    file that is removed. Reading only (`migrate=False`), under the filtered git
    environment.
    """
    with lane_core.filtered_process_environment():
        return artifact_paths.resolve_file(
            "memory", GATE_FILE_NAME, lane_path, migrate=False
        )


def _review_gate_refusal(lane_path: Path, trunk_ref: str) -> lane_core.Refusal | None:
    """The refusal when the review gate would reject this lane, else None.

    The same decision as `pre_pr_review`'s `main()` for the lane's diff against
    `trunk_ref`: `_evaluate_gate` is the hook's own, loaded by path. This is the
    one function that touches the hook's private names (`_evaluate_gate`,
    `_GATE_FILE_NAME`); a rename there fails the parity tests, not a release.
    A hook whose gate file name is not `GATE_FILE_NAME` is refused: the check
    and the apply would then work on different files.

    Fail closed: an unloadable or degraded hook, an empty diff, and any
    exception are all this one refusal, never a traceback. A git call that
    fails or times out while the changed files are read is the exception: it is
    the `git command failed` block, so `check_lane` stops on it.
    Reading only: the gate path is resolved with `migrate=False` and nothing is
    unlinked (the hook's `main()` does that on success; `integrate` does it at
    apply time). `PR_GATE_BYPASS_REASON` lives in the hook's `main()`, which is
    never called, so it has no effect here.

    The delegated code (hash, hook, `project_root`) starts its own git
    processes, so the whole evaluation runs under the filtered git environment
    (an exported `GIT_DIR` cannot redirect it), and the one call that takes a
    timeout gets `GIT_TIMEOUT_SECONDS`.
    """

    def _refuse(why: str) -> lane_core.Refusal:
        return lane_core.review_gate_refusal(trunk_ref, why)

    try:
        with lane_core.filtered_process_environment():
            hook = _load_pr_hook()
            if hook.branch_diff_gate_hash is not review_gate_hash.branch_diff_gate_hash:
                return _refuse(
                    "the review-gate check loaded in degraded mode, so its decision cannot be used"
                )
            if hook._GATE_FILE_NAME != GATE_FILE_NAME:
                return _refuse(
                    f"the review-gate check's gate file is {hook._GATE_FILE_NAME} "
                    f"(from the PR hook), not {GATE_FILE_NAME}, so the check and "
                    "the removal would use different files"
                )
            gate_hash = review_gate_hash.branch_diff_gate_hash(trunk_ref, cwd=lane_path)
            if gate_hash == review_gate_hash.EMPTY_DIGEST:
                return _refuse(
                    f"the lane has no diff against trunk {trunk_ref} to review "
                    "(or git could not compute it)"
                )
            verdict = hook._evaluate_gate(
                _gate_file(lane_path),
                gate_hash,
                str(lane_path),
                _changed_files(lane_path, trunk_ref),
            )
            if verdict.passed:
                return None
            return _refuse(_gate_rejection_why(verdict.matched_rule))
    except lane_core.RefusalError as failure:
        # A git failure keeps its own block, so `check_lane` stops on it.
        return failure.refusal
    except Exception as failure:  # noqa: BLE001 - fail closed: nothing here may escape
        return _refuse(
            f"the review gate could not be evaluated ({type(failure).__name__}: {failure})"
        )


def _check_review_gate(ctx: CheckContext) -> lane_core.Refusal | None:
    lane = ctx.entered.context
    return _review_gate_refusal(lane.lane_path, lane.trunk_ref)


def _check_trunk_has_not_moved(ctx: CheckContext) -> lane_core.Refusal | None:
    """Guards the trunk ref only; the local trunk branch is check 5's concern."""
    entered = ctx.entered
    if entered.trunk_commit == ctx.expected_trunk:
        return None
    return lane_core.trunk_moved_refusal(
        entered.context.trunk_ref, ctx.expected_trunk, entered.trunk_commit
    )


def _trunk_target(
    context: lane_core.LaneContext,
) -> tuple[str, str] | lane_core.Refusal:
    """`(trunk branch, its tip commit)`, or the refusal saying it does not exist.

    The one lookup of the branch `integrate` fast-forwards: check 5 and the
    plan both ask it, so the two cannot disagree about what is missing.
    """
    trunk_branch = context.trunk_branch
    if trunk_branch is None:
        return lane_core.trunk_branch_missing_refusal(context.trunk_ref, None)
    trunk_tip = lane_core.branch_commit(trunk_branch, context.lane_path)
    if trunk_tip is None:
        return lane_core.trunk_branch_missing_refusal(context.trunk_ref, trunk_branch)
    return trunk_branch, trunk_tip


def _trunk_worktree(trunk_branch: str, lane_path: Path) -> Path | lane_core.Refusal:
    """The worktree that has the trunk branch checked out, or the refusal."""
    trunk_worktree = lane_core.branch_worktree(trunk_branch, lane_path)
    if trunk_worktree is None:
        return lane_core.trunk_checked_out_nowhere_refusal(trunk_branch)
    return trunk_worktree


def _trunk_fast_forwards_to(trunk_tip: str, commit: str, cwd: Path) -> bool:
    """True when the trunk branch at `trunk_tip` can be fast-forwarded to `commit`.

    The one predicate for check 5 and for the apply's divergence test. A git
    failure raises; it is not "no".
    """
    return lane_core.is_ancestor_strict(trunk_tip, commit, cwd)


def _check_trunk_fast_forwards(ctx: CheckContext) -> lane_core.Refusal | None:
    """The local trunk branch can be fast-forwarded to the lane, else why not.

    One refusal per run, the first sub-condition that fails, in the order a
    person fixes them: the branch exists, the lane contains it, a worktree has
    it, and that worktree is clean (no changes, no unfinished merge). A git
    failure while asking is not a sub-condition: the readers raise it and the
    engine reports it as this check's `git command failed` block.
    """
    lane = ctx.entered.context
    lane_path = lane.lane_path
    target = _trunk_target(lane)
    if isinstance(target, lane_core.Refusal):
        return target
    trunk_branch, trunk_tip = target
    if not _trunk_fast_forwards_to(trunk_tip, ctx.head, lane_path):
        return lane_core.trunk_not_an_ancestor_refusal(trunk_branch, lane.trunk_ref)
    trunk_worktree = _trunk_worktree(trunk_branch, lane_path)
    if isinstance(trunk_worktree, lane_core.Refusal):
        return trunk_worktree
    dirty_paths, merge_in_progress = lane_core.worktree_state(trunk_worktree)
    if dirty_paths or merge_in_progress:
        return lane_core.trunk_worktree_dirty_refusal(
            trunk_branch,
            trunk_worktree,
            dirty_paths,
            merge_in_progress=merge_in_progress,
        )
    return None


def _check_not_a_pr_repository(ctx: CheckContext) -> lane_core.Refusal | None:
    """A GitHub origin lands work through a PR, unless `--local-trunk` was given.

    `--local-trunk` settles it, so the origin is not even read. Otherwise the
    one origin lookup (`_is_pr_repository`) raises when git cannot answer, and
    the engine reports that: a failed lookup never reads as "not GitHub".
    """
    if ctx.allow_local_integration or not _is_pr_repository(
        ctx.entered.context.lane_path
    ):
        return None
    return lane_core.pr_repository_refusal()


def _check_lane_is_clean(ctx: CheckContext) -> lane_core.Refusal | None:
    return _dirty_refusal(ctx.entered.context.lane_path)


#: The integrate checks, in the order their blocks are printed. `order` is the
#: slot number from the plan (1 tree, 2 review gate, 3 trunk moved, 4 lane
#: clean, 5 trunk fast-forward, 6 PR repository).
#:
#: A check that hits a git failure: `_run_check` turns the
#: `RefusalError` it raises into that check's refusal (the `git command
#: failed` block), and `check_lane` stops there. A check does not catch git
#: errors, and its readers must raise on one instead of answering "no" (a
#: yes/no question git fails to answer is not a "no"), so a broken git call
#: becomes a block and never reads as a finding.
CHECKS: tuple[Check, ...] = (
    Check(1, "tree matches", _check_tree_matches),
    Check(2, "review gate holds", _check_review_gate),
    Check(3, "trunk has not moved", _check_trunk_has_not_moved),
    Check(4, "lane is clean", _check_lane_is_clean),
    Check(5, "trunk can fast-forward", _check_trunk_fast_forwards),
    Check(6, "not a PR repository", _check_not_a_pr_repository),
)


def _run_check(check: Check, ctx: CheckContext) -> lane_core.Refusal | None:
    try:
        return check.run(ctx)
    except lane_core.RefusalError as failure:
        return failure.refusal


@dataclass(frozen=True)
class CheckedLane:
    """The outcome of the checks: `check_context` is what the apply is bound to
    (None after an early stop), `refusals` the blocks to print."""

    check_context: CheckContext | None
    refusals: list[lane_core.Refusal]


def check_lane(
    trunk_arg: str | None,
    expected_trunk: str,
    expected_tree: str,
    cwd: Path,
    allow_local_integration: bool = False,
) -> CheckedLane:
    """Enter the lane once, read its HEAD once, and run the checks. Changes nothing.

    Not a git work tree, an unresolvable trunk and not being in a lane are the
    early stops: every check needs all three, so they are a single block. Past
    them every check runs, whatever an earlier one found, except after a `git
    command failed` block: git itself is failing or stalled (each lane git call
    waits up to `GIT_TIMEOUT_SECONDS`; the delegated gate calls carry no
    timeout, see the module docstring), so the checks stop there and report the
    blocks collected so far. The blocks of the checks that did not run are not
    printed: a missing block after a `git command failed` block is not a pass.
    """
    try:
        entered = _enter_lane(trunk_arg, cwd)
        head = lane_core.head_commit(entered.context.lane_path)
    except lane_core.RefusalError as stop:
        return CheckedLane(None, [stop.refusal])
    ctx = CheckContext(
        entered, head, expected_trunk, expected_tree, allow_local_integration
    )
    refusals: list[lane_core.Refusal] = []
    for check in CHECKS:
        refusal = _run_check(check, ctx)
        if refusal is None:
            continue
        refusals.append(refusal)
        if refusal.what == lane_core.WHAT_GIT_COMMAND_FAILED:
            break
    return CheckedLane(ctx, refusals)


def emit_integrate_refusals(refusals: Sequence[lane_core.Refusal]) -> int:
    """Print the blocks, then the closing `note:` when a PR-repository refusal
    comes with others. Returns the exit code (1)."""
    code = lane_core.emit_refusals(refusals)
    pr_repository = any(r.what == lane_core.WHAT_PR_REPOSITORY for r in refusals)
    if pr_repository and len(refusals) > 1:
        sys.stderr.write(f"\nnote: {lane_core.PR_REPOSITORY_NOTE}\n")
    return code


# --- integrate: apply ---------------------------------------------------------


def _configure_integrate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        EXPECTED_TRUNK_FLAG, required=True, help="expected-trunk as compose printed it"
    )
    parser.add_argument(
        EXPECTED_TREE_FLAG, required=True, help="expected-tree as compose printed it"
    )
    _add_trunk_argument(parser)
    parser.add_argument(
        "--local-trunk",
        dest="allow_local_integration",
        action="store_true",
        help="integrate locally even when origin is on GitHub (a PR repository)",
    )


def _invalid_identities(args: argparse.Namespace) -> list[tuple[str, str]]:
    """The `(flag, value)` pairs that are not 40 lowercase hex."""
    given = (
        (EXPECTED_TRUNK_FLAG, args.expected_trunk),
        (EXPECTED_TREE_FLAG, args.expected_tree),
    )
    return [
        (flag, value)
        for flag, value in given
        if IDENTITY_PATTERN.fullmatch(value) is None
    ]


@dataclass(frozen=True)
class IntegratePlan:
    """What the apply steps act on, all read before the first one runs."""

    lane_path: Path
    lane_branch: str
    trunk_ref: str
    trunk_branch: str
    trunk_worktree: Path
    former_head: str
    gate_file: Path


_Found = TypeVar("_Found")


def _require(found: _Found | lane_core.Refusal) -> _Found:
    """`found`, or a `RefusalError` when it is a refusal.

    Turns the lookups the checks share (`_trunk_target`, `_trunk_worktree`)
    into raising calls for the plan, which must stop at the first refusal.
    """
    if isinstance(found, lane_core.Refusal):
        raise lane_core.RefusalError(found)
    return found


def _lane_moved_refusal(ctx: CheckContext, live_head: str) -> lane_core.Refusal:
    """Why a lane whose HEAD moved since the checks is refused.

    A new commit with another tree is a tree mismatch. A new commit with the
    reviewed tree is not, and saying "the tree is not the reviewed tree" for
    two equal trees would contradict itself: it says the commit moved.
    """
    context = ctx.entered.context
    live_tree = lane_core.commit_tree(live_head, context.lane_path)
    if live_tree != ctx.expected_tree:
        return lane_core.tree_mismatch_refusal(
            ctx.expected_tree, live_tree, context.trunk_ref
        )
    return lane_core.lane_head_moved_refusal(ctx.head, live_head, context.trunk_ref)


def _revalidate(ctx: CheckContext) -> None:
    """Read again what the checks read, and refuse when it changed since.

    Two facts: the trunk ref (resolved again, not taken from the checks'
    copy) and the lane's HEAD. The apply is bound to `ctx.head`, the commit
    whose tree check 1 compared, so a lane that moved is refused instead of
    fast-forwarded to a commit nobody reviewed. (A SHA names one tree for
    good, so the tree of `ctx.head` needs no second read.)
    """
    entered = ctx.entered
    context = entered.context
    lane_path = context.lane_path
    _, live_trunk = lane_core.resolve_trunk_commit(entered.trunk_arg, lane_path)
    if live_trunk != ctx.expected_trunk:
        raise lane_core.RefusalError(
            lane_core.trunk_moved_refusal(
                context.trunk_ref, ctx.expected_trunk, live_trunk
            )
        )
    live_head = lane_core.head_commit(lane_path)
    if live_head != ctx.head:
        raise lane_core.RefusalError(_lane_moved_refusal(ctx, live_head))


def _plan_integrate(ctx: CheckContext) -> IntegratePlan:
    """Read everything the apply steps need, while the lane still exists.

    Revalidated first (`_revalidate`). The checks passed, so the trunk branch
    and its worktree exist; a refusal here means that changed since they ran.

    The window between this recheck and the apply is narrower, not closed. A
    commit added to the lane after it still lets the fast-forward (which
    targets `former_head`, never the new commit) and the worktree removal
    succeed; the last step then fails on its old-value guard and is reported
    as a partial state, with the new commit kept on the lane branch.
    """
    _revalidate(ctx)
    context = ctx.entered.context
    lane_path = context.lane_path
    trunk_branch, _ = _require(_trunk_target(context))
    trunk_worktree = _require(_trunk_worktree(trunk_branch, lane_path))
    return IntegratePlan(
        lane_path=lane_path,
        lane_branch=context.branch,
        trunk_ref=context.trunk_ref,
        trunk_branch=trunk_branch,
        trunk_worktree=trunk_worktree,
        former_head=ctx.head,
        gate_file=_gate_file(lane_path),
    )


# The apply steps. Each is one named unit, run in this order by `_apply`, and
# each git call takes `plan.trunk_worktree` as its cwd: the process may be
# running inside the lane that the third step removes, and the process cwd is
# never changed. A step that cannot finish raises `StepFailed`.


class StepFailed(Exception):
    """An apply step could not finish; the message is why.

    With a `not_repeatable` reason (a `lane_core.NOT_REPEATABLE_*` constant),
    running the step (or any later one) by hand is unsafe: the failure block
    carries that reason's text instead of a command list.
    """

    def __init__(self, message: str, not_repeatable: str | None = None) -> None:
        super().__init__(message)
        self.not_repeatable = not_repeatable


class StepRefused(Exception):
    """The first step found, before changing anything, that the checks no longer
    hold. It is reported as a plain refusal: nothing is done, nothing remains."""

    def __init__(self, refusal: lane_core.Refusal) -> None:
        super().__init__(refusal.what)
        self.refusal = refusal


def _fast_forward_args(plan: IntegratePlan) -> list[str]:
    return [*FAST_FORWARD_ARGS, plan.former_head]


def _worktree_removal_args(plan: IntegratePlan) -> list[str]:
    return ["worktree", "remove", str(plan.lane_path)]


def _branch_deletion_args(plan: IntegratePlan) -> list[str]:
    return ["update-ref", "-d", lane_core.local_ref(plan.lane_branch), plan.former_head]


def _guarded_branch_deletion_command(plan: IntegratePlan) -> str:
    """The branch deletion as a person types it: the containment check, then the delete.

    `_delete_branch` refuses unless the trunk branch contains the lane's former
    HEAD. A bare `update-ref -d` printed in `remaining:` would skip that check,
    so the printed command carries it. The `&&` is text for a shell; lane never
    runs this string.
    """
    contained = _trunk_git_command(
        ["merge-base", "--is-ancestor", plan.former_head, _trunk_branch_ref(plan)],
        plan,
    )
    return f"{contained} && {_trunk_git_command(_branch_deletion_args(plan), plan)}"


def _recover_command(plan: IntegratePlan) -> str:
    """Brings the lane branch back at its former HEAD: what `recover:` shows."""
    return shlex.join(["git", "branch", plan.lane_branch, plan.former_head])


def _gate_removal_command(plan: IntegratePlan) -> str:
    return shlex.join(["rm", "--", str(plan.gate_file)])


def _run_step_git(args: Sequence[str], plan: IntegratePlan) -> None:
    attempt = lane_core.git_attempt(args, plan.trunk_worktree)
    if not attempt.ok:
        raise StepFailed(attempt.detail)


def _trunk_branch_ref(plan: IntegratePlan) -> str:
    return lane_core.local_ref(plan.trunk_branch)


def _trunk_tip_diverged(plan: IntegratePlan) -> bool:
    """True when the trunk branch has a commit the lane's HEAD lacks: trunk
    moved on, so a fast-forward can never succeed. False when it cannot be told."""
    try:
        tip = lane_core.branch_commit(plan.trunk_branch, plan.trunk_worktree)
        return tip is not None and not _trunk_fast_forwards_to(
            tip, plan.former_head, plan.trunk_worktree
        )
    except lane_core.RefusalError:
        return False


def _require_trunk_worktree_on_the_branch(plan: IntegratePlan) -> None:
    """Refuse (nothing is changed yet) when the trunk worktree switched branch."""
    on = lane_core.git_attempt(["symbolic-ref", "-q", "HEAD"], plan.trunk_worktree)
    if not on.ok or on.stdout != _trunk_branch_ref(plan):
        raise StepRefused(
            lane_core.trunk_worktree_switched_refusal(
                plan.trunk_branch, plan.trunk_worktree
            )
        )


def _fast_forward(plan: IntegratePlan) -> None:
    """Move the trunk branch to the lane's HEAD.

    Bound to the trunk branch in three ways: the trunk worktree must still
    have the branch checked out (else `git merge` would move whatever branch it
    holds now), a failure because trunk moved on is a refusal (compose again),
    and afterwards the branch is read back and must be at `former_head`.
    `--ff-only` leaves the branch at exactly the commit it was given, so the
    read-back can only differ when the worktree changed branch in the instant
    between the first check and the merge; that window is the residual one, and
    it is reported, not prevented.
    """
    _require_trunk_worktree_on_the_branch(plan)
    attempt = lane_core.git_attempt(_fast_forward_args(plan), plan.trunk_worktree)
    if not attempt.ok:
        if _trunk_tip_diverged(plan):
            raise StepRefused(
                lane_core.trunk_not_an_ancestor_refusal(
                    plan.trunk_branch, plan.trunk_ref
                )
            )
        raise StepFailed(attempt.detail)
    try:
        tip = lane_core.branch_commit(plan.trunk_branch, plan.trunk_worktree)
    except lane_core.RefusalError as unreadable:
        raise StepFailed(
            f"the new tip of {plan.trunk_branch} could not be read: "
            f"{unreadable.refusal.why}",
            lane_core.NOT_REPEATABLE_TRUNK_NOT_AT_LANE_HEAD,
        ) from unreadable
    if tip != plan.former_head:
        raise StepFailed(
            f"the merge ran but {plan.trunk_branch} is at {tip}, not at "
            f"{plan.former_head}",
            lane_core.NOT_REPEATABLE_TRUNK_NOT_AT_LANE_HEAD,
        )


def _gate_file_in_lane(plan: IntegratePlan) -> bool:
    """True when the gate path lives inside the lane. May raise OSError or, for
    a symlink loop, RuntimeError."""
    return plan.gate_file.parent.resolve().is_relative_to(plan.lane_path.resolve())


def _gate_file_is_the_lanes(plan: IntegratePlan) -> bool:
    """`_gate_file_in_lane`, where a path that cannot be resolved is not the lane's."""
    try:
        return _gate_file_in_lane(plan)
    except (OSError, RuntimeError):
        return False


def _remove_gate_file(plan: IntegratePlan) -> None:
    """Remove the gate file, but only a file that lives inside the lane.

    The gate path is read through whatever `.claude/memory` is. When that is a
    symlink out of the lane, the file belongs to someone else and stays; the
    lane's removal does not touch it either.

    Accepted: the containment check and the unlink are two calls, so a writer
    that swaps `.claude/memory` for a symlink between them, inside a lane that
    is being removed, could point the unlink elsewhere.
    """
    try:
        if not _gate_file_in_lane(plan):
            return
        plan.gate_file.unlink(missing_ok=True)
    except (OSError, RuntimeError) as failure:
        raise StepFailed(str(failure)) from failure


def _remove_worktree(plan: IntegratePlan) -> None:
    """Without `--force`: git refuses a worktree that is not clean."""
    _run_step_git(_worktree_removal_args(plan), plan)


def _delete_branch(plan: IntegratePlan) -> None:
    """Delete the lane branch when the trunk contains it and it is still where we left it.

    Not `git branch -d`: that checks the branch's upstream, not HEAD, and fails
    for a lane that was pushed with `-u`. The ancestry check (strict, so a git
    failure is a failure and not "not merged") stands in for it, and
    `update-ref -d` takes the lane's former HEAD as the old value, so a branch
    that moved since the plan is not deleted. The ancestry is read from the
    trunk branch itself, not from whatever the trunk worktree has checked out.

    `update-ref -d` removes only the ref: the `branch.<lane>.*` config that
    `git push -u` wrote stays (this tool never writes git config).
    """
    trunk_tip = lane_core.branch_commit(plan.trunk_branch, plan.trunk_worktree)
    if trunk_tip is None or not lane_core.is_ancestor_strict(
        plan.former_head, trunk_tip, plan.trunk_worktree
    ):
        raise StepFailed(
            f"the lane's former HEAD {plan.former_head} is not contained in "
            f"{plan.trunk_branch}",
            lane_core.NOT_REPEATABLE_BRANCH_KEPT,
        )
    _run_step_git(_branch_deletion_args(plan), plan)


def _trunk_git_command(args: Sequence[str], plan: IntegratePlan) -> str:
    """`args` as a person types it from any directory: `git -C <trunk worktree> ...`."""
    return shlex.join(["git", "-C", str(plan.trunk_worktree), *args])


@dataclass(frozen=True)
class ApplyStep:
    """One apply step: its name for `done:`, the command a person would type for
    `remaining:`, and what runs.

    `applies` is False when the step does nothing for this plan (the gate file
    is not the lane's): it is then neither `done:` nor `remaining:`, so no
    command is printed that the step itself would refuse to run. It is decided
    once, in `_apply_steps` before the first step runs: the worktree removal
    can change the answer (a `.claude/memory` symlink goes with the worktree),
    and `done:` must not name a step that never did anything.
    """

    name: str
    command: str
    run: Callable[[IntegratePlan], None]
    applies: bool = True


def _apply_steps(plan: IntegratePlan) -> list[ApplyStep]:
    """The apply sequence, in the order it runs. Looked up when called, so each
    step is the module's current function."""
    return [
        ApplyStep(
            lane_core.STEP_FAST_FORWARD,
            _trunk_git_command(_fast_forward_args(plan), plan),
            _fast_forward,
        ),
        ApplyStep(
            lane_core.STEP_GATE_FILE_REMOVAL,
            _gate_removal_command(plan),
            _remove_gate_file,
            applies=_gate_file_is_the_lanes(plan),
        ),
        ApplyStep(
            lane_core.STEP_WORKTREE_REMOVAL,
            _trunk_git_command(_worktree_removal_args(plan), plan),
            _remove_worktree,
        ),
        ApplyStep(
            lane_core.STEP_BRANCH_DELETION,
            _guarded_branch_deletion_command(plan),
            _delete_branch,
        ),
    ]


class ApplyFailed(Exception):
    """A step failed after the checks passed. `done` are the names of the steps
    that finished; `remaining` are the commands of the failed step and every
    step after it; `recover` is the command that restores the lane branch at
    its former HEAD, printed whatever failed so that commit is never reachable
    only from scrollback. `interruption` is the `KeyboardInterrupt` (or other
    non-`Exception`) to raise again once the report is printed."""

    def __init__(
        self,
        refusal: lane_core.Refusal,
        done: list[str],
        remaining: list[str],
        recover: str,
        interruption: BaseException | None = None,
    ) -> None:
        super().__init__(refusal.what)
        self.refusal = refusal
        self.done = done
        self.remaining = remaining
        self.recover = recover
        self.interruption = interruption


def _failure_detail(failure: BaseException) -> str:
    """Why a step failed: its own message, the refusal a git read raised, or the
    unexpected exception's type and message."""
    if isinstance(failure, lane_core.RefusalError):
        return failure.refusal.why
    if isinstance(failure, StepFailed):
        return str(failure)
    return f"{type(failure).__name__}: {failure}"


def _not_repeatable_reason(failure: BaseException) -> str | None:
    """Why a failed step declined to be run by hand, or None when it can be.

    The single rule behind both the refusal block and the `remaining:` lines.
    """
    return failure.not_repeatable if isinstance(failure, StepFailed) else None


def _failure_refusal(step: ApplyStep, failure: BaseException) -> lane_core.Refusal:
    detail = _failure_detail(failure)
    reason = _not_repeatable_reason(failure)
    if reason is not None:
        return lane_core.integrate_step_not_repeatable_refusal(
            step.name, detail, reason
        )
    return lane_core.integrate_step_failed_refusal(step.name, step.command, detail)


def _apply_failed(
    plan: IntegratePlan, steps: Sequence[ApplyStep], index: int, failure: BaseException
) -> ApplyFailed:
    """What is done and what remains after `steps[index]` failed with `failure`.

    A step that declined for its own safety (`not_repeatable`) leaves
    nothing to run by hand: its command, and the steps after it, would do what
    it refused to do.
    """
    repeatable = _not_repeatable_reason(failure) is None
    return ApplyFailed(
        _failure_refusal(steps[index], failure),
        done=[step.name for step in steps[:index] if step.applies],
        remaining=(
            [step.command for step in steps[index:] if step.applies]
            if repeatable
            else []
        ),
        recover=_recover_command(plan),
        interruption=None if isinstance(failure, Exception) else failure,
    )


def _apply(plan: IntegratePlan) -> None:
    """Run the apply steps in order. The first failure stops the sequence (nothing
    is retried) and raises `ApplyFailed` naming what is done and what remains.

    Any exception ends the sequence the same way, `KeyboardInterrupt` included
    (carried on `ApplyFailed.interruption`): the report is the only record of a
    half-done apply. `StepRefused` is the exception: only the first step raises
    it, before anything changed, so there is nothing to report.
    """
    steps = _apply_steps(plan)
    for index, step in enumerate(steps):
        try:
            step.run(plan)
        except StepRefused as refused:
            raise lane_core.RefusalError(refused.refusal) from refused
        except BaseException as failure:
            raise _apply_failed(plan, steps, index, failure) from failure


def _emit_apply_failure(failed: ApplyFailed) -> int:
    """The failure block, then what is done and what remains. Returns exit 1."""
    code = lane_core.emit_refusals([failed.refusal])
    done = failed.done or [NO_STEP_DONE]
    lines = [f"{KEY_DONE}: {name}" for name in done]
    lines += [f"{KEY_REMAINING}: {command}" for command in failed.remaining]
    lines.append(f"{KEY_RECOVER}: {failed.recover}")
    shown = "\n".join(lane_core.display_text(line) for line in lines)
    sys.stderr.write(f"\n{shown}\n")
    return code


def _print_integrated(plan: IntegratePlan) -> None:
    """The success lines. Branch names and paths come from git and the file
    system: each line is shown through `display_text`, so a control character
    in one cannot forge a line or rewrite the terminal. `now-at` is
    `former-head`: the fast-forward moved the trunk branch to exactly it."""
    lines = (
        f"{KEY_TRUNK}: {plan.trunk_branch}",
        f"{KEY_FORMER_HEAD}: {plan.former_head}",
        f"{KEY_NOW_AT}: {plan.former_head}",
        f"{KEY_CONTINUE_IN}: {plan.trunk_worktree}",
        f"{KEY_RECOVER}: {_recover_command(plan)}",
        PUSHED_NOTHING_LINE,
    )
    _print_displayed(lines)


def cmd_integrate(args: argparse.Namespace, cwd: Path) -> int:
    """Fast-forward the local trunk branch to the lane, then remove the lane.

    The checks run first and change nothing (a git command that fails stops the
    remaining checks); the apply steps run only when none refuses. The apply is bound to the lane HEAD and trunk commit the
    checks saw.

    Removing the lane worktree also deletes the ignored files inside it
    (`.claude/` and anything else the repository ignores): `git worktree
    remove` refuses only tracked changes and untracked files, not ignored ones.
    """
    invalid = _invalid_identities(args)
    if invalid:
        raise lane_core.RefusalError(
            lane_core.invalid_identity_argument_refusal(invalid)
        )
    checked = check_lane(
        args.trunk,
        args.expected_trunk,
        args.expected_tree,
        cwd,
        args.allow_local_integration,
    )
    if checked.refusals:
        return emit_integrate_refusals(checked.refusals)
    plan = _plan_integrate(checked.check_context)
    try:
        _apply(plan)
    except ApplyFailed as failed:
        code = _emit_apply_failure(failed)
        if failed.interruption is not None:
            raise failed.interruption
        return code
    _print_integrated(plan)
    return lane_core.EXIT_OK


#: Every registered command, keyed by its own `name`.
COMMANDS: dict[str, Command] = {
    command.name: command
    for command in (
        Command(
            name=OPEN_COMMAND,
            help="create a lane: a linked worktree and branch at the trunk tip",
            configure=_configure_open,
            handler=cmd_open,
        ),
        Command(
            name=COMPOSE_COMMAND,
            help="merge trunk into the lane and print the identities to review",
            configure=_configure_compose,
            handler=cmd_compose,
        ),
        Command(
            name=INTEGRATE_COMMAND,
            help="fast-forward the local trunk to the lane when every identity holds",
            configure=_configure_integrate,
            handler=cmd_integrate,
        ),
    )
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lane.py", description="Identity-checked lanes: open, compose, integrate."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )
    for command in COMMANDS.values():
        command.configure(subparsers.add_parser(command.name, help=command.help))
    return parser


def _parse(argv: Sequence[str] | None) -> argparse.Namespace | int:
    """The parsed arguments, or the exit code argparse chose (0 for --help)."""
    try:
        return build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else lane_core.EXIT_USAGE


def main(argv: Sequence[str] | None = None, cwd: Path | str | None = None) -> int:
    """In-process entry point. Returns the exit code; never raises SystemExit."""
    args = _parse(argv)
    if isinstance(args, int):
        return args
    # Resolved once: --path and every existence check then share one base.
    base = Path.cwd() if cwd is None else Path(cwd)
    try:
        return COMMANDS[args.command].handler(args, base.resolve())
    except lane_core.RefusalError as exc:
        return lane_core.emit_refusals([exc.refusal])


if __name__ == "__main__":
    sys.exit(main())
