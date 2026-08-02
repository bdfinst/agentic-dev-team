#!/usr/bin/env python3
"""Reclaim issues orphaned by a crashed/interrupted /dev-team:autoship round (#989).

Relabels a stale `autoship:in-progress` issue back to `autoship:blocked` with
an explanatory comment, so a crashed or interrupted autoship round doesn't
leave an issue permanently stuck "in progress". Deterministic, testable
Python — no model judgment, per the epic's architecture rationale (see plan
`plans/issue-989-autoship-discovery-reclaim.md`, Slice 3).

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import autoship_state

IN_PROGRESS_LABEL = autoship_state.IN_PROGRESS_LABEL
BLOCKED_LABEL = autoship_state.BLOCKED_LABEL

# Stripped alongside IN_PROGRESS_LABEL on every reclaim relabel — a crashed
# batch round can leave a member `in-progress` + `batch-confirmed`; without
# also removing this label here, reclaim would produce `blocked` +
# `batch-confirmed` still co-present, violating the "autoship:blocked is
# mutually exclusive with the other two states" invariant
# (`skills/autoship/SKILL.md`) and letting a later human relabel back to
# `ready` silently re-trigger `has_batch_confirmed_override` on a stale,
# no-longer-reconfirmed marker. Defined once in `autoship_state` alongside
# the other `autoship:*` label constants; `autoship_group.py` imports the
# same shared constant.
BATCH_CONFIRMED_LABEL = autoship_state.BATCH_CONFIRMED_LABEL

# gh subprocess calls get a hard timeout so a hung/stalled network call never
# blocks this script indefinitely.
_GH_TIMEOUT_SECONDS = 30

# Required per-issue fields for --input-file, mirroring autoship_discover's
# REQUIRED_ISSUE_FIELDS/validate_issues contract so a malformed local fixture
# fails loud with a clear message instead of an uncaught AttributeError deep
# inside select_orphaned.
REQUIRED_ISSUE_FIELDS = ("number", "title", "state", "labels")


class ReclaimError(Exception):
    """A reclaim-input or `gh` fetch problem that must surface as a clear
    CLI error message, not an uncaught exception/traceback."""


def select_orphaned(issues: list, stale_after_hours: float, now: datetime) -> list:
    """Return the subset of `issues` that are orphaned in-progress issues.

    An issue qualifies when it is open, carries `autoship:in-progress`, and
    its `labeled_at` (falling back to `updatedAt` when `labeled_at` is
    absent) is stale per `autoship_state.is_stale` (inclusive boundary). The
    live-fetch path (`_fetch_in_progress_issues`/`_labeled_at_for`) always
    populates `labeled_at` before this function runs, falling back to
    `updatedAt` itself when the real timeline event can't be found.
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
    parser.add_argument(
        "--emit-actions-only",
        action="store_true",
        help=(
            "Commit to reclaiming each orphaned issue, but never call gh — "
            "print one JSON action per line to stdout instead, for a caller "
            "without a gh CLI (e.g. a cloud session) to execute via another "
            "mechanism (issue #1700). Ignored when --dry-run is also given: "
            "dry-run's 'nothing happens yet' semantics take priority."
        ),
    )
    autoship_state.add_input_seam_args(parser)
    return parser


