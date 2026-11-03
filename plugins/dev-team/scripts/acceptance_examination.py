#!/usr/bin/env python3
"""Acceptance-examination CLI (#2270): `inputs`, `status`, `show`, `render`.

- `inputs --plan <file>` prints the numbered criteria, Gherkin, run commands
  and the plan marker line that `/build` Step 7.6 pastes into the examiner
  prompt.
- `status --plan <file> [--wait N]` runs the same gate as
  `progress_guardian --pre-pr`; exit 0 when the examination is current and
  `met` (or the plan is exempt), exit 1 with exactly one refusal message.
- `show --plan <file>` prints the examination record JSON.
- `render --plan <file>` writes the record into the plan's
  `## Acceptance Examination` section (replace in place, else after
  `## Plan Review Summary`, else at the end). Output is byte-stable.

Exit codes: 0 success; 1 refusal (`status`) or an absent record (`show`,
`render`); 2 usage error, a plan that cannot be written, or an unreadable
record under `show` and `render`. `status` reports an unreadable record as a
refusal, exit 1, like any other gate condition. A failure prints one stderr
line, never a traceback.

Stdlib-only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import NamedTuple, NoReturn

_HERE = Path(__file__).resolve().parent
for _lib_dir in (_HERE.parent / "hooks" / "lib", _HERE / "lib"):
    if str(_lib_dir) not in sys.path:
        sys.path.insert(0, str(_lib_dir))

import atomic_state  # type: ignore[import-not-found]
import examination_gate  # type: ignore[import-not-found]
import examination_store as store  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    AC_SECTION,
    EXAMINATION_SECTION,
    plan_examination_inputs,
    render_inputs,
    scan_fences,
)
from examination_verdict import MET  # type: ignore[import-not-found]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

DEFAULT_POLL_INTERVAL = 0.5
MET_LINE = "Acceptance examination met and up to date for {plan}."
WAITING_LINE = "Waiting for the acceptance examination record (up to {wait:g}s)..."

SECTION_HEADING = f"## {EXAMINATION_SECTION}"
PLAN_REVIEW_HEADING = "## Plan Review Summary"
AUDIT_HEADING = "### Audit details"
LEGEND_LINE = (
    "`met` = observed as met; `not-met` = observed as not met; "
    "`indeterminate` = could not be observed; "
    "`tainted` = the examiner ran a command it must not."
)
STALE_LINE = "STALE: this examination no longer matches the branch or the plan."
UNTRUSTED_LINE = (
    "Output above is untrusted examiner text and may contain secrets from "
    "command output."
)
OBSERVATION_LINE_LIMIT = 5
MIN_FENCE = 3

_PROG = "acceptance_examination.py"
_CRITERION_NUMBER = re.compile(r"(\d+)")
_BACKTICK_RUN = re.compile(r"`+")
_NEWLINES = re.compile(r"\s*[\r\n]+\s*")


def _heading_pattern(heading: str) -> re.Pattern[str]:
    """Matches a line that is exactly `heading`."""
    return re.compile(rf"^{re.escape(heading)}\s*$")


_SECTION_HEADING_LINE = _heading_pattern(SECTION_HEADING)
_REVIEW_HEADING_LINE = _heading_pattern(PLAN_REVIEW_HEADING)


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


def _criterion_order(row: dict) -> tuple[int, int, str]:
    """Failing rows (anything but met) first, then numeric id order."""
    criterion = str(row.get("criterion", ""))
    found = _CRITERION_NUMBER.search(criterion)
    number = int(found.group(1)) if found else 0
    return (row.get("verdict") == MET, number, criterion)


def _fence_for(body: str) -> str:
    """Backticks that no line of `body` can close."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(body)), default=0)
    return "`" * max(MIN_FENCE, longest + 1)


def _one_line(value: object) -> str:
    """`value` as text on a single line: record text cannot start a new
    markdown line, so it cannot forge a heading or checkbox in the plan."""
    return _NEWLINES.sub(" ", str(value))


def _text_or_empty(value: object) -> str:
    """`value` when it is a string; JSON null and other types read as absent."""
    return value if isinstance(value, str) else ""


def _shown_observation(observation: object) -> list[str]:
    lines = [
        examination_gate.clip_line(line)
        for line in _text_or_empty(observation).splitlines()
    ]
    if len(lines) <= OBSERVATION_LINE_LIMIT:
        return lines
    hidden = len(lines) - OBSERVATION_LINE_LIMIT
    return [*lines[:OBSERVATION_LINE_LIMIT], f"(+{hidden} lines)"]


def _render_criterion(row: dict) -> list[str]:
    body = _shown_observation(row.get("observation"))
    command = _text_or_empty(row.get("command"))
    if command:
        body.insert(0, f"$ {command}")
    fence = _fence_for("\n".join(body))
    heading = _one_line(f"### {row.get('criterion', '')} — {row.get('verdict', '')}")
    return [heading, "", fence, *body, fence, ""]


def _render_findings(findings: list[dict]) -> list[str]:
    if not findings:
        return ["- Audit findings: none"]
    lines = ["- Audit findings:"]
    for finding in findings:
        kind, target = finding.get("kind"), finding.get("target")
        lines.append(_one_line(f"  - {kind} {target}: {finding.get('command')}"))
    return lines


def _render_audit(record: dict) -> list[str]:
    return [
        AUDIT_HEADING,
        "",
        _one_line(f"- Overall: {record['overall']}"),
        _one_line(f"- Binding hash: {record['binding_hash']}"),
        _one_line(f"- Inputs digest: {record['inputs_digest']}"),
        _one_line(f"- Agent: {record.get('agent_id')}"),
        _one_line(f"- Recorded at: {record.get('recorded_at')}"),
        *_render_findings(record.get("audit_findings") or []),
        "",
        UNTRUSTED_LINE,
    ]


