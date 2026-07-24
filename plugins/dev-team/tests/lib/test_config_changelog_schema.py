"""Unit tests for hooks/lib/config_changelog_schema.py (#860).

Covers the acceptance criteria from feat: eval-gate feedback-learning
mutations with change contracts:

- fixtured-agent-change-cannot-adopt-without-eval-result
- changelog-entry-carries-full-change-contract
- unfixtured-agent-change-follows-documented-fallback
- regression-blocks-adoption-absent-logged-override
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import config_changelog_schema as schema

FIXTURED = {"security-review", "arch-review"}

_FULL_GATED_ENTRY = {
    "timestamp": "2026-07-06T00:00:00Z",
    "type": "amend",
    "trigger": "system",
    "description": "Tightened XSS detection regex",
    "file_modified": "agents/security-review.md",
    "section_modified": "## Detect",
    "previous_value": "old regex",
    "new_value": "new regex",
    "approved_by": "user",
    "component": "agents/security-review.md",
    "failure_mode_targeted": "sec-xss-vulnerable flapping",
    "predicted_improvement": "sec-xss-vulnerable stops flapping; no other pair regresses",
    "eval_pre": {"passed": 20, "total": 21, "source": "baseline"},
    "eval_post": {"passed": 21, "total": 21, "transcript": ".claude/evals/transcripts/x.json"},
    "eval_verdict": "improved",
    "adoption_status": "adopted",
    "rollback_pointer": "previous_value above",
}


# ---------------------------------------------------------------------------
# extract_agent_name
# ---------------------------------------------------------------------------


def test_extract_agent_name_from_agent_file_path():
    assert schema.extract_agent_name("agents/security-review.md") == "security-review"


def test_extract_agent_name_from_agent_override_component():
    assert (
        schema.extract_agent_name("CLAUDE.md > Agent Overrides > security-review")
        == "security-review"
    )


def test_extract_agent_name_none_when_no_match():
    assert schema.extract_agent_name("CLAUDE.md > Some Other Section") is None
    assert schema.extract_agent_name("") is None


# ---------------------------------------------------------------------------
# is_gated_entry
# ---------------------------------------------------------------------------


def test_is_gated_entry_true_for_fixtured_agent():
    assert schema.is_gated_entry({"component": "agents/security-review.md"}, FIXTURED)


def test_is_gated_entry_false_for_unfixtured_agent():
    assert not schema.is_gated_entry({"component": "agents/naming-review.md"}, FIXTURED)


def test_is_gated_entry_false_when_component_missing():
    assert not schema.is_gated_entry({"description": "no component field"}, FIXTURED)


# ---------------------------------------------------------------------------
# validate_entry — legacy / non-fixtured entries always pass
# ---------------------------------------------------------------------------


def test_legacy_entry_without_component_is_valid():
    legacy_entry = {
        "timestamp": "2026-02-20T14:30:00Z",
        "type": "amend",
        "trigger": "user",
        "description": "Updated software engineer to prefer functional patterns",
        "file_modified": "CLAUDE.md",
        "section_modified": "Agent Overrides > Software Engineer",
        "previous_value": "",
        "new_value": "- Prefer functional programming patterns over OOP",
        "approved_by": "user",
    }
    assert schema.validate_entry(legacy_entry, FIXTURED) == []


def test_unfixtured_agent_change_is_valid_without_contract_fields():
    entry = {
        "component": "agents/naming-review.md",
        "description": "tweak naming rule",
    }
    assert schema.validate_entry(entry, FIXTURED) == []


# ---------------------------------------------------------------------------
# validate_entry — gated entries require the full contract
# ---------------------------------------------------------------------------


def test_full_gated_entry_is_valid():
    assert schema.validate_entry(_FULL_GATED_ENTRY, FIXTURED) == []


def test_gated_entry_missing_eval_verdict_is_rejected():
    entry = dict(_FULL_GATED_ENTRY)
    del entry["eval_verdict"]
    errors = schema.validate_entry(entry, FIXTURED)
    assert any("eval_verdict" in e for e in errors)


def test_gated_entry_missing_rollback_pointer_is_rejected():
    entry = dict(_FULL_GATED_ENTRY)
    entry["rollback_pointer"] = ""
    errors = schema.validate_entry(entry, FIXTURED)
    assert any("rollback_pointer" in e for e in errors)


def test_gated_entry_invalid_adoption_status_is_rejected():
    entry = dict(_FULL_GATED_ENTRY)
    entry["adoption_status"] = "not-a-real-status"
    errors = schema.validate_entry(entry, FIXTURED)
    assert any("adoption_status" in e for e in errors)


def test_gated_entry_invalid_eval_verdict_is_rejected():
    entry = dict(_FULL_GATED_ENTRY)
    entry["eval_verdict"] = "great"
    errors = schema.validate_entry(entry, FIXTURED)
    assert any("eval_verdict" in e for e in errors)


# ---------------------------------------------------------------------------
# regression / override handling
# ---------------------------------------------------------------------------


def test_regressed_entry_rejected_without_override_is_valid_shape():
    entry = dict(_FULL_GATED_ENTRY)
    entry["eval_verdict"] = "regressed"
    entry["adoption_status"] = "rejected"
    assert schema.validate_entry(entry, FIXTURED) == []


def test_overridden_entry_requires_rationale():
    entry = dict(_FULL_GATED_ENTRY)
    entry["eval_verdict"] = "regressed"
    entry["adoption_status"] = "overridden"
    errors = schema.validate_entry(entry, FIXTURED)
    assert any("override_rationale" in e for e in errors)


def test_overridden_entry_with_rationale_is_valid():
    entry = dict(_FULL_GATED_ENTRY)
    entry["eval_verdict"] = "regressed"
    entry["adoption_status"] = "overridden"
    entry["override_rationale"] = "bryan.finster@gmail.com: accepted minor tradeoff for perf"
    assert schema.validate_entry(entry, FIXTURED) == []
