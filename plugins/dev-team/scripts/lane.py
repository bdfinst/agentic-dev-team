#!/usr/bin/env python3
"""lane.py -- identity-checked lanes: open, compose, integrate.

Only `open`'s parser is registered so far; its handler arrives in the next
step. Usage errors exit 2, refusals exit 1 (blocks on stderr), success 0.

Import whitelist (pinned by an AST test): the standard library and
`lane_core`. Stdlib only otherwise. See ADR 0014 and ADR 0031.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane_core

#: Command name -> function that adds its subparser.
PARSERS: dict[str, Callable[[argparse._SubParsersAction], None]] = {}

#: Command name -> handler `(args, cwd) -> exit code`.
HANDLERS: dict[str, Callable[[argparse.Namespace, Path], int]] = {}


def _register_parser(name: str) -> Callable[[Callable], Callable]:
    def decorate(add: Callable) -> Callable:
        PARSERS[name] = add
        return add

    return decorate


@_register_parser("open")
def _add_open(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "open", help="create a lane: a linked worktree and branch at the trunk tip"
    )
    parser.add_argument("name", help="branch name for the lane")
    parser.add_argument(
        "--path", help="worktree directory (default: beside the primary checkout)"
    )
    parser.add_argument(
        "--trunk", help="trunk ref (default: the remote default branch)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lane.py", description="Identity-checked lanes: open, compose, integrate."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )
    for add in PARSERS.values():
        add(subparsers)
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
    handler = HANDLERS.get(args.command)
    if handler is None:
        sys.stderr.write(f"lane.py: {args.command} is not implemented yet\n")
        return lane_core.EXIT_USAGE
    try:
        return handler(args, Path(cwd) if cwd is not None else Path.cwd())
    except lane_core.RefusalError as exc:
        return lane_core.emit_refusals([exc.refusal])


if __name__ == "__main__":
    sys.exit(main())
