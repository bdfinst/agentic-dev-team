#!/usr/bin/env python3
"""lane.py -- identity-checked lanes: open, compose, integrate.

`open` and `compose` are registered so far. Usage errors exit 2, refusals exit 1
(blocks on stderr), success 0.

Import whitelist (pinned by an AST test): the standard library, `lane_core`,
`git_origin_host` and, from the plugin's `hooks/lib`, `artifact_paths`,
`git_safe_diff` and `review_gate_hash`. The PR hook `hooks/pre_pr_review.py`
is loaded by path inside `_gate_verdict`, never imported. Stdlib only
otherwise. See ADR 0014 and ADR 0031.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _SCRIPTS_DIR.parent / "hooks"
for _import_dir in (_HOOKS_DIR / "lib", _SCRIPTS_DIR):
    if str(_import_dir) not in sys.path:
        sys.path.insert(0, str(_import_dir))

import artifact_paths
import git_origin_host
import git_safe_diff
import lane_core
import review_gate_hash

#: Between the primary checkout's name and the lane name in a default path.
LANE_DIR_INFIX = "-lane-"

NAME_PATTERN_PROBLEM = (
    "it must start with a letter or digit and use only safe characters"
)
NAME_GIT_PROBLEM = "git does not accept it as a branch name"

#: Fast-forward when possible whatever `merge.ff` says, else a merge commit.
#: A tracked file that would arrive over an ignored local file is refused, not
#: written over (`--no-overwrite-ignore`; git's default overwrites it silently).
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
    print(f"worktree: {path}")
    print(f"branch: {name}")
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
    dirty = lane_core.dirty_paths(lane_path)
    unfinished = lane_core.merge_in_progress(lane_path)
    if not dirty and not unfinished:
        return None
    if unfinished:
        return lane_core.unfinished_merge_refusal(dirty)
    return lane_core.lane_has_uncommitted_changes_refusal(dirty)


def _require_clean(lane_path: Path) -> None:
    refusal = _dirty_refusal(lane_path)
    if refusal is not None:
        raise lane_core.RefusalError(refusal)


def _is_pr_repository(lane_path: Path) -> bool:
    """True when the `origin` remote is on GitHub: work lands through a PR."""
    host = git_origin_host.classify(lane_core.origin_url(lane_path))
    return host == ORIGIN_HOST_GITHUB


# --- compose ----------------------------------------------------------------


def _configure_compose(parser: argparse.ArgumentParser) -> None:
    _add_trunk_argument(parser)


def _integrate_command(entered: EnteredLane, tree: str) -> str:
    """The `integrate` line a reviewer runs next; `--trunk` only when it was given."""
    command = (
        f"lane.py integrate --expected-trunk {entered.trunk_commit} "
        f"--expected-tree {tree}"
    )
    if entered.trunk_arg is None:
        return command
    return f"{command} --trunk {entered.trunk_arg}"


def _next_step(entered: EnteredLane, tree: str) -> str:
    """`integrate` for a local-trunk lane; `/pr` in a PR repository."""
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
    trunk_branch_commit = lane_core.branch_commit(context.trunk_branch, lane_path)
    if trunk_branch_commit is None:
        return [trunk_ref_target]
    trunk_branch_target = MergeTarget(context.trunk_branch, trunk_branch_commit)
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
    to stay true if either of those readers changes.
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
        return (
            _snapshot(lane_path) == snapshot
            and not lane_core.has_unmerged_entries(lane_path)
            and not lane_core.merge_in_progress(lane_path)
            and not lane_core.dirty_paths(lane_path)
        )
    except lane_core.RefusalError:
        return False


def _settled(
    snapshot: Snapshot,
    lane_path: Path,
    failed_step: str,
    cause: str,
    restored: lane_core.Refusal,
) -> lane_core.Refusal:
    """`restored` once the restore is verified, else the unverified refusal.

    The one place that states the rule: a refusal claims the lane was restored
    only after a verified restore.
    """
    if _restore_verified(snapshot, lane_path):
        return restored
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
    restored = (
        lane_core.compose_conflict_refusal(target.ref, unmerged)
        if unmerged
        else lane_core.compose_merge_failed_refusal(target.ref, attempt.command, detail)
    )
    return _settled(
        snapshot, lane_path, lane_core.merge_step_failed(target.ref), cause, restored
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
        f"it would overwrite ignored local files: {lane_core.listed_paths(in_the_way)}"
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
        step = lane_core.compose_failed_after([target.ref for target in merged])
        raise SettledRefusal(
            _settled(
                snapshot,
                lane_path,
                step,
                failure.refusal.why,
                lane_core.compose_restored_refusal(failure.refusal),
            )
        ) from failure
    except BaseException:
        _restore_verified(snapshot, lane_path)
        raise


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
    print(f"lane: {entered.context.branch}")
    print(f"trunk: {entered.context.trunk_ref}")
    print(f"expected-trunk: {entered.trunk_commit}")
    print(f"expected-tree: {tree}")
    print(f"next: {next_step}")
    return lane_core.EXIT_OK


# --- integrate: the check engine ----------------------------------------------


@dataclass(frozen=True)
class CheckContext:
    """What every integrate check reads: the lane entered, and the identities
    the reviewer holds (`expected-trunk`, `expected-tree` as `compose` printed them)."""

    entered: EnteredLane
    expected_trunk: str
    expected_tree: str


@dataclass(frozen=True)
class Check:
    """One integrate check. `run` returns its refusal, or None when it holds."""

    order: int
    name: str
    run: Callable[[CheckContext], lane_core.Refusal | None]


def _check_tree_matches(ctx: CheckContext) -> lane_core.Refusal | None:
    context = ctx.entered.context
    live = lane_core.head_tree(context.lane_path)
    if live == ctx.expected_tree:
        return None
    return lane_core.tree_mismatch_refusal(ctx.expected_tree, live, context.trunk_ref)


def _load_pr_hook():
    """The PR hook module, executed from its file. Nothing is registered in `sys.modules`."""
    spec = importlib.util.spec_from_file_location(PR_HOOK_MODULE, PR_HOOK_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {PR_HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
GATE_RULE_UNKNOWN = "the PR review gate rejected this lane"


def _gate_rejection_why(matched_rule: str) -> str:
    wording = GATE_RULE_WORDING.get(matched_rule, GATE_RULE_UNKNOWN)
    return f"{wording} (rule: {matched_rule or 'none given'})"


def _changed_files(lane_path: Path, trunk_ref: str) -> list[str]:
    """The paths of the lane's diff against trunk; raises when git cannot say."""
    completed = git_safe_diff.run_safe_git_diff(
        ["--name-only"],
        cwd=lane_path,
        text=True,
        target=f"{trunk_ref}...HEAD",
        timeout=lane_core.GIT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise OSError(f"git diff exited {completed.returncode}")
    return [line for line in completed.stdout.splitlines() if line]


def _gate_verdict(lane_path: Path, trunk_ref: str) -> lane_core.Refusal | None:
    """The refusal when the PR review gate would reject this lane, else None.

    The same decision as `pre_pr_review`'s `main()` for the lane's diff against
    `trunk_ref`: `_evaluate_gate` is the hook's own, loaded by path. This is the
    one function that touches the hook's private names (`_evaluate_gate`,
    `_GATE_FILE_NAME`); a rename there fails the parity tests, not a release.

    Fail closed: an unloadable or degraded hook, a diff that cannot be read, an
    empty diff, and any exception are all this one refusal, never a traceback.
    Reading only: the gate path is resolved with `migrate=False` and nothing is
    unlinked (the hook's `main()` does that on success; `integrate` does it at
    apply time). `PR_GATE_BYPASS_REASON` lives in the hook's `main()`, which is
    never called, so it has no effect here.

    The delegated code (hash, hook, `project_root`) starts its own git
    processes, so the whole evaluation runs under the filtered git environment
    (an exported `GIT_DIR` cannot redirect it), and the one call that takes a
    timeout gets `GIT_TIMEOUT_SECONDS`.
    """

    def refusal(why: str) -> lane_core.Refusal:
        return lane_core.review_gate_refusal(trunk_ref, why)

    try:
        with lane_core.filtered_process_environment():
            hook = _load_pr_hook()
            if hook.branch_diff_gate_hash is not review_gate_hash.branch_diff_gate_hash:
                return refusal(
                    "the PR hook loaded in degraded mode, so its decision cannot be used"
                )
            gate_hash = review_gate_hash.branch_diff_gate_hash(trunk_ref, cwd=lane_path)
            if gate_hash == review_gate_hash.EMPTY_DIGEST:
                return refusal(
                    f"the lane has no diff against trunk {trunk_ref} to review "
                    "(or git could not compute it)"
                )
            gate_file = artifact_paths.resolve_file(
                "memory", hook._GATE_FILE_NAME, lane_path, migrate=False
            )
            verdict = hook._evaluate_gate(
                gate_file,
                gate_hash,
                str(lane_path),
                _changed_files(lane_path, trunk_ref),
            )
            if verdict.passed:
                return None
            return refusal(_gate_rejection_why(verdict.matched_rule))
    except Exception as failure:  # noqa: BLE001 - fail closed: nothing here may escape
        return refusal(
            f"the review gate could not be evaluated ({type(failure).__name__}: {failure})"
        )


def _check_review_gate(ctx: CheckContext) -> lane_core.Refusal | None:
    context = ctx.entered.context
    return _gate_verdict(context.lane_path, context.trunk_ref)


def _check_trunk_has_not_moved(ctx: CheckContext) -> lane_core.Refusal | None:
    """Guards the trunk ref only; the local trunk branch is check 5's concern."""
    entered = ctx.entered
    if entered.trunk_commit == ctx.expected_trunk:
        return None
    return lane_core.trunk_moved_refusal(
        entered.context.trunk_ref, ctx.expected_trunk, entered.trunk_commit
    )


def _check_trunk_fast_forwards(ctx: CheckContext) -> lane_core.Refusal | None:
    """The local trunk branch can be fast-forwarded to the lane, else why not.

    One refusal per run, the first sub-condition that fails, in the order a
    person fixes them: the branch exists, the lane contains it, a worktree has
    it, and that worktree is clean (no changes, no unfinished merge). A git
    failure while asking is not a sub-condition: the readers raise it and the
    engine reports it as this check's `git command failed` block.
    """
    context = ctx.entered.context
    lane_path = context.lane_path
    branch = context.trunk_branch
    if branch is None:
        return lane_core.trunk_branch_missing_refusal(context.trunk_ref, None)
    branch_commit = lane_core.branch_commit(branch, lane_path)
    if branch_commit is None:
        return lane_core.trunk_branch_missing_refusal(context.trunk_ref, branch)
    if not lane_core.is_ancestor_strict(branch_commit, "HEAD", lane_path):
        return lane_core.trunk_not_an_ancestor_refusal(branch, context.trunk_ref)
    worktree = lane_core.branch_worktree(branch, lane_path)
    if worktree is None:
        return lane_core.trunk_checked_out_nowhere_refusal(branch)
    dirty = lane_core.dirty_paths(worktree)
    unfinished = lane_core.merge_in_progress(worktree)
    if dirty or unfinished:
        return lane_core.trunk_worktree_dirty_refusal(
            branch, worktree, dirty, merge_unfinished=unfinished
        )
    return None


def _check_lane_is_clean(ctx: CheckContext) -> lane_core.Refusal | None:
    return _dirty_refusal(ctx.entered.context.lane_path)


#: The integrate checks, in the order their blocks are printed. `order` is the
#: slot number from the plan; a gap is a check a later step registers, so that
#: step adds one entry and moves nothing:
#:   6 PR repository (Step 3.3).
#:
#: A check that hits a git failure: `collect_refusals` turns the
#: `RefusalError` it raises into that check's refusal (the `git command
#: failed` block) and runs the rest. A check does not catch git errors, and its
#: readers must raise on one instead of answering "no" (a yes/no question git
#: fails to answer is not a "no"), so one broken git call becomes a block and
#: cannot hide the other checks' findings.
CHECKS: tuple[Check, ...] = (
    Check(1, "tree matches", _check_tree_matches),
    Check(2, "review gate holds", _check_review_gate),
    Check(3, "trunk has not moved", _check_trunk_has_not_moved),
    Check(4, "lane is clean", _check_lane_is_clean),
    Check(5, "trunk can fast-forward", _check_trunk_fast_forwards),
)


def _run_check(check: Check, ctx: CheckContext) -> lane_core.Refusal | None:
    try:
        return check.run(ctx)
    except lane_core.RefusalError as failure:
        return failure.refusal


def collect_refusals(
    trunk_arg: str | None, expected_trunk: str, expected_tree: str, cwd: Path
) -> list[lane_core.Refusal]:
    """Every refusal `integrate` would print, in check order. Changes nothing.

    Not a git work tree, an unresolvable trunk and not being in a lane are the
    only early stops: every check needs all three, so they are a single block.
    Past them every check runs, whatever an earlier one found.
    """
    try:
        entered = _enter_lane(trunk_arg, cwd)
    except lane_core.RefusalError as stop:
        return [stop.refusal]
    ctx = CheckContext(entered, expected_trunk, expected_tree)
    outcomes = (_run_check(check, ctx) for check in CHECKS)
    return [refusal for refusal in outcomes if refusal is not None]


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
