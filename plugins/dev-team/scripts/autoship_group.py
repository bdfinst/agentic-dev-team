#!/usr/bin/env python3
"""autoship_group.py — deterministic issue grouping for `/dev-team:autoship` (Slice 1).

Groups eligible `autoship:ready` (or `--label`) issues into batches using two
native signals, via union-find:

- **Native dependency**: issue A's `blockedBy`/`blocking` field names issue B,
  and B is also in the eligible input set.
- **Shared parent**: two eligible issues name the same non-null `parent`
  issue number.

Issues with no signal at all land in `ungrouped`. This step implements only
the two signals above — the shared-label signal and the `--max-batch-size`
cap are later steps in this same slice and are not built here; the same
union-find design lets each future signal be added as its own small,
independently-testable function (see `has_dependency_edge`/
`has_shared_parent`) rather than one growing conditional.

Shares its `gh` fetch, `--input-file` schema validation, and eligibility
filter with `autoship_discover.py` via `autoship_state.fetch_eligible_issues`
— this script requests a richer field set (`blockedBy`, `blocking`, `parent`)
on top of the base required fields, and operates on the FULL eligible pool
(no `--max-issues`-style cap; that stays a downstream script's concern).

Usage:
    autoship_group.py --label autoship:ready
    autoship_group.py --label autoship:ready --input-file fixture.json

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

# The base discovery fields plus the dependency/parent fields this script's
# signals need — passed as both the `--input-file` schema requirement and
# the live `gh issue list --json` field list (via `required_fields`).
REQUIRED_ISSUE_FIELDS = autoship_state.BASE_REQUIRED_FIELDS + (
    "blockedBy",
    "blocking",
    "parent",
)


def build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert flag values via `build_parser().parse_args([...])`
    without exercising `main()`'s file/`gh` I/O."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Label marking an issue eligible for autoship (default: {DEFAULT_LABEL!r}).",
    )
    autoship_state.add_input_seam_args(parser)
    return parser


def _referenced_numbers(field: Any) -> set[int]:
    """Extract issue numbers referenced by a `blockedBy`/`blocking` field.

    Accepts either a list of issue-like dicts (each carrying a `number`) or
    a list of bare ints — the exact shape isn't pinned down yet, so this
    tolerates both rather than assuming one.
    """
    if not field:
        return set()
    numbers: set[int] = set()
    for entry in field:
        if isinstance(entry, dict):
            if "number" in entry:
                numbers.add(entry["number"])
        elif isinstance(entry, int):
            numbers.add(entry)
    return numbers


def has_dependency_edge(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when `a` and `b` name each other via `blockedBy`/`blocking`, in
    either direction.

    Only ever true when both issues are present in the same eligible input
    set passed to `group_issues` — a reference to an issue absent from that
    set (e.g. filtered out upstream as ineligible) simply never matches any
    other issue in the set, so the referencing issue naturally stays
    ungrouped rather than needing a special case here.
    """
    a_number, b_number = a["number"], b["number"]
    if b_number in _referenced_numbers(a.get("blockedBy")):
        return True
    if b_number in _referenced_numbers(a.get("blocking")):
        return True
    if a_number in _referenced_numbers(b.get("blockedBy")):
        return True
    return a_number in _referenced_numbers(b.get("blocking"))


def _parent_number(issue: dict[str, Any]) -> int | None:
    parent = issue.get("parent")
    if isinstance(parent, dict):
        return parent.get("number")
    if isinstance(parent, int):
        return parent
    return None


def has_shared_parent(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when `a` and `b` name the same non-null `parent` issue number."""
    a_parent = _parent_number(a)
    b_parent = _parent_number(b)
    return a_parent is not None and a_parent == b_parent


class _UnionFind:
    """Minimal union-find over a fixed set of keys (issue numbers)."""

    def __init__(self, keys: list[int]) -> None:
        self._parent = {key: key for key in keys}

    def find(self, key: int) -> int:
        while self._parent[key] != key:
            self._parent[key] = self._parent[self._parent[key]]
            key = self._parent[key]
        return key

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _member_view(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "createdAt": issue["createdAt"],
    }


def group_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Group `issues` into batches by native-dependency and shared-parent
    signals, via union-find.

    Returns the stdout contract shape: `{"batches": [...], "ungrouped":
    [...]}`. Each batch's `batch_id` is `grp-<oldest-member-number>`,
    derived from the oldest (by `createdAt`) member — deterministic, never
    random.
    """
    numbers = [issue["number"] for issue in issues]
    by_number = {issue["number"]: issue for issue in issues}
    union_find = _UnionFind(numbers)

    for i, a in enumerate(issues):
        for b in issues[i + 1 :]:
            if has_dependency_edge(a, b) or has_shared_parent(a, b):
                union_find.union(a["number"], b["number"])

    groups: dict[int, list[int]] = {}
    for number in numbers:
        root = union_find.find(number)
        groups.setdefault(root, []).append(number)

    batches = []
    ungrouped = []
    for members in groups.values():
        if len(members) == 1:
            ungrouped.append(_member_view(by_number[members[0]]))
            continue
        member_issues = sorted(
            (by_number[number] for number in members),
            key=lambda issue: issue["createdAt"],
        )
        batches.append(
            {
                "batch_id": f"grp-{member_issues[0]['number']}",
                "members": [_member_view(issue) for issue in member_issues],
            }
        )

    return {"batches": batches, "ungrouped": ungrouped}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        eligible = autoship_state.fetch_eligible_issues(
            args.label,
            input_file=args.input_file,
            required_fields=REQUIRED_ISSUE_FIELDS,
        )
    except autoship_state.FetchError as exc:
        print(f"autoship_group: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(group_issues(eligible)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
