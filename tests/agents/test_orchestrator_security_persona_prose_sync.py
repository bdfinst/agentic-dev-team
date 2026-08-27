"""Content-guard: orchestrator.py's SECURITY_KEYWORDS / PLAN_CORE_PERSONAS /
CRITICS_SKIPPED_ALL_CORE_FAILED constants must stay in sync with the prose
that restates them in knowledge/orchestrator-script-implementation.md (the
script-behavior companion doc `agents/orchestrator.md`'s phase table points
at for each phase — see its "Security Engineer dispatch — script
approximation" and "Plan persona roster" sections).

Two comments in orchestrator.py (near SECURITY_KEYWORDS and
PLAN_CORE_PERSONAS) used to point at follow-up #1716 for this guard; #1716
closed without it (its own 5 enumerated items didn't include it), so this
test — tracked against #2067 — is the guard those comments now name.

No prior test mechanically bound the code constants to this prose: a future
edit to either side could silently drift the other out of sync. This test
parses both and asserts set-equality, not just substring presence, so an
accidental drop (or accidental addition) on either side fails CI.
"""

from __future__ import annotations

import re
import sys

import skill_doc_helpers

from _repo_root import REPO_ROOT

SCRIPTS = REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import orchestrator as orch

DOC = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "orchestrator-script-implementation.md"


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _backtick_tokens(text: str) -> list[str]:
    """Every `backtick-quoted` token in `text`, in order."""
    return re.findall(r"`([^`]+)`", text)


def _security_engineer_dispatch_section(text: str) -> str:
    return skill_doc_helpers.collapsed(
        skill_doc_helpers.section(
            text,
            r"^### Security Engineer dispatch",
            boundary_pattern=r"^## ",
        )
    )


def _plan_persona_roster_section(text: str) -> str:
    return skill_doc_helpers.collapsed(
        skill_doc_helpers.section(
            text,
            r"^### Plan persona roster",
            boundary_pattern=r"^## ",
        )
    )


def _prose_security_keywords(text: str) -> set[str]:
    section = _security_engineer_dispatch_section(text)
    match = re.search(r"`SECURITY_KEYWORDS`\s*\(([^)]*)\)", section)
    assert match, f"SECURITY_KEYWORDS restatement not found in: {section!r}"
    return set(_backtick_tokens(match.group(1)))


def _prose_plan_core_personas(text: str) -> set[str]:
    section = _plan_persona_roster_section(text)
    match = re.search(r"core trio ((?:`[^`]+`,?\s*)+)\(`PLAN_CORE_PERSONAS`\)", section)
    assert match, f"PLAN_CORE_PERSONAS restatement not found in: {section!r}"
    return set(_backtick_tokens(match.group(1)))


def _prose_critics_skipped_sentinel(text: str) -> str:
    section = _plan_persona_roster_section(text)
    match = re.search(r'critics_skipped_reason:\s*"([^"]+)"', section)
    assert match, f"critics_skipped_reason restatement not found in: {section!r}"
    return match.group(1)


def test_prose_security_keywords_match_the_code_constant() -> None:
    assert _prose_security_keywords(_doc_text()) == set(orch.SECURITY_KEYWORDS)


def test_prose_security_keywords_cardinality_matches() -> None:
    """Set-equality alone wouldn't catch an accidental duplicate entry on
    either side (SECURITY_KEYWORDS has no duplicates, so a doc or code
    regression that introduced one would otherwise pass silently)."""
    prose_list = _backtick_tokens(
        re.search(
            r"`SECURITY_KEYWORDS`\s*\(([^)]*)\)",
            _security_engineer_dispatch_section(_doc_text()),
        ).group(1)
    )
    assert len(prose_list) == len(orch.SECURITY_KEYWORDS)


def test_prose_plan_core_personas_match_the_code_constant() -> None:
    assert _prose_plan_core_personas(_doc_text()) == set(orch.PLAN_CORE_PERSONAS)


def test_prose_plan_core_personas_cardinality_matches() -> None:
    prose_list = _backtick_tokens(
        re.search(
            r"core trio ((?:`[^`]+`,?\s*)+)\(`PLAN_CORE_PERSONAS`\)",
            _plan_persona_roster_section(_doc_text()),
        ).group(1)
    )
    assert len(prose_list) == len(orch.PLAN_CORE_PERSONAS)


def test_prose_critics_skipped_sentinel_matches_the_code_constant() -> None:
    assert _prose_critics_skipped_sentinel(_doc_text()) == orch.CRITICS_SKIPPED_ALL_CORE_FAILED
