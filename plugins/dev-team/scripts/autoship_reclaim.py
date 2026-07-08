#!/usr/bin/env python3
"""Reclaim issues orphaned by a crashed/interrupted /dev-team:autoship round (#989).

Relabels a stale `autoship:in-progress` issue back to `autoship:blocked` with
an explanatory comment, so a crashed or interrupted autoship round doesn't
leave an issue permanently stuck "in progress". Deterministic, testable
Python — no model judgment, per the epic's architecture rationale (see plan
`plans/issue-989-autoship-discovery-reclaim.md`, Slice 3).

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import autoship_state  # noqa: E402

IN_PROGRESS_LABEL = "autoship:in-progress"
BLOCKED_LABEL = "autoship:blocked"


def select_orphaned(issues: list, stale_after_hours: float, now: datetime) -> list:
    """Return the subset of `issues` that are orphaned in-progress issues.

    An issue qualifies when it is open, carries `autoship:in-progress`, and
    its `labeled_at` (falling back to `updatedAt` when `labeled_at` is
    absent — the live-fetch path's best-effort fallback, added in a later
    step) is stale per `autoship_state.is_stale` (inclusive boundary).
    """
    orphaned = []
    for issue in issues:
        if issue.get("state") != "OPEN":
            continue
        labels = issue.get("labels") or []
        label_names = {
            label["name"] if isinstance(label, dict) else label for label in labels
        }
        if IN_PROGRESS_LABEL not in label_names:
            continue
        timestamp_raw = issue.get("labeled_at") or issue.get("updatedAt")
        if timestamp_raw is None:
            continue
        labeled_at = _parse_timestamp(timestamp_raw)
        if autoship_state.is_stale(labeled_at, stale_after_hours, now):
            orphaned.append(issue)
    return orphaned


def _parse_timestamp(raw) -> datetime:
    """Parse a `labeled_at`/`updatedAt` value into a `datetime`.

    Accepts either an already-parsed `datetime` (as tests may supply) or an
    ISO-8601 string (as `--input-file` JSON and the live `gh` fetch supply),
    tolerating a trailing `Z` suffix.
    """
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(raw.rstrip("Z"))


def _build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert defaults/overrides via `_build_parser().parse_args([...])`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stale-after-hours",
        type=autoship_state.positive_float_validator("--stale-after-hours"),
        default=24,
        help=(
            "Hours an issue may stay autoship:in-progress before it is "
            "considered orphaned (default 24)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview reclaims without commenting or relabeling (no gh calls).",
    )
    autoship_state.add_input_seam_args(parser)
    return parser


def _fetch_in_progress_issues() -> list:
    """Fetch open `autoship:in-progress` issues via `gh issue list`, enriched
    with each one's real `labeled_at` timestamp from its GitHub timeline.

    `labels` and `state` are requested even though the live fetch is already
    server-filtered to open + `autoship:in-progress`, so the fetched shape
    matches exactly what `select_orphaned` checks — same reasoning as
    discovery's live-fetch step. A failure fetching the issue list itself
    (non-zero `gh` exit or malformed JSON) is unrecoverable and propagates to
    the caller, which translates it to a clear stderr message. A failure
    looking up one issue's timeline is NOT fatal — it falls back to that
    issue's own `updatedAt` (see `_labeled_at_for`), so one issue's timeline
    hiccup never aborts the whole run.
    """
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--label",
            IN_PROGRESS_LABEL,
            "--json",
            "number,title,state,labels,updatedAt",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    issues = json.loads(result.stdout)
    try:
        repo = _current_repo()
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        # Repo resolution failing is one more "timeline lookup hiccup" —
        # every issue falls back to its own `updatedAt` rather than
        # aborting the whole run.
        repo = None
    for issue in issues:
        issue["labeled_at"] = _labeled_at_for(issue, repo)
    return issues


def _labeled_at_for(issue: dict, repo: Optional[str]) -> str:
    """Return the best `labeled_at` timestamp for `issue` in `repo`.

    Prefers the most recent `labeled` timeline event naming
    `autoship:in-progress`; falls back to the issue's own `updatedAt` when
    `repo` is unresolved, the timeline fetch fails, or no matching event is
    found. `repo` is resolved once by the caller and threaded through —
    resolving it per issue would cost one redundant `gh repo view`
    subprocess call per orphan candidate.
    """
    if repo is None:
        return issue["updatedAt"]
    try:
        timeline = _fetch_timeline(issue["number"], repo)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return issue["updatedAt"]

    labeled_events = [
        event
        for event in timeline
        if event.get("event") == "labeled"
        and event.get("label", {}).get("name") == IN_PROGRESS_LABEL
    ]
    if not labeled_events:
        return issue["updatedAt"]

    return labeled_events[-1]["created_at"]


def _fetch_timeline(number: int, repo: str) -> list:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}/timeline"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _current_repo() -> str:
    """Resolve `OWNER/REPO` for the current cwd via `gh repo view` (cwd-based
    repo auto-detection — see the plan's Decision-defaults stance)."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _load_issues(args: argparse.Namespace) -> list:
    """Load the issue list from `--input-file` when given, else the live
    `gh` fetch. Both paths converge on the same field set (`number`,
    `title`, `state`, `labels`, plus `labeled_at`/`updatedAt`) before
    `select_orphaned` runs.
    """
    if args.input_file:
        with open(args.input_file, encoding="utf-8") as fh:
            return json.load(fh)
    return _fetch_in_progress_issues()


def _explanatory_comment(issue: dict, stale_after_hours: float, now: datetime) -> str:
    """Build the comment posted on a reclaimed issue, naming the stale
    threshold and the `labeled_at`/`updatedAt` timestamp used to judge it."""
    timestamp_raw = issue.get("labeled_at") or issue.get("updatedAt")
    return (
        f"Reclaiming this issue: it has carried `{IN_PROGRESS_LABEL}` for at "
        f"least {stale_after_hours} hour(s) (since {timestamp_raw}), past the "
        f"stale threshold as of {autoship_state.format_round_timestamp(now)}. "
        f"Relabeling to `{BLOCKED_LABEL}` so it can be triaged by a human."
    )


def _post_comment(number: int, body: str) -> None:
    subprocess.run(
        ["gh", "issue", "comment", str(number), "--body", body],
        capture_output=True,
        text=True,
        check=True,
    )


def _relabel(number: int) -> None:
    subprocess.run(
        [
            "gh",
            "issue",
            "edit",
            str(number),
            "--remove-label",
            IN_PROGRESS_LABEL,
            "--add-label",
            BLOCKED_LABEL,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _reclaim_issue(
    issue: dict, stale_after_hours: float, now: datetime, dry_run: bool
) -> int:
    """Reclaim a single orphaned `issue`: comment first, then relabel.

    This order is deliberate — if the comment call fails, the issue is left
    exactly as it was (still `autoship:in-progress`, no misleading partial
    comment), so a later reclaim run naturally re-selects and retries it via
    `select_orphaned` with no special-cased recovery path. If the comment
    succeeds but the relabel then fails, the issue also stays
    `autoship:in-progress` and is retried the same way. Returns 0 on
    success, 1 if either sub-operation fails (after printing a stderr
    message naming the issue and the failing sub-operation).
    """
    number = issue["number"]
    comment = _explanatory_comment(issue, stale_after_hours, now)

    if dry_run:
        print(
            f"would-reclaim #{number}: {IN_PROGRESS_LABEL} -> {BLOCKED_LABEL} "
            f"(comment: {comment!r})"
        )
        return 0

    try:
        _post_comment(number, comment)
    except subprocess.CalledProcessError as exc:
        print(f"failed #{number}: comment ({exc})", file=sys.stderr)
        return 1

    try:
        _relabel(number)
    except subprocess.CalledProcessError as exc:
        print(f"failed #{number}: relabel ({exc})", file=sys.stderr)
        return 1

    print(f"reclaimed #{number}")
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    now = args.now_override or datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        issues = _load_issues(args)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as exc:
        print(f"Failed to load in-progress issues via gh: {exc}", file=sys.stderr)
        return 1

    orphaned = select_orphaned(issues, args.stale_after_hours, now)

    if not orphaned:
        print("No orphaned autoship:in-progress issues found.")
        return 0

    exit_code = 0
    for issue in orphaned:
        rc = _reclaim_issue(issue, args.stale_after_hours, now, args.dry_run)
        if rc != 0:
            exit_code = rc

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
