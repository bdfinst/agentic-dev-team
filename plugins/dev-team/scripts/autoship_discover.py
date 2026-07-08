#!/usr/bin/env python3
"""autoship_discover.py — deterministic issue discovery for `/dev-team:autoship` (#989).

Selects open, non-epic issues labeled `autoship:ready` (or `--label`) that
are not already `autoship:in-progress`/`autoship:blocked` and have no open
linked pull request, ordered oldest-first and capped at `--max-issues`. This
is deterministic filtering, not model judgment — see the plan's Architectural
Context (`plans/issue-989-autoship-discovery-reclaim.md`) for the precedent
this follows (`scripts/plan_waves.py`, `scripts/git_origin_host.py`).

Usage:
    autoship_discover.py --max-issues 3 --max-cost-usd 25
    autoship_discover.py --max-issues 3 --max-cost-usd 25 --label autoship:ready
    autoship_discover.py --max-issues 3 --max-cost-usd 25 --input-file fixture.json

`--max-issues` and `--max-cost-usd` are both required — a missing cap is a
hard CLI failure, never a silently-assumed default, since an uncapped round
could dispatch unboundedly. `--input-file` bypasses the live `gh` fetch
entirely for tests/dry runs; production use relies on `gh`'s cwd-based repo
auto-detection (no `--repo` flag — see the plan's Decision-defaults stance).

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import autoship_state  # noqa: E402

DEFAULT_LABEL = "autoship:ready"
IN_PROGRESS_LABEL = "autoship:in-progress"
BLOCKED_LABEL = "autoship:blocked"

# Same fields `gh issue list --json` returns for these names — no schema
# invention. `title` is required because the stdout contract emits it;
# `state` is required because `select_eligible` checks it directly.
REQUIRED_ISSUE_FIELDS = (
    "number",
    "title",
    "state",
    "createdAt",
    "labels",
    "closedByPullRequestsReferences",
    "subIssuesSummary",
)

GH_JSON_FIELDS = ",".join(REQUIRED_ISSUE_FIELDS)


class DiscoveryError(Exception):
    """A discovery-input or `gh` fetch problem that must surface as a clear
    CLI error message, not an uncaught exception/traceback."""


def _positive_int(raw: str) -> int:
    """`argparse` `type=` validator for `--max-issues`: rejects `<= 0` at the
    CLI boundary rather than silently clamping downstream — mirrors
    `evals/code-review-benchmark/cli.py`'s `_positive_int`."""
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(
            f"--max-issues must be a positive integer, got {raw!r}"
        )
    return value


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
        type=_positive_int,
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


def validate_issues(issues: Any) -> None:
    """Validate `issues` is a JSON array of objects each carrying every
    `REQUIRED_ISSUE_FIELDS` entry.

    Raises `DiscoveryError` naming the malformed entry (by issue number if
    present, by index otherwise) rather than letting a `KeyError` propagate
    uncaught.
    """
    if not isinstance(issues, list):
        raise DiscoveryError(
            "--input-file must contain a JSON array of issue objects, got "
            f"{type(issues).__name__}"
        )
    for idx, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise DiscoveryError(
                f"malformed --input-file entry at index {idx}: not a JSON object"
            )
        missing = [field for field in REQUIRED_ISSUE_FIELDS if field not in issue]
        if missing:
            identifier = f"#{issue['number']}" if "number" in issue else f"index {idx}"
            raise DiscoveryError(
                f"malformed --input-file entry ({identifier}): missing required "
                f"field(s) {', '.join(missing)}"
            )


def load_issues_from_file(path: str) -> List[Dict[str, Any]]:
    """Read and validate the `--input-file` JSON array of issue objects.

    Raises `DiscoveryError` on unreadable/malformed JSON or a schema
    violation — never an uncaught exception.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            issues = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"--input-file {path!r} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise DiscoveryError(f"--input-file {path!r} could not be read: {exc}") from exc
    validate_issues(issues)
    return issues


def _label_names(issue: Dict[str, Any]) -> List[str]:
    return [label["name"] for label in issue["labels"]]


def _is_epic(issue: Dict[str, Any]) -> bool:
    return issue["subIssuesSummary"].get("total", 0) > 0


def _has_open_linked_pr(issue: Dict[str, Any]) -> bool:
    """True when any entry in `closedByPullRequestsReferences` is itself
    still open — a single open PR anywhere in the list excludes the issue,
    even when other entries in the same list are closed/merged."""
    return any(
        pr.get("state") == "OPEN" for pr in issue["closedByPullRequestsReferences"]
    )


def is_eligible(issue: Dict[str, Any], label: str) -> bool:
    """True when `issue` qualifies for autoship dispatch: open, carries
    `label`, is not in-progress/blocked, is not an epic, and has no open
    linked pull request."""
    if issue["state"] != "OPEN":
        return False
    labels = _label_names(issue)
    if label not in labels:
        return False
    if IN_PROGRESS_LABEL in labels or BLOCKED_LABEL in labels:
        return False
    if _is_epic(issue):
        return False
    if _has_open_linked_pr(issue):
        return False
    return True


def select_eligible(
    issues: List[Dict[str, Any]], label: str, max_issues: int
) -> List[Dict[str, Any]]:
    """Filter `issues` to those eligible for autoship dispatch, sorted
    oldest-first by `createdAt` and truncated to `max_issues` (a cap of `0`
    truncates to an empty list, not an error)."""
    eligible = [issue for issue in issues if is_eligible(issue, label)]
    eligible.sort(key=lambda issue: issue["createdAt"])
    return eligible[:max_issues]


def render_selection(issues: List[Dict[str, Any]]) -> str:
    """Render the stable stdout contract `/dev-team:autoship` (#992) parses:
    a JSON array of `{number, title}` objects."""
    return json.dumps(
        [{"number": issue["number"], "title": issue["title"]} for issue in issues]
    )


def fetch_issues_from_gh(label: str) -> List[Dict[str, Any]]:
    """Fetch open issues labeled `label` via a live `gh issue list` call,
    using `gh`'s cwd-based repo auto-detection (no `--repo` flag — see the
    plan's Decision-defaults stance).

    The `--state open` server-side filter and the requested `state` field
    are intentionally redundant with `select_eligible`'s own `state ==
    "OPEN"` check — this is what makes the `--input-file` and live paths
    behave identically.

    Raises `DiscoveryError` on a non-zero `gh` exit or malformed JSON output
    — never an uncaught `CalledProcessError`/`JSONDecodeError`/traceback.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                GH_JSON_FIELDS,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DiscoveryError(f"gh CLI not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise DiscoveryError(
            f"gh issue list failed (exit {exc.returncode}): {stderr}"
        ) from exc

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"gh issue list returned malformed JSON: {exc}") from exc

    validate_issues(issues)
    return issues


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.input_file:
            issues = load_issues_from_file(args.input_file)
        else:
            issues = fetch_issues_from_gh(args.label)
    except DiscoveryError as exc:
        print(f"autoship_discover: {exc}", file=sys.stderr)
        return 1

    selected = select_eligible(issues, args.label, args.max_issues)
    print(render_selection(selected))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
