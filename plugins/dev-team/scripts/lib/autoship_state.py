"""autoship_state — shared round-state helpers for /dev-team:autoship (#989).

Shared by `autoship_discover.py`, `autoship_group.py`, and
`autoship_reclaim.py` so none has to inspect another's code to reuse common
logic: the `autoship:*` label constants scripts filter on, the
`--input-file`/`--now-override` CLI seam, the positive-value CLI validators,
and (as of the Slice 1 grouping work) the shared `gh issue list` fetch +
eligibility-filter pipeline (`fetch_eligible_issues`) that both
`autoship_discover.py` and `autoship_group.py` build on.
`is_stale`/`format_round_timestamp` are consumed only by
`autoship_reclaim.py`'s staleness check — discovery/grouping have no
staleness concept of their own.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from typing import Any

READY_LABEL = "autoship:ready"
IN_PROGRESS_LABEL = "autoship:in-progress"
BLOCKED_LABEL = "autoship:blocked"

# The label a human confirmation applies to an agent-proposed batch (Step 2c,
# `skills/autoship/SKILL.md`) — recognized by `autoship_group.py`'s
# `has_batch_confirmed_override` signal function, and stripped by
# `autoship_reclaim.py`'s reclaim relabel. Lives here, alongside the other
# three `autoship:*` label constants, so both scripts import one definition
# instead of each redefining it independently.
BATCH_CONFIRMED_LABEL = "autoship:batch-confirmed"

# `gh issue list` applies a default result cap (typically 30) — every caller
# that needs the FULL matching pool (discovery/grouping's eligible pool,
# reclaim's in-progress pool) passes this explicit override instead of each
# hardcoding its own "500" literal.
GH_LIST_LIMIT = "500"

# Same fields `gh issue list --json` returns for these names — no schema
# invention. `title` is required because `autoship_discover.py`'s stdout
# contract emits it; `state` is required because `is_eligible` checks it
# directly. Callers needing richer data (e.g. `autoship_group.py`'s
# dependency/parent signals) pass their own, larger `required_fields` tuple
# to `fetch_eligible_issues`/`validate_issues`/`load_issues_from_file`.
BASE_REQUIRED_FIELDS = (
    "number",
    "title",
    "state",
    "createdAt",
    "labels",
    "closedByPullRequestsReferences",
    "subIssuesSummary",
)

# gh subprocess calls get a hard timeout so a hung/stalled network call never
# blocks a caller script indefinitely.
_GH_TIMEOUT_SECONDS = 30


class FetchError(Exception):
    """A discovery/grouping-input or `gh` fetch problem that must surface as
    a clear CLI error message, not an uncaught exception/traceback."""


def format_round_timestamp(dt: datetime) -> str:
    """Format `dt` as an ISO-8601 UTC string ending in "Z".

    Matches the timestamp shape already used in `metrics/config-changelog.jsonl`.
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_stale(labeled_at: datetime, stale_after_hours: float, now: datetime) -> bool:
    """True when `labeled_at` is at or beyond `stale_after_hours` before `now`.

    Inclusive at the boundary: exactly `stale_after_hours` counts as stale —
    "past" in the issue's own language means "at or beyond".
    """
    elapsed_hours = (now - labeled_at).total_seconds() / 3600
    return elapsed_hours >= stale_after_hours


def _iso8601(raw: str) -> datetime:
    """`argparse` `type=` validator for an ISO-8601 timestamp string."""
    # Deliberately naive: `is_stale`'s `now` (autoship_reclaim.py) strips
    # tzinfo from its UTC clock read to match this, so both sides of the
    # subtraction stay naive-UTC. Making this tz-aware would break that pairing.
    return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")  # noqa: DTZ007


def positive_float_validator(flag_name: str):
    """Return an `argparse` `type=` validator that rejects `<= 0` for `flag_name`.

    Shared by `autoship_discover.py`'s `--max-cost-usd` and
    `autoship_reclaim.py`'s `--stale-after-hours` so both fail loud at the
    CLI boundary the same way, per `evals/code-review-benchmark/cli.py`'s
    `_positive_float` precedent — one implementation instead of two
    independently-copied ones.
    """

    def _validator(raw: str) -> float:
        value = float(raw)
        if value <= 0:
            raise argparse.ArgumentTypeError(
                f"{flag_name} must be a positive number, got {raw!r}"
            )
        return value

    return _validator


