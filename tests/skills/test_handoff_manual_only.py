"""/handoff is manual only: no forced-handoff language survives (#2177, ADR 0043)."""

from __future__ import annotations

import re

import pytest
from skill_doc_helpers import PLUGIN_ROOT

HANDOFF = PLUGIN_ROOT / "skills" / "handoff" / "SKILL.md"
LOADING = PLUGIN_ROOT / "skills" / "context-loading-protocol" / "SKILL.md"
CONTEXT_MGMT = PLUGIN_ROOT / "docs" / "context-management.md"

# Phrases the retired guard's bands produced; none may describe current behavior.
_FORCED = re.compile(
    r"350K|DEV_TEAM_CONTEXT_ABS_CEILING|hard[- ]?block|forced[- ]hand[- ]?off|"
    r"blocks? (?:the )?(?:skill|agent|dispatch)",
    re.IGNORECASE,
)

# The one intentional mention: the doc records that the old cap was dropped.
_EXEMPT_SUBSTRING = "The former 350K cap was deliberately dropped"


def _offending_lines(path) -> list[str]:
    hits = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if _EXEMPT_SUBSTRING in line:
            continue
        if _FORCED.search(line):
            hits.append(line.strip())
    return hits


def _when_to_summarize() -> str:
    text = HANDOFF.read_text(encoding="utf-8")
    start = text.index("### When to Summarize")
    end = text.index("### Writing Summaries")
    return text[start:end]


def test_when_to_summarize_says_manual():
    section = _when_to_summarize()
    assert "`/handoff` is manual" in section
    assert "nothing forces or blocks" in section


def test_when_to_summarize_points_at_harness_autocompact():
    section = _when_to_summarize()
    assert "The harness compacts on its own" in section
    assert "/dev-team:setup" in section


@pytest.mark.parametrize("path", [HANDOFF, LOADING, CONTEXT_MGMT], ids=lambda p: p.parent.name)
def test_no_forced_handoff_language_anywhere_in_file(path):
    assert _offending_lines(path) == []


def test_loading_protocol_states_no_absolute_cap():
    text = LOADING.read_text(encoding="utf-8")
    assert "there is no absolute cap" in text
    assert "No hook blocks or warns on capability loads" in text


@pytest.mark.parametrize(
    "sample",
    [
        "capped at 350K absolute tokens",
        "raise DEV_TEAM_CONTEXT_ABS_CEILING",
        "the guard will hard block the load",
        "a hard-block at 40%",
        "hardblock",
        "a forced handoff occurs",
        "a forced-handoff occurs",
        "forced hand-off",
        "forced handoff",
        "it blocks the skill load",
        "block agent launches",
        "blocks dispatch",
    ],
)
def test_detector_flags_each_alternative(sample):
    assert _FORCED.search(sample), sample


@pytest.mark.parametrize(
    "sample",
    [
        "`/handoff` is manual: nothing forces or blocks on it.",
        "The harness compacts on its own at 40%.",
        "40% of a 1M window is 400K",
    ],
)
def test_detector_passes_clean_prose(sample):
    assert _FORCED.search(sample) is None, sample
