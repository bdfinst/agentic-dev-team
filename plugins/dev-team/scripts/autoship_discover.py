#!/usr/bin/env python3
"""autoship_discover.py — deterministic issue discovery for `/dev-team:autoship` (#989).

Selects open, non-epic issues labeled `autoship:ready` (or `--label`) that
are not already `autoship:in-progress`/`autoship:blocked` and have no open
linked pull request, ordered oldest-first and capped at `--max-issues`. This
is deterministic filtering, not model judgment — see the plan's Architectural
Context (`plans/issue-989-autoship-discovery-reclaim.md`) for the precedent
this follows (`scripts/plan_waves.py`, `scripts/git_origin_host.py`).

The `gh` fetch, `--input-file` schema validation, and eligibility filter are
shared with `autoship_group.py` via `autoship_state.fetch_eligible_issues` —
this script's own concern is only the `--max-issues` cap on top of that
shared, full eligible pool.

Usage:
    autoship_discover.py --max-issues 3 --max-cost-usd 25
    autoship_discover.py --max-issues 3 --max-cost-usd 25 --label autoship:ready
    autoship_discover.py --max-issues 3 --max-cost-usd 25 --input-file fixture.json

`--max-issues` and `--max-cost-usd` are both required — a missing cap is a
hard CLI failure, never a silently-assumed default, since an uncapped round
could dispatch unboundedly. `--input-file` bypasses the live `gh` fetch
entirely for tests/dry runs; production use relies on `gh`'s cwd-based repo
auto-detection (no `--repo` flag — see the plan's Decision-defaults stance).

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import autoship_state

DEFAULT_LABEL = autoship_state.READY_LABEL


def build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert required/rejected values via
    `build_parser().parse_args([...])` without exercising `main()`'s
    file/`gh` I/O."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--max-issues",
        type=autoship_state.positive_int_validator("--max-issues"),
        required=True,
        help="Maximum number of issues to select this round. Must be > 0.",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=autoship_state.positive_float_validator("--max-cost-usd"),
        required=True,
        help=(
            "Budget cap in USD for the round, consumed by /dev-team:autoship's "
            "own scheduler (not enforced by this script). Must be > 0."
        ),
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Label marking an issue eligible for autoship (default: {DEFAULT_LABEL!r}).",
    )
    autoship_state.add_input_seam_args(parser)
    return parser


def select_eligible(
    issues: list[dict[str, Any]], label: str, max_issues: int
) -> list[dict[str, Any]]:
    """Filter `issues` to those eligible for autoship dispatch, sorted
    oldest-first by `createdAt` and truncated to `max_issues` (a cap of `0`
    truncates to an empty list, not an error).

    A pure post-processing step over an already-loaded issue list — kept
    independent of `autoship_state.fetch_eligible_issues`'s own fetch/filter/
    sort (which `main()` uses to source the full pool) so this stays testable
    against arbitrary in-memory issue data.
    """
    eligible = [issue for issue in issues if autoship_state.is_eligible(issue, label)]
    eligible.sort(key=lambda issue: issue["createdAt"])
    return eligible[:max_issues]


def render_selection(issues: list[dict[str, Any]]) -> str:
    """Render the stable stdout contract `/dev-team:autoship` (#992) parses:
    a JSON array of `{number, title}` objects."""
    return json.dumps(
        [{"number": issue["number"], "title": issue["title"]} for issue in issues]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        eligible = autoship_state.fetch_eligible_issues(
            args.label, input_file=args.input_file
        )
    except autoship_state.FetchError as exc:
        print(f"autoship_discover: {exc}", file=sys.stderr)
        return 1

    selected = eligible[: args.max_issues]
    print(render_selection(selected))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
