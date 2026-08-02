#!/usr/bin/env python3
"""autoship_group.py — deterministic issue grouping for `/dev-team:autoship` (Slice 1).

Groups eligible `autoship:ready` (or `--label`) issues into batches using
four signals, via union-find:

- **Native dependency**: issue A's `blockedBy`/`blocking` field names issue B,
  and B is also in the eligible input set.
- **Shared parent**: two eligible issues name the same non-null `parent`
  issue number.
- **Shared label**: two eligible issues carry any label in common outside
  the `autoship:*` prefix AND outside the configured eligibility label
  itself (every eligible issue carries that label by construction — see
  `is_eligible` — so it can never be a grouping signal on its own,
  regardless of whether it happens to start with `autoship:`).
- **Confirmed-batch override** (Step 4.3): two eligible issues both carry
  `autoship:batch-confirmed` AND each one's `confirmed_batch_members` field
  names the other's issue number — see `has_batch_confirmed_override`.
  Supports partial confirmation of an agent-proposed batch (Step 2c,
  `skills/autoship/SKILL.md`): the signal only fires between two members
  that are both confirmed and both still list each other.

Issues with no signal at all land in `ungrouped`. Any batch larger than
`--max-batch-size` (default 5) is trimmed to its oldest N members; the
overflow members move to `ungrouped` rather than being dropped. The same
union-find design lets each signal be added as its own small,
independently-testable function (see `has_dependency_edge`/
`has_shared_parent`/`has_shared_label`) rather than one growing conditional.

Shares its `gh` fetch, `--input-file` schema validation, and eligibility
filter with `autoship_discover.py` via `autoship_state.fetch_eligible_issues`
— this script requests `blockedBy`/`blocking`/`parent` as `extra_fields` on
top of the base required fields, so a live `gh` call fetches them but an
`--input-file` fixture may omit them entirely (they're optional enrichment,
not required schema). Operates on the FULL eligible pool (no
`--max-issues`-style cap; that stays a downstream script's concern).

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
DEFAULT_MAX_BATCH_SIZE = 5

# Every label starting with this prefix is excluded from the shared-label
# signal — never a naming carve-out for one specific label.
_AUTOSHIP_LABEL_PREFIX = "autoship:"

# The label a human confirmation applies (Step 2c, `skills/autoship/SKILL.md`)
# — recognized by `has_batch_confirmed_override`, its own independent signal
# function, never as a carve-out inside `has_shared_label`'s exclusion rule.
BATCH_CONFIRMED_LABEL = "autoship:batch-confirmed"

# The dependency/parent fields this script's signals need, on top of
# autoship_state.BASE_REQUIRED_FIELDS. Requested as `extra_fields` (not
# `required_fields`) from `fetch_eligible_issues` — see `main()` — so they're
# fetched from a live `gh` call but stay OPTIONAL on the `--input-file` path,
# matching the plan's "no blockedBy/blocking data present" scenario.
_DEPENDENCY_FIELDS = ("blockedBy", "blocking", "parent")


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
    parser.add_argument(
        "--max-batch-size",
        type=autoship_state.positive_int_validator("--max-batch-size"),
        default=DEFAULT_MAX_BATCH_SIZE,
        help=f"Maximum members per batch; overflow moves to ungrouped (default: {DEFAULT_MAX_BATCH_SIZE}).",
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


def _non_autoship_label_names(issue: dict[str, Any], exclude_label: str) -> set[str]:
    """Label names on `issue` outside the `autoship:*` prefix AND outside
    `exclude_label`.

    `exclude_label` is the CLI's configured eligibility label (`--label`,
    not necessarily `autoship:*`-prefixed — see `build_parser`). Every
    eligible issue carries it by construction (`is_eligible` requires it),
    so without this exclusion every eligible pool would share it and
    `has_shared_label` would collapse the entire pool into one batch.

    The `autoship:*` exclusion is otherwise a plain, general rule — every
    `autoship:*` label is excluded, with no carve-out for any specific one
    (e.g. `autoship:batch-confirmed`). `has_batch_confirmed_override` (Step
    4.3) is the wholly independent signal function that recognizes
    `autoship:batch-confirmed`; this function must never special-case it.
    """
    names = set()
    for label in issue.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        if (
            name
            and name != exclude_label
            and not name.startswith(_AUTOSHIP_LABEL_PREFIX)
        ):
            names.add(name)
    return names


def has_shared_label(a_labels: set[str], b_labels: set[str]) -> bool:
    """True when `a_labels` and `b_labels` (each already filtered by
    `_non_autoship_label_names`) share any label name."""
    return bool(a_labels & b_labels)


def _raw_label_names(issue: dict[str, Any]) -> set[str]:
    """Every label name on `issue`, unfiltered (unlike
    `_non_autoship_label_names`, which excludes `autoship:*` and the
    configured eligibility label) — used by `has_batch_confirmed_override`
    to check for `autoship:batch-confirmed` itself."""
    return {
        label.get("name") if isinstance(label, dict) else label
        for label in issue.get("labels") or []
    }


def has_batch_confirmed_override(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True iff both `a` and `b` carry the `autoship:batch-confirmed` label
    AND each one's `confirmed_batch_members` field contains the other's
    issue number.

    `confirmed_batch_members` is an optional field (a list of ints, read via
    `.get(...)` — same convention as `blockedBy`/`blocking`/`parent`); its
    absence is "no signal", never an error. Requiring BOTH issues to be
    labeled AND to still cross-reference each other is what supports partial
    confirmation (Step 2c, `skills/autoship/SKILL.md`): a human confirming
    only a subset of an agent-proposed batch unions exactly that subset,
    never pulling in a member that was never relabeled or whose own marker
    no longer lists its counterpart.
    """
    if BATCH_CONFIRMED_LABEL not in _raw_label_names(a):
        return False
    if BATCH_CONFIRMED_LABEL not in _raw_label_names(b):
        return False
    a_members = set(a.get("confirmed_batch_members") or [])
    b_members = set(b.get("confirmed_batch_members") or [])
    return b["number"] in a_members and a["number"] in b_members


