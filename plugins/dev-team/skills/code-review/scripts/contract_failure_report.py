#!/usr/bin/env python3
"""Per-agent contract-parse failure rate (#1998).

`validate_review_output.py` logs one row to `contract-failures.jsonl` per
review-agent output that fails the shared JSON contract. On its own that log
answers "how many failures" but not "out of how many dispatches" — the same
denominator problem `review_value_coverage.py` solved for `review-value.jsonl`
by joining against `agent_dispatch_ledger.py`'s deterministic
`boundary-events.jsonl` "record" rows. This module does the same join for the
failure log: `rate = failures / dispatches`, per agent, so #1980/#1982 can
read a real per-lens `$/finding` denominator instead of a lossy one, and so
this rate is reported as a metric rather than asserted from memory (#1998
acceptance criterion 2).

The ledger-reading half of that join (`read_jsonl`, `dispatch_counts`, the
`boundary-events.jsonl` predicate) lives in `hooks/lib/review_dispatch_ledger.py`,
shared with `review_value_coverage.py` — both used to hand-roll an identical
copy; see that module's docstring.

Caveat on the rate: the denominator (`boundary-events.jsonl`'s
`agent_dispatch_ledger` "record" rows) counts every dispatch of a registered
review agent, from any caller — `/code-review`, `/build`'s inline checkpoints,
`/repo-review` — while `validate_review_output.py` (the numerator) is only
ever invoked from `/code-review` step 4 and sliced-mode's equivalent step.
Dispatches this module never contract-checked still inflate the denominator
and can never contribute to the numerator, so the reported rate is a LOWER
bound on the true per-agent contract-failure rate, not an exact figure.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import review_dispatch_ledger  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    review_dispatch_ledger = None

FAILURE_STREAM = "contract-failures.jsonl"
LEDGER_STREAM = review_dispatch_ledger.LEDGER_STREAM if review_dispatch_ledger else "boundary-events.jsonl"


def _resolve(stream: str, cwd: Path) -> Path:
    # Read-only report: migrate=False so running it never migrates a legacy
    # top-level metrics/ file or creates .claude/metrics/ as a side effect
    # (mirrors hooks/lib/metrics_query.py::_stream_path's same reasoning).
    if review_dispatch_ledger is not None:
        return review_dispatch_ledger.resolve_stream("metrics", stream, cwd, migrate=False)
    return cwd / ".claude" / "metrics" / stream


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return (rows, malformed_count). Delegates to
    `hooks/lib/review_dispatch_ledger.py` (#1998); degrades to an empty
    result (fail-open, same posture as `validate_review_output.log_failure`)
    rather than re-deriving the ledger's wire shape by hand a third time if
    `hooks/lib` is unreachable."""
    if review_dispatch_ledger is None:  # pragma: no cover - degraded fallback
        return [], 0
    return review_dispatch_ledger.read_jsonl(path)


def dispatch_counts(ledger_rows) -> Counter:
    """Per-agent dispatch counts from the deterministic ledger. Delegates to
    `hooks/lib/review_dispatch_ledger.py` (#1998); see `read_jsonl` above for
    why the fallback degrades rather than re-implements."""
    if review_dispatch_ledger is None:  # pragma: no cover - degraded fallback
        return Counter()
    return review_dispatch_ledger.dispatch_counts(ledger_rows)


def failure_counts(failure_rows) -> tuple[Counter, dict]:
    """Per-agent failure totals, plus a per-agent shape breakdown."""
    counts: Counter = Counter()
    shapes: dict = defaultdict(Counter)
    for row in failure_rows:
        agent = row.get("agent")
        if not (isinstance(agent, str) and agent.strip()):
            continue
        agent = agent.strip()
        counts[agent] += 1
        shape = row.get("shape")
        if isinstance(shape, str) and shape.strip():
            shapes[agent][shape.strip()] += 1
    return counts, shapes


def build_report(failure_rows, ledger_rows) -> dict:
    dispatches = dispatch_counts(ledger_rows)
    failures, shapes = failure_counts(failure_rows)
    total_dispatches = sum(dispatches.values())
    total_failures = sum(failures.values())

    per_agent = {}
    for agent in sorted(set(dispatches) | set(failures)):
        agent_dispatches = dispatches.get(agent, 0)
        agent_failures = failures.get(agent, 0)
        per_agent[agent] = {
            "dispatches": agent_dispatches,
            "failures": agent_failures,
            "rate": (agent_failures / agent_dispatches) if agent_dispatches else None,
            "shapes": dict(sorted(shapes.get(agent, {}).items())),
        }

    return {
        "totals": {
            "dispatches": total_dispatches,
            "failures": total_failures,
            "rate": (total_failures / total_dispatches) if total_dispatches else None,
        },
        "per_agent": per_agent,
    }


def run(cwd: Path) -> dict:
    failure_rows, failure_malformed = read_jsonl(_resolve(FAILURE_STREAM, cwd))
    ledger_rows, ledger_malformed = read_jsonl(_resolve(LEDGER_STREAM, cwd))
    report = build_report(failure_rows, ledger_rows)
    report["malformed_lines"] = {
        FAILURE_STREAM: failure_malformed,
        LEDGER_STREAM: ledger_malformed,
    }
    return report


def _format_text(report: dict) -> str:
    totals = report["totals"]
    rate = totals["rate"]
    lines = [
        (
            f"contract-parse failure rate: {'n/a' if rate is None else f'{rate:.1%}'} "
            f"({totals['failures']}/{totals['dispatches']} dispatches)"
        ),
        (
            "  note: dispatches counts every agent_dispatch_ledger record, including "
            "callers this module never contract-checks (e.g. /build inline checkpoints) "
            "— this rate is a lower bound, not exact"
        ),
    ]
    for agent, row in sorted(
        report["per_agent"].items(),
        key=lambda kv: (kv[1]["rate"] if kv[1]["rate"] is not None else -1),
        reverse=True,
    ):
        agent_rate = row["rate"]
        lines.append(
            f"  {agent}: {'n/a' if agent_rate is None else f'{agent_rate:.0%}'} "
            f"({row['failures']}/{row['dispatches']}) {row['shapes']}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report per-agent contract-parse failure rate from contract-failures.jsonl"
    )
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    report = run(Path(args.cwd) if args.cwd else Path.cwd())
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = ("build_report", "dispatch_counts", "failure_counts", "read_jsonl", "run")
