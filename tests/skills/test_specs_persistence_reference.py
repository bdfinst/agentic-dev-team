"""Doc-shape contract for the /specs persistence extraction (epic #2159,
prerequisite slice).

`skills/specs/SKILL.md` carried its whole persistence procedure inline —
41% of the file's words, and a leaf step with no callers above it. It now
lives in `skills/specs/references/persistence.md`, loaded on demand once
the Cross-Artifact Consistency Gate passes, matching the `references/`
progressive-disclosure convention every sibling skill of this size already
uses (`plan/references/`, `build/references/`, `test-improve/references/`).

These guards pin the three things the move must not break: the reference
carries the whole procedure, SKILL.md points at it instead of inlining it,
and the size recorded in `knowledge/agent-registry.md` still matches the
shipped file.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

from _repo_root import REPO_ROOT

SKILL = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
REFERENCE = PLUGIN_ROOT / "skills" / "specs" / "references" / "persistence.md"
REGISTRY = PLUGIN_ROOT / "knowledge" / "agent-registry.md"

# Pre-extraction size, recorded so the shrink assertion below is anchored to a
# real number rather than a moving target. Slices 2-5 add to SKILL.md; the
# cumulative guard (scripts/specs_skill_delta.py, step 1.3) is what keeps them
# from silently re-consuming the headroom this extraction bought.
PRE_EXTRACTION_WORDS = 2659


@pytest.fixture(scope="module")
def reference_text() -> str:
    return REFERENCE.read_text()


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text()


# --- the reference carries the whole procedure -----------------------------


def test_reference_file_exists():
    assert REFERENCE.is_file(), f"{REFERENCE} is missing — the extraction did not land"


@pytest.mark.parametrize(
    "pattern",
    [
        r"Classify where to persist",
        r"Persist to file",
        r"Persist to GitHub issue",
        r"Auto-trigger /plan",
    ],
)
def test_reference_carries_every_persistence_section(reference_text, pattern):
    assert grep(pattern, reference_text), f"{pattern!r} did not survive the move"


def test_reference_carries_the_body_template(reference_text):
    # The fenced template is the single source of truth for a persisted spec's
    # shape; the GitHub-issue branch cites it rather than duplicating it.
    assert "# Spec: <Feature Name>" in reference_text
    for section in (
        "## Intent Description",
        "## Acceptance Criteria",
        "## Ambiguity Log",
    ):
        assert section in reference_text, f"template lost {section!r}"


def test_reference_has_exactly_one_fenced_body_template(reference_text):
    # Guards the single-source-template pattern against a second block being
    # introduced later (slice 4 adds a Glossary row to this one, and must not
    # create a sibling to keep in sync).
    assert reference_text.count("```markdown") == 1


def test_reference_keeps_both_persistence_branches_distinguishable(reference_text):
    assert grep(r"github.*origin.*marker", collapsed(reference_text), ignore_case=True)


# --- SKILL.md points at it instead of inlining it --------------------------


def test_skill_points_at_the_reference(skill_text):
    assert "references/persistence.md" in skill_text


def test_skill_tells_the_agent_to_load_it(skill_text):
    assert grep(r"load it now", skill_text, ignore_case=True)


def test_skill_no_longer_inlines_the_body_template(skill_text):
    assert "# Spec: <Feature Name>" not in skill_text


def test_skill_no_longer_inlines_the_persistence_branching(skill_text):
    assert "Persist to GitHub issue" not in skill_text


def test_skill_shrank_measurably(skill_text):
    """A one-word trim must not satisfy this.

    The extraction moved ~41% of the file's words out, so the bar is a
    substantive reduction, not any reduction at all. 0.75 leaves room for
    slices 2-5 to add their own prose without this test becoming a second,
    weaker copy of scripts/specs_skill_delta.py's cumulative ceiling.
    """
    words = len(skill_text.split())
    ceiling = PRE_EXTRACTION_WORDS * 0.75
    assert words < ceiling, (
        f"SKILL.md is {words} words, not meaningfully below the "
        f"{PRE_EXTRACTION_WORDS}-word pre-extraction size (bar: {ceiling:.0f}) — "
        "the extraction's headroom has been consumed"
    )


# --- the recorded size stays truthful --------------------------------------


def test_agent_registry_records_the_specs_skill():
    row = [
        line
        for line in REGISTRY.read_text().splitlines()
        if "skills/specs/SKILL.md" in line
    ]
    assert len(row) == 1, "expected exactly one agent-registry row for the specs skill"


def test_agent_registry_size_has_no_measured_drift():
    """The registry figure must track the file, and only the canonical tool decides.

    An earlier version of this test approximated tokens as words * 4/3 with a
    wide tolerance. That estimator was wrong by 20% (2,209 vs. the measured
    2,765) and would have passed a stale figure, so it is gone: this repo
    already owns `scripts/measure_tokens.py`, and CLAUDE.md's
    deterministic-tools-first rule says to run the real thing rather than
    re-derive a worse one. `measure_tokens.py --verify` is also a pre-push
    gate, so this test's job is narrow — it pins that the specs row
    specifically is not DEVIATED, giving a targeted failure here instead of a
    whole-registry gate failure at push time.
    """
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "measure_tokens.py"), "--verify"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        # Non-zero means drift somewhere in the registry, not a run failure.
        # This test judges the specs row from stdout, so the exit code is not
        # the signal — a whole-registry failure is chk_registry_drift's job.
        check=False,
    )
    rows = [
        line for line in proc.stdout.splitlines() if "skills/specs/SKILL.md" in line
    ]
    assert len(rows) == 1, (
        f"expected one specs row from measure_tokens.py, got {rows!r}"
    )
    assert "DEVIATED" not in rows[0], (
        "agent-registry's recorded size for the specs skill has drifted from the "
        f"measured value — update it to the 'actual' column:\n  {rows[0].strip()}"
    )
