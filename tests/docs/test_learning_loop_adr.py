"""Tests for ADR 0009 (human consent gate) and ADR 0010 (per-session
granularity).

Ported from tests/docs/learning_loop_adr_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

ADR_0009 = REPO_ROOT / "docs" / "adr" / "0009-human-consent-gate-for-learning-loop.md"
ADR_0010 = REPO_ROOT / "docs" / "adr" / "0010-per-session-analysis-granularity.md"


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    collected = []
    in_section = False
    for line in lines:
        if line.startswith(heading):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            collected.append(line)
    return "\n".join(collected)


def test_adr_0009_file_exists() -> None:
    assert ADR_0009.is_file()


def test_adr_0009_has_accepted_status_and_required_sections() -> None:
    text = ADR_0009.read_text(encoding="utf-8")
    assert re.search(r"^## Status", text, re.MULTILINE)
    assert "Accepted" in text
    assert re.search(r"^## Context", text, re.MULTILINE)
    assert re.search(r"^## Decision", text, re.MULTILINE)
    assert re.search(r"^## Consequences", text, re.MULTILINE)


def test_adr_0009_decision_contains_queued_not_auto_applied() -> None:
    text = ADR_0009.read_text(encoding="utf-8")
    decision = _section(text, "## Decision")
    assert "queued" in decision.lower()
    assert "auto-applied" not in decision.lower()


def test_adr_0010_file_exists() -> None:
    assert ADR_0010.is_file()


def test_adr_0010_has_accepted_status_and_required_sections() -> None:
    text = ADR_0010.read_text(encoding="utf-8")
    assert re.search(r"^## Status", text, re.MULTILINE)
    assert "Accepted" in text
    assert re.search(r"^## Context", text, re.MULTILINE)
    assert re.search(r"^## Decision", text, re.MULTILINE)
    assert re.search(r"^## Consequences", text, re.MULTILINE)


def test_adr_0010_decision_contains_sessionend_not_per_turn() -> None:
    text = ADR_0010.read_text(encoding="utf-8")
    decision = _section(text, "## Decision")
    assert "SessionEnd" in decision
    assert "per turn" not in decision.lower()