def positive_int_validator(flag_name: str):
    """Return an `argparse` `type=` validator that rejects `<= 0` for `flag_name`.

    Same shape as `positive_float_validator`, for integer-valued flags —
    shared by `autoship_discover.py`'s `--max-issues` so the CLI boundary
    fails loud the same way `--max-cost-usd` does.
    """

    def _validator(raw: str) -> int:
        value = int(raw)
        if value <= 0:
            raise argparse.ArgumentTypeError(
                f"{flag_name} must be a positive integer, got {raw!r}"
            )
        return value

    return _validator


def _label_names(issue: dict[str, Any]) -> list[str]:
    return [label["name"] for label in issue["labels"]]


def _is_epic(issue: dict[str, Any]) -> bool:
    return issue["subIssuesSummary"].get("total", 0) > 0


def _has_open_linked_pr(issue: dict[str, Any]) -> bool:
    """True when any entry in `closedByPullRequestsReferences` is itself
    still open — a single open PR anywhere in the list excludes the issue,
    even when other entries in the same list are closed/merged."""
    return any(
        pr.get("state") == "OPEN" for pr in issue["closedByPullRequestsReferences"]
    )


def is_eligible(issue: dict[str, Any], label: str) -> bool:
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
    return not _has_open_linked_pr(issue)


def _validate_shape(issue: dict[str, Any], identifier: str) -> None:
    """Validate the structural shape of `labels`, `subIssuesSummary`, and
    `closedByPullRequestsReferences` when present on `issue`.

    `is_eligible` reads these three fields structurally, not just by key
    presence: `_label_names` indexes every `labels` entry with `label["name"]`,
    `_is_epic` calls `.get("total", 0)` on `subIssuesSummary`, and
    `_has_open_linked_pr` calls `.get("state")` on every
    `closedByPullRequestsReferences` entry. A malformed `--input-file` (e.g.
    `labels` as bare strings instead of `{"name": ...}` objects) reached an
    uncaught `TypeError`/`AttributeError` deep inside `is_eligible` instead of
    a clean `FetchError` here.

    Raises `FetchError` naming `identifier` and the offending field.
    """
    if "labels" in issue:
        labels = issue["labels"]
        if not isinstance(labels, list):
            raise FetchError(
                f"malformed --input-file entry ({identifier}): field "
                f'"labels" must be a JSON array, got {type(labels).__name__}'
            )
        for label_idx, label in enumerate(labels):
            if not isinstance(label, dict) or not isinstance(label.get("name"), str):
                raise FetchError(
                    f"malformed --input-file entry ({identifier}): "
                    f'"labels[{label_idx}]" must be a JSON object with a '
                    'string "name" field'
                )

    if "subIssuesSummary" in issue:
        summary = issue["subIssuesSummary"]
        if not isinstance(summary, dict):
            raise FetchError(
                f"malformed --input-file entry ({identifier}): field "
                f'"subIssuesSummary" must be a JSON object, got '
                f"{type(summary).__name__}"
            )
        if "total" in summary and not isinstance(summary["total"], int):
            raise FetchError(
                f"malformed --input-file entry ({identifier}): field "
                f'"subIssuesSummary.total" must be a number, got '
                f"{type(summary['total']).__name__}"
            )

    if "closedByPullRequestsReferences" in issue:
        refs = issue["closedByPullRequestsReferences"]
        if not isinstance(refs, list):
            raise FetchError(
                f"malformed --input-file entry ({identifier}): field "
                '"closedByPullRequestsReferences" must be a JSON array, got '
                f"{type(refs).__name__}"
            )
        for ref_idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                raise FetchError(
                    f"malformed --input-file entry ({identifier}): "
                    f'"closedByPullRequestsReferences[{ref_idx}]" must be a '
                    "JSON object"
                )


def validate_issues(
    issues: Any, required_fields: tuple[str, ...] = BASE_REQUIRED_FIELDS
) -> None:
    """Validate `issues` is a JSON array of objects each carrying every
    `required_fields` entry, and that `labels`/`subIssuesSummary`/
    `closedByPullRequestsReferences` (when present) have the structural shape
    `is_eligible` expects (see `_validate_shape`).

    Raises `FetchError` naming the malformed entry (by issue number if
    present, by index otherwise) rather than letting a `KeyError`/`TypeError`/
    `AttributeError` propagate uncaught.
    """
    if not isinstance(issues, list):
        raise FetchError(
            "--input-file must contain a JSON array of issue objects, got "
            f"{type(issues).__name__}"
        )
    for idx, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise FetchError(
                f"malformed --input-file entry at index {idx}: not a JSON object"
            )
        identifier = f"#{issue['number']}" if "number" in issue else f"index {idx}"
        missing = [field for field in required_fields if field not in issue]
        if missing:
            raise FetchError(
                f"malformed --input-file entry ({identifier}): missing required "
                f"field(s) {', '.join(missing)}"
            )
        _validate_shape(issue, identifier)


