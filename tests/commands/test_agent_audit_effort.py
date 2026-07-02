"""Tests for /agent-audit — it validates the effort vocabulary (effort:
low|medium|high in frontmatter) and warns on a legacy model: tier name,
naming the band to use.

Ported from tests/commands/agent_audit_effort_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-audit" / "SKILL.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
TEMPLATES_DIR = REPO_ROOT / "plugins" / "dev-team" / "templates" / "agents"


def test_agent_audit_validates_effort_low_medium_high() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    assert re.search(r"effort:.*low\|medium\|high", text)


def test_agent_audit_warns_on_legacy_model_tier_name() -> None:
    # The audit names the deprecated model: tier and the band to use instead.
    text = AUDIT.read_text(encoding="utf-8")
    assert re.search(r"deprecat", text, re.IGNORECASE)
    assert re.search(r"model:.*(haiku|sonnet|opus)", text, re.IGNORECASE)


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
