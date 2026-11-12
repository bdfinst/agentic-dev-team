#!/usr/bin/env python3
"""benefit_eval_cli.py — instrument audit and benefit report for the benefit evaluation.

``audit`` reads the pre-registration, confirms each id-bearing instrument it
names emits for at least three real sessions, checks an id-less stream only for
rows, and names any metric with no persisted instrument. ``report`` computes each
metric against its pre-registered threshold. Both are read-only: they never write,
rewrite or reorder an input.

    benefit_eval_cli.py audit [--json]
    benefit_eval_cli.py report [--seed N] [--json]

Exit codes: 0 ok; 1 finding (gap, no instrument, or a threshold breach); 2
malformed input or missing argument; 3 insufficient data. A report's code comes from
the lines that feed a verdict only: id-less and DIRECTIONAL lines print their status
but never change it, except that malformed input is always 2. Session ids print as
their first 8 characters. Output is plain text with literal status tokens, no ANSI.

Monorepo-only evaluation tooling; logic lives in scripts/lib/benefit_eval/.
Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from benefit_eval import formatting, prereg, streams
from benefit_eval.formatting import ReportContext, ReportLine, ReportNote

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


@dataclass(frozen=True)
class Handler:
    """How the report computes one metric: its line, then any notes that ride with it."""

    compute: Callable[[prereg.Metric, ReportContext], ReportLine]
    notes: tuple[Callable[[prereg.Metric, ReportContext], ReportNote], ...] = ()


def _metric_modules():
    """The metric modules, imported on first use so the audit path loads only the reader and the pre-registration parser."""
    from benefit_eval import metrics_cost, metrics_hooks, metrics_ledger

    return metrics_cost, metrics_hooks, metrics_ledger


def _handler_for(metric: prereg.Metric, prereg_path: Path) -> Handler:
    """Hand-entered and unmeasurable metrics need no stream; every other metric needs a registered computation."""
    metrics_cost, metrics_hooks, metrics_ledger = _metric_modules()
    if (
        metric.instrument == streams.NO_INSTRUMENT
        or metric.id_less_handling == streams.UNMEASURABLE
    ):
        return Handler(metrics_cost.unmeasurable_line)
    if metric.instrument == streams.MANUAL_INSTRUMENT:
        return Handler(metrics_cost.manual_metric)
    handlers = {
        "skip-rate": Handler(
            metrics_ledger.skip_rate, (metrics_ledger.missing_scope_marker_split,)
        ),
        "abort-yield": Handler(
            metrics_ledger.abort_yield, (metrics_ledger.abort_frequency,)
        ),
        "injection-overhead": Handler(metrics_hooks.injection_overhead),
        "injection-uptake": Handler(metrics_hooks.injection_uptake),
        "guard-divergence": Handler(
            metrics_hooks.completion_guard_divergence,
            (metrics_hooks.completion_guard_sample,),
        ),
        "test-review-token-delta": Handler(metrics_hooks.test_review_token_delta),
        "contradicted-rate": Handler(
            metrics_cost.verdict_rate, (metrics_cost.skill_adoption,)
        ),
    }
    if metric.id not in handlers:
        raise streams.InputError(
            prereg_path,
            0,
            f"the report has no computation for metric '{metric.id}'",
            "remove the entry or add its computation",
        )
    return handlers[metric.id]


def run_report(args: argparse.Namespace) -> int:
    metrics_cost, metrics_hooks, _ = _metric_modules()
    pre = prereg.load_prereg(args.prereg)
    roots = tuple(args.project_root or [Path.cwd()])
    sources = streams.Sources(roots, args.home_metrics, args.projects_root)
    manual_file = args.manual_input or metrics_cost.manual_input_path(roots[0])
    index = streams.SessionIndex(sources.projects_root)
    ctx = ReportContext(
        sources,
        index,
        metrics_hooks.SubagentTranscripts(index),
        start=args.window_start,
        end=args.window_end,
        boundary=streams.parse_utc(args.boundary) if args.boundary else None,
        seed=args.seed,
        manual=metrics_cost.load_manual_input(manual_file, {m.id for m in pre.metrics}),
        manual_file=manual_file,
    )
    chosen = [(m, _handler_for(m, pre.path)) for m in pre.metrics]
    lines, notes = [], []
    for metric, handler in chosen:
        lines.append(formatting.mark_id_less(handler.compute(metric, ctx), metric))
        notes += [make(metric, ctx) for make in handler.notes]
    code = formatting.combined_exit_code(lines)
    run_at = formatting.utc_now()
    if args.json:
        print(
            json.dumps(
                {
                    "run_at": run_at,
                    "prereg_posted": args.prereg_posted,
                    "boundary": args.boundary,
                    "seed": args.seed,
                    "metrics": [line.as_dict() for line in lines],
                    "notes": {note.key: note.data for note in notes},
                    "exit_code": code,
                },
                indent=2,
            )
        )
    else:
        print(render_report_text(run_at, args, lines, notes))
    return code


def render_report_text(
    run_at: str,
    args: argparse.Namespace,
    lines: list[ReportLine],
    notes: list[ReportNote],
) -> str:
    out = [
        f"run at (UTC): {run_at}",
        f"prereg posted (UTC): {args.prereg_posted}",
        f"boundary (UTC): {args.boundary or 'not set'}",
        f"seed: {args.seed}",
    ]
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


def _utc_text(text: str) -> str:
    """A validated ISO 8601 UTC timestamp, kept as typed so the report echoes what the operator attested."""
    _utc_argument(text)
    return text


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
        "--prereg-posted",
        type=_utc_text,
        required=True,
        help="UTC time (ISO 8601, ending in Z) the pre-registration comment was posted; "
        "that it came before this run is your attestation, not checked",
    )
    report.add_argument(
        "--boundary",
        type=_utc_text,
        help="before and after split (ISO 8601 UTC ending in Z): before is ts < boundary, "
        "after is ts >= boundary; required when a before and after metric is pre-registered",
    )
    report.add_argument(
        "--manual-input",
        type=Path,
        help="hand-entered numbers; default: <first project root>/.claude/metrics/benefit-manual-input.json",
    )
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