def load_issues_from_file(
    path: str, required_fields: tuple[str, ...] = BASE_REQUIRED_FIELDS
) -> list[dict[str, Any]]:
    """Read and validate an `--input-file` JSON array of issue objects.

    Raises `FetchError` on unreadable/malformed JSON or a schema violation —
    never an uncaught exception.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            issues = json.load(fh)
    except json.JSONDecodeError as exc:
        raise FetchError(f"--input-file {path!r} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise FetchError(f"--input-file {path!r} could not be read: {exc}") from exc
    validate_issues(issues, required_fields)
    return issues


def fetch_issues_from_gh(
    label: str,
    required_fields: tuple[str, ...] = BASE_REQUIRED_FIELDS,
    extra_fields: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Fetch open issues labeled `label` via a live `gh issue list` call,
    using `gh`'s cwd-based repo auto-detection (no `--repo` flag).

    `--json` requests `required_fields` plus any `extra_fields` a caller
    needs on top of that base set (e.g. `autoship_group.py`'s dependency/
    parent fields), deduplicated while preserving order.

    The `--state open` server-side filter and the requested `state` field
    are intentionally redundant with `is_eligible`'s own `state == "OPEN"`
    check — this is what makes the `--input-file` and live paths behave
    identically.

    `--limit 500` is required here: `gh issue list` applies a default
    result cap (typically 30), and this function is documented (see
    `fetch_eligible_issues`) as returning the FULL eligible pool — without
    an explicit override that claim is false on any repo with more than a
    page of matching issues.

    Raises `FetchError` on a non-zero `gh` exit, a timeout, or malformed
    JSON output — never an uncaught
    `CalledProcessError`/`TimeoutExpired`/`JSONDecodeError`/traceback.
    """
    fields = list(required_fields)
    for field in extra_fields:
        if field not in fields:
            fields.append(field)
    gh_json_fields = ",".join(fields)

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
                "--limit",
                GH_LIST_LIMIT,
                "--json",
                gh_json_fields,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise FetchError(f"gh CLI not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError(
            f"gh issue list timed out after {_GH_TIMEOUT_SECONDS}s: {exc}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise FetchError(
            f"gh issue list failed (exit {exc.returncode}): {stderr}"
        ) from exc

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FetchError(f"gh issue list returned malformed JSON: {exc}") from exc

    validate_issues(issues, required_fields)
    return issues


def fetch_eligible_issues(
    label: str,
    extra_fields: tuple[str, ...] = (),
    input_file: str | None = None,
    required_fields: tuple[str, ...] = BASE_REQUIRED_FIELDS,
) -> list[dict[str, Any]]:
    """Return the FULL eligible pool for `label`, oldest-first by
    `createdAt` — no `--max-issues`-style truncation (that stays each
    caller's own concern, applied after this returns).

    Sources issues from `input_file` when given (bypassing the live `gh`
    call, the shared `--input-file` test seam), otherwise from a live
    `gh issue list` call requesting `required_fields` plus `extra_fields`.
    Raises `FetchError` on any fetch/validation problem (never an uncaught
    exception).
    """
    if input_file:
        issues = load_issues_from_file(input_file, required_fields)
    else:
        issues = fetch_issues_from_gh(label, required_fields, extra_fields)

    eligible = [issue for issue in issues if is_eligible(issue, label)]
    eligible.sort(key=lambda issue: issue["createdAt"])
    return eligible


def add_input_seam_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared `--input-file`/`--now-override` test seam to `parser`.

    Both flags are optional at this shared level; each caller decides its
    own default file-source behavior. `--input-file` lets a caller skip its
    live `gh` fetch entirely (JSON array of issue objects); `--now-override`
    feeds `is_stale` an explicit "now" instead of the real clock.
    """
    parser.add_argument(
        "--input-file",
        help="Path to a JSON array of issue objects, bypassing the live gh fetch.",
    )
    parser.add_argument(
        "--now-override",
        type=_iso8601,
        help="ISO-8601 UTC timestamp (e.g. 2026-07-08T12:00:00Z) to use as 'now'.",
    )
