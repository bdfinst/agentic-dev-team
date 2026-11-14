"""The `rubric` grader: apply the pass rule to a recorded rubric judgement.

The judging itself is a model call the A/B harness makes (a `claude -p` judge
pinned one tier above the agent under test). This grader stays model-free: it
reads the judge's recorded per-criterion verdicts and decides pass or fail, so
the pass rule lives in one deterministic place.

A trial passes only when the judge marked every criterion met: each criterion
of the agent-level rubric (`criterionIds`, supplied by the harness from the
committed rubric file) and each of the fixture's `rubricPoints`. A criterion the
judge left out counts as not met.

Recorded ``actual`` shape::

    {"criterionIds": ["contract-shape", ...],
     "judgement": {"criteria": [{"id": "...", "met": true, "reason": "..."}]}}
"""

from __future__ import annotations


def required_ids(spec: dict, actual: dict) -> list[str]:
    """The criterion IDs a trial must meet: the rubric's, then the fixture's points."""
    point_ids = [point["id"] for point in spec.get("rubricPoints", [])]
    return list(dict.fromkeys([*actual.get("criterionIds", []), *point_ids]))


def grade_rubric(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    ids = required_ids(spec, actual)
    if not ids:
        return ["rubric: no criteria to judge (empty rubric and no rubricPoints)"]
    judged = {}
    for verdict in (actual.get("judgement") or {}).get("criteria", []) or []:
        if isinstance(verdict, dict) and isinstance(verdict.get("id"), str):
            judged[verdict["id"]] = verdict
    fails = []
    for criterion_id in ids:
        verdict = judged.get(criterion_id)
        if verdict is None:
            fails.append(f"rubric: judge gave no verdict for {criterion_id!r}")
        elif verdict.get("met") is not True:
            reason = str(verdict.get("reason", "")).strip()
            fails.append(
                f"rubric: {criterion_id!r} not met" + (f" — {reason}" if reason else "")
            )
    return fails
