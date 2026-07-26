"""Downstream-service branch content-guard tests for
`cd-test-architecture/SKILL.md`. Traces to issue #1434 (sub-issue of epic
#1431) and Step 1.1 of the (transient) plan file
plans/issue-1434-cd-test-architecture-downstream-service-branch.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1434 is the durable reference once it's gone.

This file covers Step 1.1 only: the amendment to Step 1's component
inventory that records, for API Consumer / Event Consumer / Event
Producer components, whether the dependency is team-controlled or
third-party/other-team. Step 4b's new `#### Downstream-service branch`
subsection (which reads this recorded classification) does not exist yet
in this repo state — it lands in a later step of the same plan — so
assertions here are scoped to Step 1's own section only, mirroring the
sibling `test_cd_test_architecture_step4b.py`'s scoped-boundary discipline
(a boundary regex must be empirically verified reachable, not assumed —
a prior round of that file family shipped an unreachable boundary and it
was a real bug, issue #1433 round 4).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _step_1_section() -> str:
    return section(_text(), r"^### 1\.", boundary_pattern=r"^### 2\.")


# --- Boundary reachability sanity check -------------------------------------


def test_step_1_section_boundary_is_reachable():
    # Empirically verify the scoping boundary actually narrows the text —
    # not an assumption. Step 1's own heading and the Graph-assisted
    # inventory paragraph must be present; Step 2's heading and content
    # must be excluded.
    sec = _step_1_section()
    assert "### 1. Inventory the application's components" in sec
    assert "Graph-assisted inventory" in sec
    assert "### 2." not in sec
    assert "Inventory the existing tests and classify them" not in sec


# --- Step 1.1: ownership/deployability note ---------------------------------


def test_step_1_records_ownership_for_downstream_service_components():
    sec = _step_1_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)
    assert grep(r"team-controlled", sec, ignore_case=True)
    assert grep(r"third-party", sec, ignore_case=True)


def test_step_1_cites_component_test_patterns_ownership_guidance():
    sec = _step_1_section()
    assert grep(r"component-test-patterns\.md", sec)
