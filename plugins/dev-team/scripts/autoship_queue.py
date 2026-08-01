#!/usr/bin/env python3
"""autoship_queue.py — deterministic dispatch-queue construction for
`/dev-team:autoship` (Slice 2).

Consumes `autoship_group.py`'s stdout shape (`{"batches": [...], "ungrouped":
[...]}`) and produces the round's ordered dispatch queue, capped by
`--max-issues`: each `batches` entry becomes a `"batch"` queue unit (backed
by every member issue number), each `ungrouped` entry becomes a `"solo"`
unit. Units are walked oldest-first — by a batch's oldest (first) member's
`createdAt`, or by the solo issue's own `createdAt` — accumulating a running
total of member-issue count. A unit is admitted into `"queue"` only if
including it does not push the running total over `--max-issues`; otherwise
it is deferred whole into `"deferred"` and the walk continues to the next
unit in order (a later, smaller unit may still fit under the same cap).

This script has no eligibility/fetch concern of its own — it is pure queue
construction over already-produced grouping output, so it never calls `gh`
and never needs `autoship_state.fetch_eligible_issues`. It reuses only
`autoship_state.positive_int_validator` for its own `--max-issues` flag.

Usage:
    autoship_group.py --input-file eligible.json | autoship_queue.py --max-issues 10
    autoship_queue.py --max-issues 10 --input-file grouping-output.json

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


class QueueError(Exception):
    """A malformed grouping-output payload (from `--input-file` or stdin)
    that must surface as a clear CLI error message, not an uncaught
    exception/traceback."""


def build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert flag values via `build_parser().parse_args([...])`
    without exercising `main()`'s file/stdin I/O."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--max-issues",
        type=autoship_state.positive_int_validator("--max-issues"),
        required=True,
        help=(
            "Maximum total member-issue count admitted into the queue this "
            "round; the rest is deferred whole. Must be > 0."
        ),
    )
    parser.add_argument(
        "--input-file",
        help=(
            "Path to a JSON object matching autoship_group.py's stdout shape "
            '({"batches": [...], "ungrouped": [...]}). Defaults to reading '
            "the same shape from stdin."
        ),
    )
    return parser


def _batch_unit(batch: dict[str, Any]) -> dict[str, Any]:
    """Convert one `autoship_group.py` batch into a queue unit.

    `members` is already oldest-first (see `autoship_group.group_issues`),
    so the first member's `createdAt`/`number` are the batch's own oldest —
    used for sort ordering below.
    """
    members = batch["members"]
    oldest = members[0]
    return {
        "type": "batch",
        "batch_id": batch["batch_id"],
        "issues": [member["number"] for member in members],
        "_created_at": oldest["createdAt"],
        "_tie_break": oldest["number"],
    }


def _solo_unit(entry: dict[str, Any]) -> dict[str, Any]:
    """Convert one `autoship_group.py` ungrouped entry into a queue unit."""
    return {
        "type": "solo",
        "issue": entry["number"],
        "_created_at": entry["createdAt"],
        "_tie_break": entry["number"],
    }


def _public_fields(unit: dict[str, Any]) -> dict[str, Any]:
    """Strip the internal sort-key fields (`_created_at`/`_tie_break`) a
    queue unit carries only for ordering, leaving the stdout contract's
    public shape."""
    return {key: value for key, value in unit.items() if not key.startswith("_")}


def build_queue(grouping_output: dict[str, Any], max_issues: int) -> dict[str, Any]:
    """Build the ordered, `max_issues`-capped dispatch queue from
    `autoship_group.py`'s output shape.

    Units are sorted oldest-first by `createdAt`; ties break on the unit's
    identifying issue number (a batch's oldest member, or the solo issue
    itself) for deterministic ordering — the same tie-break convention
    `autoship_group.group_issues` uses for its own member/batch-id ordering.

    Walks the sorted units accumulating a running member-issue count (a solo
    unit counts as 1, a batch counts as its member count). A unit is
    admitted into `"queue"` only when doing so would not push the running
    total over `max_issues`; otherwise it is deferred whole into
    `"deferred"` and the walk continues — a unit that doesn't fit does not
    stop the scan, since a later, smaller unit may still fit under the same
    cap.
    """
    units = [_batch_unit(batch) for batch in grouping_output.get("batches", [])]
    units += [_solo_unit(entry) for entry in grouping_output.get("ungrouped", [])]
    units.sort(key=lambda unit: (unit["_created_at"], unit["_tie_break"]))

    queue: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    running_total = 0
    for unit in units:
        size = len(unit["issues"]) if unit["type"] == "batch" else 1
        public = _public_fields(unit)
        if running_total + size <= max_issues:
            queue.append(public)
            running_total += size
        else:
            deferred.append(public)

    return {"queue": queue, "deferred": deferred}


def _validate_grouping_output(data: dict[str, Any]) -> None:
    """Validate `data`'s `batches`/`ungrouped` structure so `build_queue`
    never receives a payload malformed enough to trip a raw
    `KeyError`/`IndexError` in `_batch_unit`/`_solo_unit`.

    Raises `QueueError` naming the offending entry (by `batch_id` if
    present, by index otherwise; by issue `number` if present, by index
    otherwise for `ungrouped` entries) and the specific missing/malformed
    field — mirroring `autoship_state.validate_issues`'s convention.
    """
    batches = data.get("batches", [])
    if not isinstance(batches, list):
        raise QueueError(
            f'"batches" must be a JSON array, got {type(batches).__name__}'
        )
    for idx, batch in enumerate(batches):
        if not isinstance(batch, dict):
            raise QueueError(f"malformed batch at index {idx}: not a JSON object")
        identifier = (
            f"batch_id {batch['batch_id']!r}" if "batch_id" in batch else f"index {idx}"
        )
        if "batch_id" not in batch:
            raise QueueError(
                f'malformed batch ({identifier}): missing required field "batch_id"'
            )
        members = batch.get("members")
        if not isinstance(members, list) or not members:
            raise QueueError(
                f'malformed batch ({identifier}): "members" must be a non-empty '
                "JSON array"
            )
        for member_idx, member in enumerate(members):
            if not isinstance(member, dict):
                raise QueueError(
                    f"malformed batch ({identifier}): member at index "
                    f"{member_idx} is not a JSON object"
                )
            missing = [
                field for field in ("number", "createdAt") if field not in member
            ]
            if missing:
                raise QueueError(
                    f"malformed batch ({identifier}): member at index "
                    f"{member_idx} missing required field(s) {', '.join(missing)}"
                )

    ungrouped = data.get("ungrouped", [])
    if not isinstance(ungrouped, list):
        raise QueueError(
            f'"ungrouped" must be a JSON array, got {type(ungrouped).__name__}'
        )
    for idx, entry in enumerate(ungrouped):
        if not isinstance(entry, dict):
            raise QueueError(
                f"malformed ungrouped entry at index {idx}: not a JSON object"
            )
        identifier = f"#{entry['number']}" if "number" in entry else f"index {idx}"
        missing = [field for field in ("number", "createdAt") if field not in entry]
        if missing:
            raise QueueError(
                f"malformed ungrouped entry ({identifier}): missing required "
                f"field(s) {', '.join(missing)}"
            )


def _load_grouping_output(input_file: str | None) -> dict[str, Any]:
    """Read and parse the grouping-output JSON object from `input_file`
    when given, otherwise from stdin (the real pipeline's wiring: `gh` ->
    `autoship_group.py` -> `autoship_queue.py`).

    Raises `QueueError` on an unreadable file/stdin, invalid JSON, a
    non-object payload, or a malformed `batches`/`ungrouped` structure —
    never an uncaught exception.
    """
    if input_file:
        try:
            with open(input_file, encoding="utf-8") as fh:
                raw = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise QueueError(
                f"--input-file {input_file!r} could not be read: {exc}"
            ) from exc
    else:
        try:
            raw = sys.stdin.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise QueueError(
                f"grouping output could not be read from stdin: {exc}"
            ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QueueError(f"grouping output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise QueueError(
            'grouping output must be a JSON object with "batches"/"ungrouped" '
            f"keys, got {type(data).__name__}"
        )
    _validate_grouping_output(data)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        grouping_output = _load_grouping_output(args.input_file)
    except QueueError as exc:
        print(f"autoship_queue: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(build_queue(grouping_output, args.max_issues)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
