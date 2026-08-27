#!/usr/bin/env python3
"""autoship_proposals.py — deterministic transforms for `/dev-team:autoship`'s
Step 2b/2c agent-proposed-batch pipeline (`skills/autoship/SKILL.md`).

Three transforms were previously specified only as prose an agent had to
re-execute correctly every round (#2072). Each is mechanically checkable, so
each gets its own pure function plus a small CLI subcommand:

- ``validate-proposals`` — Step 2b's response-validation rules 1-4: discard
  any proposed issue number outside the current `ungrouped` set, discard a
  duplicate issue number (keeping only its first occurrence across
  proposals), trim an oversized proposal to its oldest `--max-batch-size`
  members (overflow returns to ungrouped — the SAME oldest-first rule
  `autoship_group.py`'s `_trim_batch` applies to deterministic batches), and
  discard any proposal left with fewer than 2 members.
- ``remove-blocked`` — Step 2c Fix A's `ungrouped`-array rewrite, PLUS the
  issue-number validation (`^[0-9]+$`) that decides which proposed batches
  were actually blockable at all: a batch containing any issue number that
  fails validation is rejected in its entirety (its members stay in
  `ungrouped`); every other batch's members are removed from `ungrouped`,
  since they were (or will be) actually labeled `autoship:blocked`.
- ``parse-marker`` — the `confirmed_batch_members` marker parse/validate:
  extract the most recent `<!-- autoship-batch-members: n1,n2,... -->`
  marker from a comment authored by the invoking identity, validate every
  value matches `^[0-9]+$`, and drop the WHOLE marker (never a partial
  list) if any value fails or no matching comment/marker exists.

Every subcommand is non-fatal on a malformed **agent response**
(`validate-proposals`'s `--agent-response-file`) — an unparseable response is
treated as zero proposals, matching Step 1 reclaim's "failure is non-fatal"
convention documented in `skills/autoship/SKILL.md`. A malformed **pipeline**
input (`--ungrouped-file`/`--batches-file`/`--comments-file` — data this
script's own upstream steps produced, not third-party agent/comment text)
still raises a clear `ProposalsError`, mirroring `autoship_queue.py`'s
`QueueError` convention.

Usage:
    autoship_proposals.py validate-proposals \\
        --agent-response-file response.json \\
        --ungrouped-file scratch-grouping.json \\
        --max-batch-size 5
    autoship_proposals.py remove-blocked \\
        --ungrouped-file scratch-grouping.json \\
        --batches-file proposed-batches.json
    autoship_proposals.py parse-marker \\
        --comments-file comments.json \\
        --invoking-login the-bot-login

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

#: Step 2c's issue-number validation regex — see `is_valid_issue_number`.
_ISSUE_NUMBER_RE = re.compile(r"^[0-9]+$")

#: The hidden marker Step 2c posts and later reads back (see `parse_marker`).
_MARKER_RE = re.compile(r"<!--\s*autoship-batch-members:\s*([0-9,\s]*)-->")


class ProposalsError(Exception):
    """A malformed pipeline input (`--ungrouped-file`/`--batches-file`/
    `--comments-file`) that must surface as a clear CLI error message, not
    an uncaught exception/traceback. Never raised for a malformed AGENT
    response — see `_load_agent_response`'s "treat as zero proposals" rule.
    """


# ---------------------------------------------------------------------------
# Shared: issue-number validation (Step 2c "Issue-number validation (security)")
# ---------------------------------------------------------------------------


def is_valid_issue_number(value: Any) -> bool:
    """True iff `value` (int or str) represents a bare non-negative integer
    matching `^[0-9]+$` — Step 2c's validation gate before any issue number
    is used in a `gh` command, a marker value, or the `ungrouped`-array
    rewrite. Rejects negative ints (`str(-5)` is `"-5"`, not all-digit),
    floats, and non-digit strings; never raises on unexpected input shapes.
    """
    if isinstance(value, bool):  # bool is an int subclass — exclude explicitly
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, str):
        return bool(_ISSUE_NUMBER_RE.match(value))
    return False


# ---------------------------------------------------------------------------
# Transform 1 — Step 2b response validation (rules 1-4)
# ---------------------------------------------------------------------------


def _load_ungrouped(data: Any) -> list[dict[str, Any]]:
    """Unwrap `<scratch-grouping.json>`'s `ungrouped` array from either a
    bare JSON array or the full `{"batches": [...], "ungrouped": [...]}`
    scratch-file shape, so callers can point either subcommand's
    `--ungrouped-file` at the whole scratch file without an extra `jq`
    step.

    Raises `ProposalsError` naming the offending entry when the shape is
    malformed (missing `number`/`createdAt`, wrong types).
    """
    if isinstance(data, dict):
        if "ungrouped" not in data:
            raise ProposalsError(
                '--ungrouped-file is a JSON object but has no "ungrouped" key'
            )
        entries = data["ungrouped"]
    else:
        entries = data

    if not isinstance(entries, list):
        raise ProposalsError(
            f'"ungrouped" must be a JSON array, got {type(entries).__name__}'
        )
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ProposalsError(
                f"malformed ungrouped entry at index {idx}: not a JSON object"
            )
        identifier = f"#{entry['number']}" if "number" in entry else f"index {idx}"
        missing = [field for field in ("number", "createdAt") if field not in entry]
        if missing:
            raise ProposalsError(
                f"malformed ungrouped entry ({identifier}): missing required "
                f"field(s) {', '.join(missing)}"
            )
    return entries


def _load_agent_response(raw: str) -> list[dict[str, Any]]:
    """Parse an agent's raw response text into its `proposals` list.

    Rule 5 (unparseable response): ANY failure here — invalid JSON, a
    non-object payload, a missing/non-list `proposals` key, or a non-list
    `issues` entry inside a proposal — returns `[]` rather than raising.
    This is deliberately lenient (never a `ProposalsError`): the agent's
    response is third-party model output, not this pipeline's own data, and
    Step 2b's doc requires treating an unparseable response as zero
    proposals, non-fatal, exactly like Step 1 reclaim's failure handling.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    proposals = data.get("proposals")
    if not isinstance(proposals, list):
        return []
    cleaned = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        issues = proposal.get("issues")
        if not isinstance(issues, list):
            continue
        cleaned.append({"rationale": proposal.get("rationale", ""), "issues": issues})
    return cleaned


