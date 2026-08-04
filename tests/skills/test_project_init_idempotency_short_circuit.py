"""#1778 — `/project-init` must short-circuit re-invocation on an
already-initialized project instead of re-running the full Steps 1-6
sequence every time.

Evidence (session-review, #1778): 119 invocations against a mid-range token
cost — a signature of repeated re-invocation rather than one heavy call.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, collapsed

PROJECT_INIT = (PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md").read_text(
    encoding="utf-8"
)


def _step_0():
    body = collapsed(PROJECT_INIT)
    section = re.search(
        r"Step 0: Idempotency short-circuit.*?(?=### Step 1|\Z)", body, flags=re.DOTALL
    )
    assert section, "expected a Step 0 idempotency section before Step 1"
    return section.group(0)


def test_step_0_reads_last_run_state_from_init_state_json():
    section = _step_0()
    assert "init-state.json" in section
    assert "last_run" in section


def test_step_0_names_the_three_short_circuit_conditions():
    section = _step_0()
    assert "capability slot bound" in section
    assert "durably declined" in section
    body = collapsed(PROJECT_INIT)
    step_6 = re.search(r"Step 6: Summary.*?(?=## Greenfield|\Z)", body, flags=re.DOTALL)
    assert "all_slots_bound" in step_6.group(0)
    assert "capability_tools_resolved" in step_6.group(0)


def test_force_flag_bypasses_the_short_circuit():
    body = collapsed(PROJECT_INIT)
    assert "--force" in body
    section = _step_0()
    assert "--force" in section


def test_step_6_actually_writes_the_last_run_snapshot():
    body = collapsed(PROJECT_INIT)
    step_6 = re.search(r"Step 6: Summary.*?(?=## Greenfield|\Z)", body, flags=re.DOTALL)
    assert step_6, "expected a Step 6: Summary section"
    assert "last_run" in step_6.group(0)
    assert "init-state.json" in step_6.group(0)


def test_short_circuit_still_runs_the_two_standing_checks():
    section = _step_0()
    assert "mcp.json" in section.lower()
    assert "graphify" in section.lower()


def test_short_circuit_condition_uses_fresh_detection_not_cached_booleans():
    section = _step_0()
    assert "re-derived from the live probes" in section or "live probes" in section