def _fetch_in_progress_issues() -> list:
    """Fetch open `autoship:in-progress` issues via `gh issue list`, enriched
    with each one's real `labeled_at` timestamp from its GitHub timeline.

    `labels` and `state` are requested even though the live fetch is already
    server-filtered to open + `autoship:in-progress`, so the fetched shape
    matches exactly what `select_orphaned` checks — same reasoning as
    discovery's live-fetch step. `--limit 500` overrides `gh issue list`'s
    default result cap (typically 30) so a repo with more than a page of
    stale in-progress issues doesn't silently reclaim only part of them. A
    failure fetching the issue list itself
    (missing `gh` binary, non-zero exit, timeout, or malformed JSON) is
    unrecoverable and propagates to the caller, which translates it to a
    clear stderr message. A failure looking up one issue's timeline is NOT
    fatal — it falls back to that issue's own `updatedAt` (see
    `_labeled_at_for`), so one issue's timeline hiccup never aborts the
    whole run.
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
                IN_PROGRESS_LABEL,
                "--limit",
                autoship_state.GH_LIST_LIMIT,
                "--json",
                "number,title,state,labels,updatedAt",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ReclaimError(f"gh CLI not found: {exc}") from exc
    issues = json.loads(result.stdout)
    try:
        repo = _current_repo()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        json.JSONDecodeError,
    ):
        # Repo resolution failing is one more "timeline lookup hiccup" —
        # every issue falls back to its own `updatedAt` rather than
        # aborting the whole run.
        repo = None
    for issue in issues:
        issue["labeled_at"] = _labeled_at_for(issue, repo)
    return issues


def _labeled_at_for(issue: dict, repo: str | None) -> str:
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
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        json.JSONDecodeError,
    ):
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
    """Fetch the full timeline for `issue`, following pagination.

    `--paginate --slurp` is required here: the timeline endpoint returns
    events oldest-first, and `_labeled_at_for` reads the *most recent*
    matching `labeled` event (`labeled_events[-1]`) — on a busy issue with
    more activity than one page, an unpaginated fetch would silently return
    only the first page and miss the real most-recent event, understating
    staleness rather than failing loudly. `--slurp` wraps the pages into a
    JSON array-of-arrays (one array per page), which this flattens back
    into a single flat list of events.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo}/issues/{number}/timeline",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    pages = json.loads(result.stdout)
    return [event for page in pages for event in page]