def _matches_any_signal(
    a: dict[str, Any],
    b: dict[str, Any],
    exclude_label: str,
    label_names_by_number: dict[int, set[str]],
) -> bool:
    """True when `a` and `b` match any grouping signal: native dependency,
    shared parent, confirmed-batch override, or a shared label (outside
    `autoship:*` and `exclude_label`).

    `label_names_by_number` is `group_issues`'s once-per-issue precomputed
    label-name lookup — passed in rather than recomputed here so the O(n^2)
    pairwise loop never re-scans an issue's label list more than once.
    """
    if has_dependency_edge(a, b):
        return True
    if has_shared_parent(a, b):
        return True
    if has_batch_confirmed_override(a, b):
        return True
    return has_shared_label(
        label_names_by_number[a["number"]], label_names_by_number[b["number"]]
    )


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


def _trim_batch(
    member_issues: list[dict[str, Any]], max_batch_size: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split `member_issues` (already sorted oldest-first) into the kept
    (oldest `max_batch_size`) and overflow (newest, beyond the cap) slices."""
    return member_issues[:max_batch_size], member_issues[max_batch_size:]


def group_issues(
    issues: list[dict[str, Any]],
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    label: str = DEFAULT_LABEL,
) -> dict[str, Any]:
    """Group `issues` into batches by native-dependency, shared-parent,
    shared-label, and confirmed-batch-override signals, via union-find.

    `label` is the CLI's configured eligibility label — excluded from the
    shared-label signal alongside the `autoship:*` prefix, since every
    eligible issue carries it by construction (see `_non_autoship_label_names`).

    A batch whose member count exceeds `max_batch_size` is trimmed to its
    oldest `max_batch_size` members; the overflow (newest) members move to
    `ungrouped` rather than being dropped. A group trimmed down to a single
    kept member is itself routed to `ungrouped` instead of emitted as a
    1-member batch — consistent with the untrimmed `len(members) == 1` case
    just below.

    Returns the stdout contract shape: `{"batches": [...], "ungrouped":
    [...]}`. Each batch's `batch_id` is `grp-<oldest-member-number>`,
    derived from the oldest (by `createdAt`, tie-broken by issue `number`)
    member of the TRIMMED batch — deterministic, never random. In practice
    this is always the same member as the pre-trim oldest: trimming keeps
    the oldest N of a sorted list, so the overall-oldest member is never the
    one trimmed away.
    """
    numbers = [issue["number"] for issue in issues]
    by_number = {issue["number"]: issue for issue in issues}
    label_names_by_number = {
        issue["number"]: _non_autoship_label_names(issue, label) for issue in issues
    }
    union_find = _UnionFind(numbers)

    for i, a in enumerate(issues):
        for b in issues[i + 1 :]:
            if _matches_any_signal(a, b, label, label_names_by_number):
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
            key=lambda issue: (issue["createdAt"], issue["number"]),
        )
        kept, overflow = _trim_batch(member_issues, max_batch_size)
        ungrouped.extend(_member_view(issue) for issue in overflow)
        if len(kept) == 1:
            ungrouped.append(_member_view(kept[0]))
            continue
        batches.append(
            {
                "batch_id": f"grp-{kept[0]['number']}",
                "members": [_member_view(issue) for issue in kept],
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
            extra_fields=_DEPENDENCY_FIELDS,
        )
    except autoship_state.FetchError as exc:
        print(f"autoship_group: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            group_issues(eligible, max_batch_size=args.max_batch_size, label=args.label)
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
