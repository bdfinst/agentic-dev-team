#!/usr/bin/env python3
"""Acceptance-examination CLI (#2270): `inputs`, `status`, `show`.

- `inputs --plan <file>` prints the numbered criteria, Gherkin, run commands
  and the plan marker line that `/build` Step 7.6 pastes into the examiner
  prompt.
- `status --plan <file> [--wait N]` runs the same gate as
  `progress_guardian --pre-pr`; exit 0 when the examination is current and
  `met` (or the plan is exempt), exit 1 with exactly one refusal message.
- `show --plan <file>` prints the examination record JSON.

Exit codes: 0 success, 1 refusal or absent record, 2 usage error or an
unreadable record. A failure prints one stderr line, never a traceback.

Stdlib-only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple, NoReturn

_HERE = Path(__file__).resolve().parent
for _lib_dir in (_HERE.parent / "hooks" / "lib", _HERE / "lib"):
    if str(_lib_dir) not in sys.path:
        sys.path.insert(0, str(_lib_dir))

import examination_gate  # type: ignore[import-not-found]
import examination_store as store  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    AC_SECTION,
    plan_examination_inputs,
    render_inputs,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

DEFAULT_POLL_INTERVAL = 0.5
MET_LINE = "Acceptance examination met and up to date for {plan}."
NOT_APPLICABLE_LINE = (
    "Acceptance examination not applicable: "
    "the plan declares Examination: not-applicable."
)
WAITING_LINE = "Waiting for the acceptance examination record (up to {wait:g}s)..."

_ERROR = "error"
_PROG = "acceptance_examination.py"
_AC_HEADING = re.compile(rf"^## {re.escape(AC_SECTION)}\s*$", re.MULTILINE)


class UsageError(Exception):
    """A failure the caller reports as one stderr line and exit 2."""


class Loaded(NamedTuple):
    root: Path
    plan_id: str
    record_path: Path
    plan_text: str


class _Parser(argparse.ArgumentParser):
    """Argument errors become one stderr line and exit 2, with no usage dump."""

    def error(self, message: str) -> NoReturn:
        print(f"{_PROG}: error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _load(plan: str) -> Loaded:
    """Read the plan and resolve its repository, canonical id and record path."""
    try:
        plan_text = Path(plan).read_text(encoding="utf-8")
        root = store.repo_root(plan)
        plan_id = store.canonical_plan_id(plan, root)
    except store.NotARepository as exc:
        raise UsageError(str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot use plan {plan}: {exc}") from exc
    return Loaded(root, plan_id, store.record_path(root, plan_id), plan_text)


def cmd_inputs(args: argparse.Namespace) -> int:
    loaded = _load(args.plan)
    if not _AC_HEADING.search(loaded.plan_text):
        raise UsageError(f"{args.plan} has no '## {AC_SECTION}' section")
    inputs = plan_examination_inputs(loaded.plan_text)
    print(render_inputs(inputs, loaded.plan_id))
    return EXIT_OK


def _non_negative_seconds(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number of seconds: {text!r}")
    if not seconds >= 0:  # also rejects NaN
        raise argparse.ArgumentTypeError(f"must be 0 or more: {text!r}")
    return seconds


def _blocking(issues: list[dict]) -> list[dict]:
    return [issue for issue in issues if issue["severity"] == _ERROR]


def _poll_gate(plan: str, wait: float, interval: float) -> list[dict]:
    """Check the gate; while it refuses, re-check until `wait` seconds pass."""
    issues = examination_gate.load_and_check(plan)
    if wait <= 0 or not _blocking(issues):
        return issues
    print(WAITING_LINE.format(wait=wait), file=sys.stderr)
    deadline = time.monotonic() + wait
    while _blocking(issues) and time.monotonic() < deadline:
        time.sleep(interval)  # 0 yields the CPU rather than busy-waiting
        issues = examination_gate.load_and_check(plan)
    return issues


def cmd_status(args: argparse.Namespace) -> int:
    loaded = _load(args.plan)
    issues = _poll_gate(args.plan, args.wait, args.poll_interval)
    blocking = _blocking(issues)
    if blocking:
        print(blocking[0]["message"])
        print(blocking[0]["suggestedFix"])
        return EXIT_REFUSED
    line = NOT_APPLICABLE_LINE if issues else MET_LINE.format(plan=loaded.plan_id)
    print(line)
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    path = _load(args.plan).record_path
    try:
        record = store.read_record(path)
    except FileNotFoundError:
        print(f"No examination record at {path}", file=sys.stderr)
        return EXIT_REFUSED
    except store.RecordUnreadable as exc:
        raise UsageError(f"examination record unreadable: {path} ({exc.problem})")
    except OSError as exc:
        raise UsageError(f"examination record unreadable: {path} ({exc})")
    print(json.dumps(record, indent=2))
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=_PROG, description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    inputs = commands.add_parser("inputs", help="print the examiner inputs block")
    inputs.add_argument("--plan", required=True, help="path to the plan file")
    inputs.set_defaults(handler=cmd_inputs)
    status = commands.add_parser("status", help="check the examination gate")
    status.add_argument("--plan", required=True, help="path to the plan file")
    status.add_argument(
        "--wait",
        type=_non_negative_seconds,
        default=0.0,
        help="seconds to wait for the record (default 0: check once)",
    )
    status.add_argument(
        "--poll-interval",
        type=_non_negative_seconds,
        default=DEFAULT_POLL_INTERVAL,
        help=f"seconds between checks (default {DEFAULT_POLL_INTERVAL})",
    )
    status.set_defaults(handler=cmd_status)
    show = commands.add_parser("show", help="print the examination record")
    show.add_argument("--plan", required=True, help="path to the plan file")
    show.set_defaults(handler=cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except UsageError as exc:
        print(f"{_PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
