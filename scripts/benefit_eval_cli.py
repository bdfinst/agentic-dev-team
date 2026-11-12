#!/usr/bin/env python3
"""benefit_eval_cli.py — instrument audit for the benefit evaluation.

Reads the pre-registration, confirms each instrument it names emits for at
least three real sessions, and names any metric with no persisted instrument.
Read-only: it never writes, rewrites or reorders an input.

    benefit_eval_cli.py audit [--json]

Exit codes: 0 ok; 1 finding (gap or no instrument); 2 malformed input or
missing argument; 3 insufficient data. Session ids print as their first 8
characters. Output is plain text with literal status tokens, no ANSI.

Monorepo-only evaluation tooling; logic lives in scripts/lib/benefit_eval/.
Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from benefit_eval import prereg, streams

DEFAULT_PREREG = _SCRIPTS_DIR.parent / "docs" / "benefit-eval" / "preregistration.md"


def render_audit_text(statuses: list[streams.InstrumentStatus]) -> str:
    lines = []
    for status in statuses:
        if status.status == streams.STATUS_NO_INSTRUMENT:
            lines += [f"{metric}: {status.status}" for metric in status.metrics]
            continue
        lines.append(f"{status.instrument}: {status.status}")
        lines.append(f"  metrics: {', '.join(status.metrics)}")
        if status.has_counts:
            sessions = (
                f" ({', '.join(status.session_ids)})" if status.session_ids else ""
            )
            lines += [
                f"  real sessions: {status.real_sessions}{sessions}",
                f"  rows: {status.rows}",
                f"  unverified: {status.unverified_rows}",
                f"  skipped transcripts: {status.skipped_transcripts}",
            ]
    lines.append(f"findings: {sum(s.is_finding for s in statuses)}")
    return "\n".join(lines)


def run_audit(args: argparse.Namespace) -> int:
    pre = prereg.load_prereg(args.prereg)
    sources = streams.Sources(
        tuple(args.project_root or [Path.cwd()]), args.home_metrics, args.projects_root
    )
    statuses = streams.audit(pre.metrics, sources)
    code = streams.audit_exit_code(statuses)
    if args.json:
        print(
            json.dumps(
                {"statuses": [asdict(s) for s in statuses], "exit_code": code}, indent=2
            )
        )
    else:
        print(render_audit_text(statuses))
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benefit_eval_cli.py", description=__doc__.split("\n\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser(
        "audit", help="confirm each pre-registered instrument emits"
    )
    audit.add_argument(
        "--prereg", type=Path, default=DEFAULT_PREREG, help="path to preregistration.md"
    )
    audit.add_argument(
        "--project-root",
        type=Path,
        action="append",
        help="project whose .claude/metrics to read; repeatable; default: current directory",
    )
    audit.add_argument(
        "--home-metrics",
        type=Path,
        default=Path.home() / ".claude" / "metrics",
        help="home metrics directory",
    )
    audit.add_argument(
        "--projects-root",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="transcript tree used to confirm real sessions",
    )
    audit.add_argument(
        "--json", action="store_true", help="print InstrumentStatus records as JSON"
    )
    audit.set_defaults(handler=run_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except streams.InputError as exc:
        print(exc.message(), file=sys.stderr)
        return streams.EXIT_MALFORMED


if __name__ == "__main__":
    sys.exit(main())
