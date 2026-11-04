#!/usr/bin/env python3
"""lane.py -- identity-checked lanes: open, compose, integrate.

`open` and `compose` are registered so far. Usage errors exit 2, refusals exit 1
(blocks on stderr), success 0.

Import whitelist (pinned by an AST test): the standard library and
`lane_core`. Stdlib only otherwise. See ADR 0014 and ADR 0031.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import git_origin_host
import lane_core

#: Between the primary checkout's name and the lane name in a default path.
LANE_DIR_INFIX = "-lane-"

NAME_PATTERN_PROBLEM = (
    "it must start with a letter or digit and use only safe characters"
)
NAME_GIT_PROBLEM = "git does not accept it as a branch name"

#: What `compose` suggests in a PR repository, instead of an `integrate` line.
PR_NEXT_STEP = "open a PR with /pr (or pass --local-trunk to integrate locally)"
ORIGIN_HOST_GITHUB = "github"

#: Exists in the git directory only while a merge is unfinished.
MERGE_HEAD = "MERGE_HEAD"

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


def _configure_open(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="branch name for the lane")
    parser.add_argument(
        "--path", help="worktree directory (default: beside the primary checkout)"
    )
    parser.add_argument(
        "--trunk",
        help="trunk ref (default: origin's default branch, else main or master)",
    )


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
        _require_free_path(path)
        if lane_core.branch_checked_out(name, cwd):
            raise lane_core.RefusalError(lane_core.branch_exists_refusal(name))
        raise
    print(f"worktree: {path}")
    print(f"branch: {name}")
    return lane_core.EXIT_OK


def _configure_compose(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--trunk",
        help="trunk ref (default: origin's default branch, else main or master)",
    )


def _integrate_command(trunk_arg: str | None, trunk_commit: str, tree: str) -> str:
    """The `integrate` line a reviewer runs next; `--trunk` only when it was given."""
    command = (
        f"lane.py integrate --expected-trunk {trunk_commit} --expected-tree {tree}"
    )
    return command if trunk_arg is None else f"{command} --trunk {trunk_arg}"


@dataclass(frozen=True)
class MergeTarget:
    """What `compose` merges: `label` for messages, `ref` for git."""

    label: str
    ref: str


def _contains(ancestor: str, descendant: str, lane_path: Path) -> bool:
    return lane_core.git_ok(
        ["merge-base", "--is-ancestor", ancestor, descendant], lane_path
    )


def _merge_targets(context: lane_core.LaneContext) -> list[MergeTarget]:
    """The trunk ref, plus the local trunk branch when it holds work the ref lacks.

    The local branch (`main` for `origin/main`) joins only when it exists and
    is not contained in the trunk ref. When it contains the trunk ref, it is
    the only target: merging it brings the trunk ref along.
    """
    lane_path = context.lane_path
    trunk = MergeTarget(context.trunk_ref, context.trunk_ref)
    local = context.trunk_branch
    if local is None or not lane_core.branch_exists(local, lane_path):
        return [trunk]
    local_target = MergeTarget(local, f"{lane_core.HEAD_REFS_PREFIX}{local}")
    if _contains(local_target.ref, trunk.ref, lane_path):
        return [trunk]
    if _contains(trunk.ref, local_target.ref, lane_path):
        return [local_target]
    return [trunk, local_target]


@dataclass(frozen=True)
class Snapshot:
    """The lane as it was before compose touched it."""

    head: str
    tree: str


def _snapshot(lane_path: Path) -> Snapshot:
    return Snapshot(
        head=lane_core.git_text(["rev-parse", "--verify", "HEAD^{commit}"], lane_path),
        tree=lane_core.git_text(["rev-parse", "HEAD^{tree}"], lane_path),
    )


def _unmerged_paths(lane_path: Path) -> list[str]:
    listed = lane_core.git_text(
        ["diff", "--name-only", "--diff-filter=U", "-z"], lane_path
    )
    return [path for path in listed.split("\0") if path]


def _merge_refusal(
    target: MergeTarget, attempt: lane_core.GitAttempt, lane_path: Path
) -> lane_core.Refusal:
    """Why the merge failed. Read before the restore: it erases the evidence."""
    unmerged = _unmerged_paths(lane_path)
    if unmerged:
        return lane_core.compose_conflict_refusal(target.label, unmerged)
    return lane_core.compose_merge_failed_refusal(
        target.label, attempt.command, attempt.detail
    )


def _merge_in_progress(lane_path: Path) -> bool:
    return lane_core.git_ok(["rev-parse", "--verify", "--quiet", MERGE_HEAD], lane_path)


def _restore_verified(snapshot: Snapshot, lane_path: Path) -> bool:
    """Put the lane back to `snapshot`, then check that it is there.

    `reset --hard` also undoes an earlier successful merge and a rejected merge
    that left a merged index without `MERGE_HEAD`. True only when HEAD and its
    tree match, no path is unmerged or dirty and no merge is in progress.
    """
    try:
        if _merge_in_progress(lane_path):
            lane_core.git_ok(["merge", "--abort"], lane_path)
        lane_core.git_ok(["reset", "--hard", snapshot.head], lane_path)
        return (
            _snapshot(lane_path) == snapshot
            and not lane_core.git_text(["ls-files", "-u"], lane_path)
            and not _merge_in_progress(lane_path)
            and not lane_core.dirty_paths(lane_path)
        )
    except lane_core.RefusalError:
        return False


def _merge_all(
    targets: Sequence[MergeTarget], snapshot: Snapshot, lane_path: Path
) -> None:
    """Merge each target the lane lacks; on a failure, restore and refuse."""
    for target in targets:
        if _contains(target.ref, "HEAD", lane_path):
            continue
        attempt = lane_core.git_attempt(["merge", "--no-edit", target.ref], lane_path)
        if not attempt.ok:
            try:
                refusal = _merge_refusal(target, attempt, lane_path)
            except lane_core.RefusalError as unreadable:
                # Still restore: the lane must not stay half merged.
                refusal = unreadable.refusal
            if not _restore_verified(snapshot, lane_path):
                refusal = lane_core.compose_restore_unverified_refusal(
                    target.label, snapshot.head, refusal.why
                )
            raise lane_core.RefusalError(refusal)


def _enter_lane(trunk_arg: str | None, cwd: Path) -> tuple[lane_core.LaneContext, str]:
    """The lane `cwd` is in and the trunk commit, or a refusal.

    Shared by every command that works inside a lane: a repository, a
    resolvable trunk and a lane, checked in that order.
    """
    lane_core.require_work_tree(cwd)
    trunk_ref, trunk_commit = lane_core.resolve_trunk_commit(trunk_arg, cwd)
    context = lane_core.lane_context(trunk_ref, cwd)
    if context is None:
        raise lane_core.RefusalError(lane_core.not_in_a_lane_refusal(cwd, trunk_ref))
    return context, trunk_commit


def _require_clean(lane_path: Path) -> None:
    dirty = lane_core.dirty_paths(lane_path)
    if dirty:
        raise lane_core.RefusalError(
            lane_core.lane_has_uncommitted_changes_refusal(dirty)
        )


def _next_step(
    trunk_arg: str | None, trunk_commit: str, tree: str, lane_path: Path
) -> str:
    """`integrate` for a local-trunk lane; `/pr` when the origin is on GitHub."""
    host = git_origin_host.classify(lane_core.origin_url(lane_path))
    if host == ORIGIN_HOST_GITHUB:
        return PR_NEXT_STEP
    return _integrate_command(trunk_arg, trunk_commit, tree)


def cmd_compose(args: argparse.Namespace, cwd: Path) -> int:
    context, trunk_commit = _enter_lane(args.trunk, cwd)
    _require_clean(context.lane_path)
    snapshot = _snapshot(context.lane_path)
    _merge_all(_merge_targets(context), snapshot, context.lane_path)
    tree = lane_core.git_text(["rev-parse", "HEAD^{tree}"], context.lane_path)
    print(f"lane: {context.branch}")
    print(f"trunk: {context.trunk_ref}")
    print(f"expected-trunk: {trunk_commit}")
    print(f"expected-tree: {tree}")
    print(f"next: {_next_step(args.trunk, trunk_commit, tree, context.lane_path)}")
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