def validate_proposals(
    proposals: list[dict[str, Any]],
    ungrouped: list[dict[str, Any]],
    max_batch_size: int,
) -> dict[str, Any]:
    """Apply Step 2b's response-validation rules 1-4, in order, to an
    agent's already-parsed `proposals` list against the current `ungrouped`
    pool.

    `ungrouped` is `<scratch-grouping.json>`'s own `ungrouped` array (each
    entry carrying `number`/`title`/`createdAt`) — the oldest-first trim
    (rule 3) needs `createdAt`, which a raw proposal (issue numbers only)
    does not carry.

    Returns `{"batches": [{"rationale": ..., "issues": [...]}], "ungrouped":
    [...]}` — `batches` is every proposal surviving all four rules, each
    trimmed to oldest-first member order; `ungrouped` is every entry from
    the input `ungrouped` array NOT claimed by a surviving batch, in its
    original order — Step 2b's own "issues not included in any surviving
    proposal ... remain ungrouped and proceed ... as solo dispatch units"
    rule.
    """
    by_number = {entry["number"]: entry for entry in ungrouped}
    valid_numbers = set(by_number)

    claimed: set[int] = set()
    survivors: list[dict[str, Any]] = []

    for proposal in proposals:
        # Rule 1: discard any issue number not in the current ungrouped set.
        candidates = [n for n in proposal.get("issues", []) if n in valid_numbers]
        # Rule 2: discard an issue already claimed by an earlier proposal —
        # first occurrence wins, by proposal order.
        candidates = [n for n in candidates if n not in claimed]

        if not candidates:
            continue

        # Rule 3: trim to the oldest --max-batch-size members — the SAME
        # oldest-first-trim/overflow-to-ungrouped rule autoship_group.py's
        # _trim_batch applies to deterministic batches. Overflow members are
        # simply left unclaimed here (never added to `claimed`), which is
        # what returns them to `ungrouped` below.
        member_issues = sorted(
            (by_number[n] for n in candidates),
            key=lambda issue: (issue["createdAt"], issue["number"]),
        )
        kept = member_issues[:max_batch_size]

        # Rule 4: discard any proposal with fewer than 2 members after 1-3.
        if len(kept) < 2:
            continue

        claimed.update(issue["number"] for issue in kept)
        survivors.append(
            {
                "rationale": proposal.get("rationale", ""),
                "issues": [issue["number"] for issue in kept],
            }
        )

    remaining = [entry for entry in ungrouped if entry["number"] not in claimed]
    return {"batches": survivors, "ungrouped": remaining}


