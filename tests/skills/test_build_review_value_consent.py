"""Content-guard: review-value.jsonl is gated by telemetry consent and
relocated under .claude/metrics/; verify-log.jsonl stays unconditional and
unrelocated (#1405/#1406 combined plan, Slice 3 Step 3.1).

`review-value.jsonl` is written entirely via build/SKILL.md's agent
instructions — there is no Python write call site to gate. Two independent
prose occurrences name it: the Orchestrator constraints overview list's
item 5, and sub-step 7's "Record review value" paragraph. Both must (a)
require checking ~/.claude/telemetry.json consent, layered under the
existing DEV_TEAM_REVIEW_VALUE=off opt-out, and (b) target the relocated
path .claude/metrics/review-value.jsonl, never the bare
metrics/review-value.jsonl path.

verify-log.jsonl is exempt from all of this (AC3) — sub-step 4.9's
"Verify runtime behavior" paragraph must remain untouched: no consent
check, still the bare metrics/verify-log.jsonl path.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

BUILD_SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"


def _text() -> str:
    return BUILD_SKILL.read_text()


def _orchestrator_constraints_item_5() -> str:
    constraints = section(
        _text(),
        r"^## Orchestrator constraints",
        boundary_pattern=r"^## Parse Arguments",
        include_start_line=False,
    )
    match = re.search(
        r"(?ms)^5\. \*\*Review checkpoints.*?(?=^\d+\. \*\*|\Z)", constraints
    )
    assert match, "could not locate Orchestrator constraints item 5"
    return match.group(0)


def _sub_step_7_review_value() -> str:
    step4 = section(
        _text(),
        r"^### 4\. Implement each step",
        boundary_pattern=r"^### 4\.9\. ",
        include_start_line=False,
    )
    match = re.search(
        r"(?ms)^7\. \*\*Record review value.*\Z", step4
    )
    assert match, "could not locate sub-step 7's review-value paragraph"
    return match.group(0)


def _verify_runtime_behavior_section() -> str:
    return section(
        _text(),
        r"^### 4\.9\. Verify runtime behavior",
        boundary_pattern=r"^### 4\.10\. ",
        include_start_line=False,
    )


# --- Orchestrator constraints item 5 -----------------------------------


def test_constraints_item_5_requires_telemetry_consent_check():
    item = _orchestrator_constraints_item_5()
    assert grep(r"~/\.claude/telemetry\.json", item)


def test_constraints_item_5_targets_relocated_review_value_path():
    item = _orchestrator_constraints_item_5()
    assert grep(r"\.claude/metrics/review-value\.jsonl", item)
    # No bare (un-relocated) reference should remain once the relocated
    # form is stripped out.
    assert "metrics/review-value.jsonl" not in item.replace(
        ".claude/metrics/review-value.jsonl", ""
    )


# --- Sub-step 7's "Record review value" paragraph ----------------------


def test_sub_step_7_requires_telemetry_consent_check():
    para = _sub_step_7_review_value()
    assert grep(r"~/\.claude/telemetry\.json", para)


def test_sub_step_7_targets_relocated_review_value_path():
    para = _sub_step_7_review_value()
    assert grep(r"\.claude/metrics/review-value\.jsonl", para)
    assert "metrics/review-value.jsonl" not in para.replace(
        ".claude/metrics/review-value.jsonl", ""
    )


def test_sub_step_7_keeps_existing_opt_out_env_var():
    para = _sub_step_7_review_value()
    assert grep(r"DEV_TEAM_REVIEW_VALUE=off", para)


# --- verify-log.jsonl stays exempt (AC3) --------------------------------


def test_verify_log_paragraph_has_no_consent_check():
    section_text = _verify_runtime_behavior_section()
    assert "~/.claude/telemetry.json" not in section_text


def test_verify_log_paragraph_stays_at_bare_unrelocated_path():
    section_text = _verify_runtime_behavior_section()
    assert grep(r"metrics/verify-log\.jsonl", section_text)
    assert ".claude/metrics/verify-log.jsonl" not in section_text
