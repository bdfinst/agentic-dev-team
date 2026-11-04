#!/usr/bin/env python3
"""lane.py -- identity-checked lanes: open, compose, integrate.

Only `open` is registered so far. Usage errors exit 2, refusals exit 1
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


@dataclass(frozen=True)
class Command:
    name: str
    add_parser: Callable[[argparse._SubParsersAction], None]
    handler: Callable[[argparse.Namespace, Path], int]


def _add_open(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        OPEN_COMMAND,
        help="create a lane: a linked worktree and branch at the trunk tip",
    )
    parser.add_argument("name", help="branch name for the lane")
    parser.add_argument(
        "--path", help="worktree directory (default: beside the primary checkout)"
    )
    parser.add_argument(
        "--trunk", help="trunk ref (default: the remote default branch)"
    )


def _name_problem(name: str, cwd: Path) -> str | None:
    """Why `name` is unusable, or None. The pattern runs before git sees it."""
    if lane_core.REF_PATTERN.fullmatch(name) is None:
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
    branch_ref = f"{lane_core.HEAD_REFS_PREFIX}{name}"
    if lane_core.git_ok(["show-ref", "--verify", "--quiet", branch_ref], cwd):
        raise lane_core.RefusalError(lane_core.branch_exists_refusal(name))


def _branch_is_checked_out(name: str, cwd: Path) -> bool:
    """True when a worktree has branch `name` checked out."""
    listing = lane_core.git_text(["worktree", "list", "--porcelain"], cwd)
    return f"branch {lane_core.HEAD_REFS_PREFIX}{name}" in listing.splitlines()


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
        if _branch_is_checked_out(name, cwd):
            raise lane_core.RefusalError(lane_core.branch_exists_refusal(name))
        raise
    print(f"worktree: {path}")
    print(f"branch: {name}")
    return lane_core.EXIT_OK


#: Every registered command, by name.
COMMANDS: dict[str, Command] = {
    OPEN_COMMAND: Command(OPEN_COMMAND, _add_open, cmd_open),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lane.py", description="Identity-checked lanes: open, compose, integrate."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )
    for command in COMMANDS.values():
        command.add_parser(subparsers)
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