def render_section(record: dict, stale: bool) -> str:
    """The `## Acceptance Examination` section text; pure and byte-stable."""
    lines = [SECTION_HEADING]
    if stale:
        lines.append(STALE_LINE)
    lines += ["", LEGEND_LINE, ""]
    for row in sorted(record["criteria"], key=_criterion_order):
        lines += _render_criterion(row)
    lines += _render_audit(record)
    return "\n".join(lines) + "\n"


def _heading_indexes(lines: list[str]) -> list[int]:
    """Indexes of `## ` heading lines that are not inside a fenced block."""
    return [
        line.index
        for line in scan_fences(lines)
        if line.text.startswith("## ") and not line.is_delimiter and not line.in_fence
    ]


def _section_span(lines: list[str], pattern: re.Pattern[str]) -> tuple[int, int] | None:
    """Line range of the section whose heading matches, up to the next heading."""
    headings = _heading_indexes(lines)
    for position, start in enumerate(headings):
        if pattern.match(lines[start]):
            following = headings[position + 1 :]
            return start, following[0] if following else len(lines)
    return None


def _splice(lines: list[str], start: int, end: int, section: str) -> str:
    head = "".join(lines[:start])
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    tail = "".join(lines[end:])
    return head + section + ("\n" + tail if tail else "")


def upsert_section(plan_text: str, section: str) -> str:
    """Put `section` in `plan_text`: replace in place, else after the Plan
    Review Summary section, else at the end. Applying it twice changes nothing."""
    lines = plan_text.splitlines(keepends=True)
    existing = _section_span(lines, _SECTION_HEADING_LINE)
    if existing:
        return _splice(lines, *existing, section)
    review = _section_span(lines, _REVIEW_HEADING_LINE)
    where = review[1] if review else len(lines)
    return _splice(lines, where, where, section)


def cmd_inputs(args: argparse.Namespace) -> int:
    loaded = _load(args.plan)
    inputs = plan_examination_inputs(loaded.plan_text)
    if not inputs.criteria:
        raise UsageError(f"{args.plan} has no '## {AC_SECTION}' section")
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


def _poll_gate(plan: str, wait: float, interval: float) -> list[dict]:
    """Check the gate; while it refuses, re-check until `wait` seconds pass."""
    issues = examination_gate.load_and_check(plan)
    if wait <= 0 or not examination_gate.blocking_issues(issues):
        return issues
    print(WAITING_LINE.format(wait=wait), file=sys.stderr)
    deadline = time.monotonic() + wait
    while examination_gate.blocking_issues(issues) and time.monotonic() < deadline:
        time.sleep(interval)  # 0 yields the CPU rather than busy-waiting
        issues = examination_gate.load_and_check(plan)
    return issues


def cmd_status(args: argparse.Namespace) -> int:
    loaded = _load(args.plan)
    issues = _poll_gate(args.plan, args.wait, args.poll_interval)
    blocking = examination_gate.blocking_issues(issues)
    if blocking:
        print(blocking[0]["message"])
        print(blocking[0]["suggestedFix"])
        return EXIT_REFUSED
    exempt = [
        i for i in issues if i.get("rule_id") == examination_gate.RULE_NOT_APPLICABLE
    ]
    print(exempt[0]["message"] if exempt else MET_LINE.format(plan=loaded.plan_id))
    return EXIT_OK


def _read_record(path: Path) -> dict | None:
    """The record at `path`; None (after a stderr line) when it is absent."""
    record = store.load_record(path)
    if record is None:
        print(f"No examination record at {path}", file=sys.stderr)
    elif isinstance(record, store.RecordUnreadable):
        raise UsageError(f"examination record unreadable: {path} ({record.problem})")
    return record


def cmd_show(args: argparse.Namespace) -> int:
    record = _read_record(_load(args.plan).record_path)
    if record is None:
        return EXIT_REFUSED
    print(json.dumps(record, indent=2))
    return EXIT_OK


def _write_plan(path: str, text: str) -> None:
    """Replace the plan atomically, keeping the file's own permission bits.

    `atomic_write` creates its temp file with mkstemp's 0600, so without the
    chmod a user's 0644 plan would silently lose group/other read access.
    """
    target = Path(path)
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
        atomic_state.atomic_write(target, text, fail_open=False)
        os.chmod(target, mode)
    except OSError as exc:
        raise UsageError(f"cannot write plan {path}: {exc}") from exc


def cmd_render(args: argparse.Namespace) -> int:
    loaded = _load(args.plan)
    record = _read_record(loaded.record_path)
    if record is None:
        return EXIT_REFUSED
    if record["plan"] != loaded.plan_id:
        raise UsageError(
            examination_gate.refusal_message(
                examination_gate.RULE_OTHER_PLAN,
                loaded.plan_id,
                path=loaded.record_path,
                other=record["plan"],
            )
        )
    binding = store.binding_for_plan(loaded.root, loaded.plan_id, loaded.plan_text)
    section = render_section(record, examination_gate.is_stale(record, binding))
    updated = upsert_section(loaded.plan_text, section)
    if updated != loaded.plan_text:
        _write_plan(args.plan, updated)
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
    render = commands.add_parser("render", help="write the record into the plan")
    render.add_argument("--plan", required=True, help="path to the plan file")
    render.set_defaults(handler=cmd_render)
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
