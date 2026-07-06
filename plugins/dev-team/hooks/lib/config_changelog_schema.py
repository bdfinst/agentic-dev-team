#!/usr/bin/env python3
"""Change-contract schema validator for metrics/config-changelog.jsonl (#860).

`feedback-learning` (plugins/dev-team/skills/feedback-learning/SKILL.md §
Audit Trail) extends the config-changelog entry schema with nine change-
contract fields whenever a change touches a review agent that has eval
fixtures (`evals/expected/*.json` `applicableAgents`): `component`,
`failure_mode_targeted`, `predicted_improvement`, `eval_pre`, `eval_post`,
`eval_verdict`, `adoption_status`, `override_rationale` (required iff
`adoption_status == "overridden"`), `rollback_pointer`.

Entries that do NOT touch a fixtured agent (or predate the contract
entirely) are unaffected — the log is append-only and backward-compatible:
this validator only enforces the contract on *gated* entries (those whose
`component` names a fixtured agent), never on legacy rows.

Stdlib-only (ADR 0014/0015). Not wired into any hook's exit code — this is
a standalone validator consumed by tests and, optionally, by a human/CI
audit script. It intentionally does not decide *whether* to gate; callers
pass in the fixtured-agent set (e.g. from
`hooks/eval_compliance_check.py::_fixtured_agents`).
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

GATED_REQUIRED_FIELDS = (
    "component",
    "failure_mode_targeted",
    "predicted_improvement",
    "eval_pre",
    "eval_post",
    "eval_verdict",
    "adoption_status",
    "rollback_pointer",
)

VALID_ADOPTION_STATUSES = {
    "pending-eval",
    "adopted",
    "rejected",
    "rolled-back",
    "overridden",
}

VALID_EVAL_VERDICTS = {"improved", "unchanged", "regressed", "not-applicable"}

_AGENT_FILE_RE = re.compile(r"agents/([A-Za-z0-9_-]+)\.md")
_AGENT_OVERRIDE_RE = re.compile(r"Agent Overrides\s*>\s*([A-Za-z0-9_-]+)")


def extract_agent_name(component: str) -> Optional[str]:
    """Pull the review-agent stem out of a `component` value.

    Matches both direct plugin-repo edits (``agents/security-review.md``)
    and project-side overrides (``CLAUDE.md > Agent Overrides >
    security-review``) — the gate covers both per the spec's Ambiguity Log."""
    if not component:
        return None
    match = _AGENT_FILE_RE.search(component)
    if match:
        return match.group(1)
    match = _AGENT_OVERRIDE_RE.search(component)
    if match:
        return match.group(1)
    return None


def is_gated_entry(entry: dict, fixtured_agents: Iterable[str]) -> bool:
    """True when `entry` touches a review agent that has eval fixtures."""
    component = entry.get("component")
    if not isinstance(component, str) or not component:
        return False
    agent_name = extract_agent_name(component)
    return agent_name is not None and agent_name in set(fixtured_agents)


def validate_entry(entry: dict, fixtured_agents: Iterable[str]) -> List[str]:
    """Validate one config-changelog entry against the change-contract schema.

    Returns a list of human-readable errors (empty = valid). Entries that
    are not gated (no `component`, or a `component` naming an agent with
    no fixtures) always validate — this keeps every pre-existing entry in
    `metrics/config-changelog.jsonl` valid, per the append-only /
    backward-compatible constraint."""
    errors: List[str] = []
    fixtured: Set[str] = set(fixtured_agents)

    if not is_gated_entry(entry, fixtured):
        return errors

    for field in GATED_REQUIRED_FIELDS:
        value = entry.get(field)
        if value in (None, "", {}, []):
            errors.append(f"missing or empty required field: {field}")

    adoption_status = entry.get("adoption_status")
    if adoption_status is not None and adoption_status not in VALID_ADOPTION_STATUSES:
        errors.append(f"invalid adoption_status: {adoption_status!r}")

    eval_verdict = entry.get("eval_verdict")
    if eval_verdict is not None and eval_verdict not in VALID_EVAL_VERDICTS:
        errors.append(f"invalid eval_verdict: {eval_verdict!r}")

    if adoption_status == "overridden":
        rationale = entry.get("override_rationale")
        if not rationale:
            errors.append(
                "adoption_status is 'overridden' but override_rationale "
                "is missing or empty"
            )

    return errors
