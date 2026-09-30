"""/handoff is manual only: no forced-handoff language survives (#2177, ADR 0043)."""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

HANDOFF = PLUGIN_ROOT / "skills" / "handoff" / "SKILL.md"
LOADING = PLUGIN_ROOT / "skills" / "context-loading-protocol" / "SKILL.md"

# Phrases the retired guard's bands produced; none may describe current behavior.
_FORCED = re.compile(
    r"context_ceiling|hard block|\bblocks? (?:the )?(?:skill|agent|dispatch)|"
    r"forced handoff|must hand ?off|DEV_TEAM_CONTEXT_ABS_CEILING|350K",
    re.IGNORECASE,
)


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


def test_no_forced_handoff_language_in_handoff_skill():
    assert _FORCED.search(HANDOFF.read_text(encoding="utf-8")) is None


def test_no_forced_handoff_language_in_loading_protocol_enforcement():
    text = LOADING.read_text(encoding="utf-8")
    start = text.index("## Enforcement")
    end = text.index("## Loading Decision Procedure")
    section = text[start:end]
    # The section may mention the removed hook once, to say it is gone.
    assert re.search(r"hard block|forced handoff|350K", section, re.IGNORECASE) is None
    assert "No hook blocks or warns on capability loads" in section


def test_forced_pattern_detects_a_regression():
    assert _FORCED.search("the guard will hard block the skill load")
