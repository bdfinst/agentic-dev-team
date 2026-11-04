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

import lane_core

#: Between the primary checkout's name and the lane name in a default path.
LANE_DIR_INFIX = "-lane-"

NAME_PATTERN_PROBLEM = (
    "it must start with a letter or digit and use only safe characters"
)
NAME_GIT_PROBLEM = "git does not accept it as a branch name"

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


def _merge_targets(
    context: lane_core.LaneContext, lane_path: Path
) -> list[MergeTarget]:
    """The trunk ref, plus the local trunk branch when it holds work the ref lacks.

    The local branch (`main` for `origin/main`) joins only when it exists and
    is not contained in the trunk ref. When it contains the trunk ref, it is
    the only target: merging it brings the trunk ref along.
    """
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


def _merge_if_missing(target: MergeTarget, lane_path: Path) -> None:
    """Merge `target` into the lane unless the lane's HEAD already contains it."""
    if _contains(target.ref, "HEAD", lane_path):
        return
    lane_core.git_text(["merge", "--no-edit", target.ref], lane_path)


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


def cmd_compose(args: argparse.Namespace, cwd: Path) -> int:
    context, trunk_commit = _enter_lane(args.trunk, cwd)
    _require_clean(context.lane_path)
    for target in _merge_targets(context, context.lane_path):
        _merge_if_missing(target, context.lane_path)
    tree = lane_core.git_text(["rev-parse", "HEAD^{tree}"], context.lane_path)
    print(f"lane: {context.branch}")
    print(f"trunk: {context.trunk_ref}")
    print(f"expected-trunk: {trunk_commit}")
    print(f"expected-tree: {tree}")
    print(f"next: {_integrate_command(args.trunk, trunk_commit, tree)}")
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
