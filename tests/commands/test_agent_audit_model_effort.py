"""Tests for /agent-audit — it validates the native model:/effort: contract
(ADR 0026) via the shared contract validator, plus this repo's own
convention that every agent declares model:/effort: high.

Ported from tests/commands/agent_audit_effort_tests.bats (issue #675:
bats -> pytest); rewritten for epic #1284's native-contract migration
(issue #1290).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-audit" / "SKILL.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
TEMPLATES_DIR = REPO_ROOT / "plugins" / "dev-team" / "templates" / "agents"


def test_agent_audit_runs_the_shared_contract_validator() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    assert "scripts/validate_agent_contract.py" in text


def test_agent_audit_states_the_repo_convention_of_model_and_effort_high() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    assert re.search(r"effort: high", text)
    assert re.search(r"`model:`", text)


def test_agent_audit_no_longer_treats_model_tier_as_deprecated() -> None:
    # model: haiku|sonnet|opus is the native contract now, not a legacy tier.
    text = AUDIT.read_text(encoding="utf-8")
    assert not re.search(r"deprecat.*model:.*(haiku|sonnet|opus)", text, re.IGNORECASE | re.DOTALL)


def test_agent_audit_no_longer_keys_on_retired_model_tier_body_line() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    assert "Model tier:" not in text


def test_no_shipped_agent_body_carries_model_tier_line() -> None:
    offenders = [
        p
        for p in AGENTS_DIR.rglob("*")
        if p.is_file() and "Model tier:" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders


def test_no_shipped_agent_template_carries_model_tier_line() -> None:
    offenders = [
        p
        for p in TEMPLATES_DIR.rglob("*")
        if p.is_file() and "Model tier:" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
