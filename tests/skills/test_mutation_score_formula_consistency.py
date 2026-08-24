"""Formula-consistency content guard for the mutation-score formulas
restated across three docs (issue #1914, folded into #1940):

  - plugins/dev-team/knowledge/mutation-score-formulas.md (canonical)
  - plugins/dev-team/agents/mutation-kill.md
  - plugins/dev-team/skills/mutation-testing/SKILL.md

Nothing mechanically guarded these against drift before this test — a docs
edit to one location could silently disagree with the other two. This guard
extracts each named field's RHS expression via **line-anchored** search
(find the line starting with the field name, then walk outward to the
nearest enclosing bare ``` fence) rather than a blind whole-file regex over
every ``` fence — SKILL.md has many other fenced blocks (including ```json
examples whose closing fence is itself a bare ```` ``` ````), and a naive
``re.findall(r"```\\n(.*?)```")`` mis-pairs across them, merging the formula
block into unrelated trailing prose (confirmed while investigating
plans/mutation-testing-docs-domain-consistency-1940.md).

Plan: plans/mutation-testing-docs-domain-consistency-1940.md — Slice 1, Step 1.1.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

KNOWLEDGE_PATH = PLUGIN_ROOT / "knowledge" / "mutation-score-formulas.md"
AGENT_PATH = PLUGIN_ROOT / "agents" / "mutation-kill.md"
SKILL_PATH = PLUGIN_ROOT / "skills" / "mutation-testing" / "SKILL.md"

# Self-reference used by the negative-path tests to monkeypatch the three
# path constants above so the extraction/comparison code under test runs
# unchanged against tmp_path copies instead of the real files.
_THIS_MODULE = sys.modules[__name__]


def _extract_field_rhs(text: str, field: str, label: str) -> str:
    """Line-anchored extraction of ``field``'s RHS from a bare ``` fenced
    code block in ``text``. ``label`` names the source file, used only to
    make failure messages name the offending file.

    Finds the line that starts with ``field`` followed by ``=``, confirms it
    sits inside a *bare* fenced block (``` with no language tag — not
    ```json) by walking outward to the nearest enclosing fence in each
    direction, then returns the RHS with any trailing ``// comment`` and
    surrounding whitespace stripped.

    Raises ``AssertionError`` (never an unhandled ``IndexError`` /
    ``AttributeError``) naming ``label`` and ``field`` when the field line or
    either enclosing fence can't be found — the case exercised by the
    field-deleted negative-path test below.
    """
    lines = text.splitlines()
    field_pattern = re.compile(rf"^{re.escape(field)}\s*=")

    field_idx = None
    for i, line in enumerate(lines):
        if field_pattern.match(line.strip()):
            field_idx = i
            break
    if field_idx is None:
        raise AssertionError(f"{label}: field {field!r} not found")

    if not any(lines[j].strip() == "```" for j in range(field_idx - 1, -1, -1)):
        raise AssertionError(
            f"{label}: field {field!r} has no enclosing opening ``` fence"
        )
    if not any(lines[k].strip() == "```" for k in range(field_idx + 1, len(lines))):
        raise AssertionError(
            f"{label}: field {field!r} has no enclosing closing ``` fence"
        )

    rhs = lines[field_idx].split("=", 1)[1]
    rhs = re.sub(r"//.*$", "", rhs)
    return rhs.strip()


def _check_all_fields_consistent() -> None:
    """Run every cross-doc consistency check against the *current* values of
    the KNOWLEDGE_PATH/AGENT_PATH/SKILL_PATH module constants, read at call
    time so tests can monkeypatch them to point at tmp_path copies."""
    knowledge_text = KNOWLEDGE_PATH.read_text()
    agent_text = AGENT_PATH.read_text()
    skill_text = SKILL_PATH.read_text()

    # (knowledge-file field name, mutation-kill.md field name, SKILL.md field
    # name) — reported_score/claimed_score is a documented alias, not free to
    # drift silently.
    field_triples = [
        ("honest_score", "honest_score", "honest_score"),
        ("reported_score", "reported_score", "claimed_score"),
        ("adjusted_score", "adjusted_score", "adjusted_score"),
    ]
    for knowledge_field, agent_field, skill_field in field_triples:
        knowledge_rhs = _extract_field_rhs(
            knowledge_text, knowledge_field, "mutation-score-formulas.md"
        )
        agent_rhs = _extract_field_rhs(agent_text, agent_field, "mutation-kill.md")
        skill_rhs = _extract_field_rhs(skill_text, skill_field, "SKILL.md")
        assert knowledge_rhs == agent_rhs == skill_rhs, (
            f"formula field {knowledge_field!r} (SKILL.md: {skill_field!r}) "
            f"disagrees across docs: mutation-score-formulas.md={knowledge_rhs!r}, "
            f"mutation-kill.md={agent_rhs!r}, SKILL.md={skill_rhs!r}"
        )

    # knowledge/mutation-kill.md spell raw_score as the literal by-reference
    # string "honest_score (unchanged)" — an intentional by-reference form,
    # not a drift target. Only SKILL.md expands raw_score as a literal
    # formula, so the only meaningful check is self-consistency against
    # SKILL.md's own honest_score.
    raw_rhs = _extract_field_rhs(skill_text, "raw_score", "SKILL.md")
    honest_rhs = _extract_field_rhs(skill_text, "honest_score", "SKILL.md")
    assert raw_rhs == honest_rhs, (
        f"SKILL.md raw_score={raw_rhs!r} is not self-consistent with its own "
        f"honest_score={honest_rhs!r}"
    )


def _write_doc_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    knowledge_text: str | None = None,
    agent_text: str | None = None,
    skill_text: str | None = None,
) -> None:
    """Write tmp_path copies of the three docs (defaulting to the real,
    unmutated file contents) and monkeypatch this module's path constants to
    point at them, so `_check_all_fields_consistent()` exercises the same
    extraction/comparison code against the copies instead of the real
    files."""
    knowledge_copy = tmp_path / "mutation-score-formulas.md"
    agent_copy = tmp_path / "mutation-kill.md"
    skill_copy = tmp_path / "SKILL.md"

    knowledge_copy.write_text(
        knowledge_text if knowledge_text is not None else KNOWLEDGE_PATH.read_text()
    )
    agent_copy.write_text(
        agent_text if agent_text is not None else AGENT_PATH.read_text()
    )
    skill_copy.write_text(
        skill_text if skill_text is not None else SKILL_PATH.read_text()
    )

    monkeypatch.setattr(_THIS_MODULE, "KNOWLEDGE_PATH", knowledge_copy)
    monkeypatch.setattr(_THIS_MODULE, "AGENT_PATH", agent_copy)
    monkeypatch.setattr(_THIS_MODULE, "SKILL_PATH", skill_copy)


# =============================================================================
# Scenario: All three docs currently agree
# =============================================================================


def test_all_three_docs_agree_today():
    _check_all_fields_consistent()


def test_honest_score_identical_across_all_three_files():
    knowledge = _extract_field_rhs(
        KNOWLEDGE_PATH.read_text(), "honest_score", "mutation-score-formulas.md"
    )
    agent = _extract_field_rhs(
        AGENT_PATH.read_text(), "honest_score", "mutation-kill.md"
    )
    skill = _extract_field_rhs(SKILL_PATH.read_text(), "honest_score", "SKILL.md")
    assert knowledge == agent == skill


def test_reported_score_matches_skill_claimed_score_alias():
    knowledge = _extract_field_rhs(
        KNOWLEDGE_PATH.read_text(), "reported_score", "mutation-score-formulas.md"
    )
    agent = _extract_field_rhs(
        AGENT_PATH.read_text(), "reported_score", "mutation-kill.md"
    )
    skill = _extract_field_rhs(SKILL_PATH.read_text(), "claimed_score", "SKILL.md")
    assert knowledge == agent == skill


def test_adjusted_score_identical_across_all_three_files():
    knowledge = _extract_field_rhs(
        KNOWLEDGE_PATH.read_text(), "adjusted_score", "mutation-score-formulas.md"
    )
    agent = _extract_field_rhs(
        AGENT_PATH.read_text(), "adjusted_score", "mutation-kill.md"
    )
    skill = _extract_field_rhs(SKILL_PATH.read_text(), "adjusted_score", "SKILL.md")
    assert knowledge == agent == skill


def test_skill_raw_score_self_consistent_with_skill_honest_score():
    raw = _extract_field_rhs(SKILL_PATH.read_text(), "raw_score", "SKILL.md")
    honest = _extract_field_rhs(SKILL_PATH.read_text(), "honest_score", "SKILL.md")
    assert raw == honest


# =============================================================================
# Scenario: A formula is edited in only one location
# =============================================================================


def test_field_mutated_in_one_file_fails_naming_file_and_field(tmp_path, monkeypatch):
    original = AGENT_PATH.read_text()
    target = "adjusted_score = Killed / (Killed + (Survived - Accepted) + NoCoverage)"
    mutated = original.replace(
        target,
        "adjusted_score = killed / (Killed + (Survived - Accepted) + NoCoverage)",
    )
    assert mutated != original  # sanity: the replacement actually fired

    _write_doc_copies(tmp_path, monkeypatch, agent_text=mutated)

    with pytest.raises(AssertionError) as excinfo:
        _check_all_fields_consistent()
    message = str(excinfo.value)
    assert "mutation-kill.md" in message
    assert "adjusted_score" in message


# =============================================================================
# Scenario: A formula field is removed from one file
# =============================================================================


def test_field_deleted_from_one_file_fails_naming_missing_field(tmp_path, monkeypatch):
    original = KNOWLEDGE_PATH.read_text()
    lines = original.splitlines()
    filtered = [line for line in lines if not line.strip().startswith("honest_score")]
    assert len(filtered) == len(lines) - 1  # sanity: exactly one line removed
    mutated = "\n".join(filtered) + "\n"

    _write_doc_copies(tmp_path, monkeypatch, knowledge_text=mutated)

    with pytest.raises(AssertionError) as excinfo:
        _check_all_fields_consistent()
    message = str(excinfo.value)
    assert "mutation-score-formulas.md" in message
    assert "honest_score" in message