def _current_repo() -> str:
    """Resolve `OWNER/REPO` for the current cwd via `gh repo view` (cwd-based
    repo auto-detection — see the plan's Decision-defaults stance)."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    return result.stdout.strip()


def validate_issues(issues) -> None:
    """Validate `issues` is a JSON array of objects each carrying every
    `REQUIRED_ISSUE_FIELDS` entry.

    Raises `ReclaimError` naming the malformed entry (by issue number if
    present, by index otherwise) rather than letting an uncaught
    `AttributeError`/`KeyError` propagate out of `select_orphaned`.
    """
    if not isinstance(issues, list):
        raise ReclaimError(
            "--input-file must contain a JSON array of issue objects, got "
            f"{type(issues).__name__}"
        )
    for idx, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise ReclaimError(
                f"malformed --input-file entry at index {idx}: not a JSON object"
            )
        missing = [field for field in REQUIRED_ISSUE_FIELDS if field not in issue]
        if missing:
            identifier = f"#{issue['number']}" if "number" in issue else f"index {idx}"
            raise ReclaimError(
                f"malformed --input-file entry ({identifier}): missing required "
                f"field(s) {', '.join(missing)}"
            )


def _load_issues(args: argparse.Namespace) -> list:
    """Load the issue list from `--input-file` when given, else the live
    `gh` fetch. Both paths converge on the same field set (`number`,
    `title`, `state`, `labels`, plus `labeled_at`/`updatedAt`) before
    `select_orphaned` runs.

    Raises `ReclaimError` on a `--input-file` read/parse/schema failure or a
    `gh`-fetch failure (missing binary, non-zero exit, timeout) — always
    with a message naming which source failed, never an uncaught traceback.
    """
    if args.input_file:
        try:
            with open(args.input_file, encoding="utf-8") as fh:
                issues = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ReclaimError(
                f"--input-file {args.input_file!r} is not valid JSON: {exc}"
            ) from exc
        except OSError as exc:
            raise ReclaimError(
                f"--input-file {args.input_file!r} could not be read: {exc}"
            ) from exc
        validate_issues(issues)
        return issues
    try:
        return _fetch_in_progress_issues()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        raise ReclaimError(f"failed to fetch in-progress issues via gh: {exc}") from exc


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
        timeout=_GH_TIMEOUT_SECONDS,
    )


def _relabel(number: int) -> None:
    """Relabel `number` from `IN_PROGRESS_LABEL` to `BLOCKED_LABEL`, also
    stripping `BATCH_CONFIRMED_LABEL` in the same operation (a no-op via
    `gh issue edit` when the label isn't present) — see `BATCH_CONFIRMED_LABEL`
    for why this must never be a bare `IN_PROGRESS_LABEL` -> `BLOCKED_LABEL`
    swap."""
    subprocess.run(
        [
            "gh",
            "issue",
            "edit",
            str(number),
            "--remove-label",
            IN_PROGRESS_LABEL,
            "--remove-label",
            BATCH_CONFIRMED_LABEL,
            "--add-label",
            BLOCKED_LABEL,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )


def _reclaim_issue(
    issue: dict,
    stale_after_hours: float,
    now: datetime,
    dry_run: bool,
    emit_actions_only: bool = False,
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

    if emit_actions_only:
        # No gh call at all — the caller (e.g. a cloud session with no gh
        # binary, per issue #1700) is committing to actually reclaim this
        # issue and executes the action itself via another mechanism (GitHub
        # MCP tools). One compact JSON object per line, so a caller can
        # stream-process without buffering the whole run's output.
        # `relabel_remove`/`relabel_add` are lists (not a single
        # `relabel_from`/`relabel_to` pair) because a reclaimed issue may
        # need more than one label stripped — see `_relabel`'s
        # `BATCH_CONFIRMED_LABEL` handling for why.
        print(
            json.dumps(
                {
                    "number": number,
                    "comment": comment,
                    "relabel_remove": [IN_PROGRESS_LABEL, BATCH_CONFIRMED_LABEL],
                    "relabel_add": [BLOCKED_LABEL],
                }
            )
        )
        return 0

    try:
        _post_comment(number, comment)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as exc:
        print(f"failed #{number}: comment ({exc})", file=sys.stderr)
        return 1

    try:
        _relabel(number)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as exc:
        print(f"failed #{number}: relabel ({exc})", file=sys.stderr)
        return 1

    print(f"reclaimed #{number}")
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.emit_actions_only and not args.input_file:
        # --emit-actions-only's whole contract is "never call gh" (issue
        # #1700's cloud-session caller has none available). Without
        # --input-file, _load_issues falls through to the live gh fetch on
        # the READ side — --emit-actions-only only ever suppressed the WRITE
        # side. Fail loudly here rather than silently degrading the promise.
        parser.error("--emit-actions-only requires --input-file (it never calls gh)")
    now = args.now_override or datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        issues = _load_issues(args)
    except ReclaimError as exc:
        print(f"autoship_reclaim: {exc}", file=sys.stderr)
        return 1

    orphaned = select_orphaned(issues, args.stale_after_hours, now)

    if not orphaned:
        # Under --emit-actions-only, stdout is a one-JSON-action-per-line
        # machine contract (see _reclaim_issue) — this notice goes to stderr
        # so a caller parsing stdout line-by-line never hits a non-JSON line
        # on the empty-round path, the most common one. --dry-run still
        # takes precedence (matching _reclaim_issue's own dry-run-wins rule):
        # its "would-reclaim" preview lines print to stdout for a non-empty
        # round, so this notice must too for an empty one, on the same
        # --dry-run --emit-actions-only combination the SKILL.md documents.
        emitting = args.emit_actions_only and not args.dry_run
        stream = sys.stderr if emitting else sys.stdout
        print("No orphaned autoship:in-progress issues found.", file=stream)
        return 0

    exit_code = 0
    for issue in orphaned:
        rc = _reclaim_issue(
            issue, args.stale_after_hours, now, args.dry_run, args.emit_actions_only
        )
        if rc != 0:
            exit_code = rc

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
