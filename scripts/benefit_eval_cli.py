#!/usr/bin/env python3
"""benefit_eval_cli.py — instrument audit and benefit report for the benefit evaluation.

``audit`` reads the pre-registration, confirms each instrument it names emits
for at least three real sessions, and names any metric with no persisted
instrument. ``report`` computes each metric against its pre-registered
threshold. Both are read-only: they never write, rewrite or reorder an input.

    benefit_eval_cli.py audit [--json]
    benefit_eval_cli.py report [--seed N] [--json]

Exit codes: 0 ok; 1 finding (gap, no instrument, or a threshold breach); 2
malformed input or missing argument; 3 insufficient data. Session ids print as
their first 8 characters. Output is plain text with literal status tokens, no ANSI.

Monorepo-only evaluation tooling; logic lives in scripts/lib/benefit_eval/.
Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from benefit_eval import formatting, metrics_hooks, metrics_ledger, prereg, streams

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


def run_report(args: argparse.Namespace) -> int:
    pre = prereg.load_prereg(args.prereg)
    sources = streams.Sources(
        tuple(args.project_root or [Path.cwd()]), args.home_metrics, args.projects_root
    )
    ctx = formatting.ReportContext(
        pre,
        sources,
        streams.SessionIndex(sources.projects_root),
        start=args.window_start,
        end=args.window_end,
        seed=args.seed,
    )
    transcripts = metrics_hooks.SubagentTranscripts(sources.projects_root)
    handlers = {
        "skip-rate": (
            metrics_ledger.skip_rate,
            [metrics_ledger.missing_scope_marker_split],
        ),
        "abort-yield": (metrics_ledger.abort_yield, []),
        "injection-overhead": (metrics_hooks.injection_overhead, []),
        "injection-uptake": (
            lambda metric, c: metrics_hooks.injection_uptake(metric, c, transcripts),
            [],
        ),
        "guard-divergence": (
            metrics_hooks.completion_guard_divergence,
            [
                lambda metric, c: metrics_hooks.completion_guard_sample(
                    metric, c, transcripts
                )
            ],
        ),
    }
    lines, notes = [], []
    for metric in pre.metrics:
        if metric.id not in handlers:
            raise streams.InputError(
                pre.path,
                0,
                f"the report has no computation for metric '{metric.id}'",
                "remove the entry or add its computation",
            )
        compute, note_makers = handlers[metric.id]
        lines.append(compute(metric, ctx))
        notes += [make(metric, ctx) for make in note_makers]
    code = formatting.combined_exit_code(line.outcome.exit_code for line in lines)
    run_at = formatting.utc_now()
    if args.json:
        print(
            json.dumps(
                {
                    "run_at": run_at,
                    "seed": args.seed,
                    "metrics": [line.as_dict() for line in lines],
                    "notes": {note.key: note.data for note in notes},
                    "exit_code": code,
                },
                indent=2,
            )
        )
    else:
        print(render_report_text(run_at, args.seed, lines, notes))
    return code


def render_report_text(
    run_at: str,
    seed: int,
    lines: list[formatting.ReportLine],
    notes: list[formatting.ReportNote],
) -> str:
    out = [f"run at (UTC): {run_at}", f"seed: {seed}"]
    for line in lines:
        out += line.text()
    for note in notes:
        out += note.lines
    return "\n".join(out)


def _utc_argument(text: str) -> datetime:
    try:
        return streams.parse_utc(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not an ISO 8601 UTC timestamp ending in Z, for example 2026-11-12T10:00:00Z"
        ) from exc


def _add_source_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--prereg", type=Path, default=DEFAULT_PREREG, help="path to preregistration.md"
    )
    command.add_argument(
        "--project-root",
        type=Path,
        action="append",
        help="project whose .claude/metrics to read; repeatable; default: current directory",
    )
    command.add_argument(
        "--home-metrics",
        type=Path,
        default=Path.home() / ".claude" / "metrics",
        help="home metrics directory",
    )
    command.add_argument(
        "--projects-root",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="transcript tree used to confirm real sessions",
    )
    command.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benefit_eval_cli.py", description=__doc__.split("\n\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser(
        "audit", help="confirm each pre-registered instrument emits"
    )
    _add_source_arguments(audit)
    audit.set_defaults(handler=run_audit)
    report = commands.add_parser(
        "report", help="compute each metric against its pre-registered threshold"
    )
    _add_source_arguments(report)
    report.add_argument(
        "--window-start",
        type=_utc_argument,
        help="count rows at or after this ISO 8601 UTC timestamp (Z); default: no start",
    )
    report.add_argument(
        "--window-end",
        type=_utc_argument,
        help="count rows before this ISO 8601 UTC timestamp (Z); default: no end",
    )
    report.add_argument(
        "--seed",
        type=int,
        default=0,
        help="seed for the completion-guard hand-check sample (default 0)",
    )
    report.set_defaults(handler=run_report)
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