# ---------------------------------------------------------------------------
# Transform 2 — Step 2c Fix A: remove blocked-batch members from ungrouped
# ---------------------------------------------------------------------------


def _load_batches(data: Any) -> list[dict[str, Any]]:
    """Validate a `--batches-file` payload: a JSON array of `{"rationale":
    ..., "issues": [...]}` objects (`validate_proposals`'s own `batches`
    output shape). Raises `ProposalsError` naming the offending entry."""
    if not isinstance(data, list):
        raise ProposalsError(
            f'"--batches-file" must be a JSON array, got {type(data).__name__}'
        )
    for idx, batch in enumerate(data):
        if not isinstance(batch, dict):
            raise ProposalsError(
                f"malformed batch at index {idx}: not a JSON object"
            )
        issues = batch.get("issues")
        if not isinstance(issues, list) or not issues:
            raise ProposalsError(
                f"malformed batch at index {idx}: \"issues\" must be a "
                "non-empty JSON array"
            )
    return data


def partition_and_filter_blocked(
    ungrouped: list[dict[str, Any]],
    batches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Split proposed `batches` into `blocked_batches` (every issue number
    passes `is_valid_issue_number`) and `rejected_batches` (any number
    fails), then remove `blocked_batches`' members from `ungrouped` — Step
    2c's Fix A rewrite, scoped to batches that were actually BLOCKED.

    A `rejected_batches` entry's members are left untouched in `ungrouped`
    — "its members MUST stay in `ungrouped` and proceed to
    `autoship_queue.py` as solo dispatch units", per the doc's security
    carve-out. `blocked_batches` is the list the skill should actually apply
    the `autoship:blocked` label/comment mutation to.
    """
    blocked_batches = []
    rejected_batches = []
    blocked_numbers: set[int] = set()

    for batch in batches:
        numbers = batch["issues"]
        if all(is_valid_issue_number(n) for n in numbers):
            blocked_batches.append(batch)
            blocked_numbers.update(numbers)
        else:
            rejected_batches.append(batch)

    remaining = [entry for entry in ungrouped if entry["number"] not in blocked_numbers]
    return {
        "blocked_batches": blocked_batches,
        "rejected_batches": rejected_batches,
        "ungrouped": remaining,
    }


# ---------------------------------------------------------------------------
# Transform 3 — confirmed_batch_members marker parse/validate
# ---------------------------------------------------------------------------


def _load_comments(data: Any) -> list[dict[str, Any]]:
    """Validate a `--comments-file` payload: a JSON array of `{"author":
    {"login": ...}, "body": ...}` objects — `gh issue view <n> --json
    comments`'s own shape. Raises `ProposalsError` naming the offending
    entry."""
    if not isinstance(data, list):
        raise ProposalsError(
            f'"--comments-file" must be a JSON array, got {type(data).__name__}'
        )
    for idx, comment in enumerate(data):
        if not isinstance(comment, dict):
            raise ProposalsError(
                f"malformed comment at index {idx}: not a JSON object"
            )
        if "body" not in comment:
            raise ProposalsError(
                f'malformed comment at index {idx}: missing required field "body"'
            )
    return data


def parse_marker(
    comments: list[dict[str, Any]], invoking_login: str
) -> list[int] | None:
    """Extract and validate the `confirmed_batch_members` marker from
    `comments`, per Step 2's "Resolving `confirmed_batch_members`" /
    "Author and value validation (security)" rules.

    Only comments whose `author.login` equals `invoking_login` are
    considered (fail-closed: an unresolvable/absent author never matches).
    Among matching comments, the LAST one (by array order — `gh issue view
    --json comments` returns oldest-first, so this is the most recent) that
    contains the `<!-- autoship-batch-members: ... -->` marker wins.

    Every parsed value must match `^[0-9]+$` (`is_valid_issue_number`); if
    ANY value fails, the WHOLE marker is dropped (never a partially-valid
    list) — returns `None`, the same "absent" outcome as no matching
    comment/marker at all.
    """
    latest_match: str | None = None
    for comment in comments:
        author = comment.get("author")
        login = author.get("login") if isinstance(author, dict) else None
        if login != invoking_login:
            continue
        match = _MARKER_RE.search(comment.get("body", ""))
        if match:
            latest_match = match.group(1)

    if latest_match is None:
        return None

    raw_values = [v.strip() for v in latest_match.split(",") if v.strip()]
    if not raw_values:
        return None
    if not all(is_valid_issue_number(v) for v in raw_values):
        return None
    return [int(v) for v in raw_values]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert flag values via `build_parser().parse_args([...])`
    without exercising `main()`'s file I/O (mirrors `autoship_group.py`'s
    `build_parser()`/`main()` split)."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-proposals",
        help="Step 2b response validation (rules 1-4) against the current ungrouped set.",
    )
    validate.add_argument(
        "--agent-response-file",
        required=True,
        help="Path to the agent's raw response text (or '-' for stdin).",
    )
    validate.add_argument(
        "--ungrouped-file",
        required=True,
        help="Path to <scratch-grouping.json> (or a bare ungrouped-array JSON file).",
    )
    validate.add_argument(
        "--max-batch-size",
        type=int,
        default=5,
        help="Oversized-proposal trim cap (default: 5, matching autoship_group.py).",
    )

    remove_blocked = subparsers.add_parser(
        "remove-blocked",
        help="Step 2c Fix A: partition batches by issue-number validity, "
        "then remove actually-blocked members from ungrouped.",
    )
    remove_blocked.add_argument(
        "--ungrouped-file",
        required=True,
        help="Path to <scratch-grouping.json> (or a bare ungrouped-array JSON file).",
    )
    remove_blocked.add_argument(
        "--batches-file",
        required=True,
        help="Path to a JSON array of proposed batches (validate-proposals's "
        '"batches" output shape).',
    )

    parse_marker_cmd = subparsers.add_parser(
        "parse-marker",
        help="Parse and validate the confirmed_batch_members marker from an "
        "issue's comments.",
    )
    parse_marker_cmd.add_argument(
        "--comments-file",
        required=True,
        help='Path to a JSON array of {"author": {"login": ...}, "body": ...} '
        "objects (gh issue view --json comments shape).",
    )
    parse_marker_cmd.add_argument(
        "--invoking-login",
        required=True,
        help="The currently-authenticated actor's login (gh api user --jq .login).",
    )

    return parser


def _read_file_or_stdin(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_json_file(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        raise ProposalsError(f"{path!r} could not be read: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProposalsError(f"{path!r} is not valid JSON: {exc}") from exc


def _run_validate_proposals(args: argparse.Namespace) -> dict[str, Any]:
    raw = _read_file_or_stdin(args.agent_response_file)
    proposals = _load_agent_response(raw)
    ungrouped = _load_ungrouped(_read_json_file(args.ungrouped_file))
    return validate_proposals(proposals, ungrouped, args.max_batch_size)


def _run_remove_blocked(args: argparse.Namespace) -> dict[str, Any]:
    ungrouped = _load_ungrouped(_read_json_file(args.ungrouped_file))
    batches = _load_batches(_read_json_file(args.batches_file))
    return partition_and_filter_blocked(ungrouped, batches)


def _run_parse_marker(args: argparse.Namespace) -> dict[str, Any]:
    comments = _load_comments(_read_json_file(args.comments_file))
    return {"confirmed_batch_members": parse_marker(comments, args.invoking_login)}


_HANDLERS = {
    "validate-proposals": _run_validate_proposals,
    "remove-blocked": _run_remove_blocked,
    "parse-marker": _run_parse_marker,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = _HANDLERS[args.command](args)
    except ProposalsError as exc:
        print(f"autoship_proposals: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
