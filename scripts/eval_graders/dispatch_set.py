"""The `dispatch_set` grader: did a coordinating agent dispatch the right agents?

For `orchestrator` and `quality-reviewer`, whose value is which agents they send
work to. The recorded `actual` lists the agent names the run dispatched, taken
from the transcript's Agent tool calls rather than from the agent's own report of
what it ran. A plugin-qualified name (`dev-team:security-review`) counts as its
bare name.

Spec fields::

    dispatch.include   agents that must be dispatched
    dispatch.exclude   agents that must not be dispatched
    dispatch.exact     true: the dispatched set must equal `include`
    statusField / expectedStatus   optional verdict check on the agent's JSON

Recorded ``actual`` shape::

    {"dispatched": ["security-review", ...], "output": {...agent JSON or null...}}
"""

from __future__ import annotations

DEFAULT_STATUS_FIELD = "status"


def bare_agent_name(name: str) -> str:
    """`dev-team:security-review` -> `security-review`."""
    return name.rsplit(":", 1)[-1].strip()


def grade_dispatch_set(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []
    dispatch = spec.get("dispatch", {})
    got = {bare_agent_name(name) for name in actual.get("dispatched", []) or []}
    include = set(dispatch.get("include", []))
    missing = sorted(include - got)
    if missing:
        fails.append(f"dispatch: expected {', '.join(missing)} to be dispatched")
    forbidden = sorted(set(dispatch.get("exclude", [])) & got)
    if forbidden:
        fails.append(f"dispatch: {', '.join(forbidden)} must not be dispatched")
    if dispatch.get("exact"):
        extra = sorted(got - include)
        if extra:
            fails.append(f"dispatch: unexpected dispatch of {', '.join(extra)}")

    if "expectedStatus" in spec:
        field = spec.get("statusField", DEFAULT_STATUS_FIELD)
        output = actual.get("output") or {}
        if output.get(field) != spec["expectedStatus"]:
            fails.append(
                f"{field}: expected {spec['expectedStatus']!r}, got {output.get(field)!r}"
            )
    return fails
