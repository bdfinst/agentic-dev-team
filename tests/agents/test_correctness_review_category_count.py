"""Pins the spelled-out Detect category count in correctness-review.md to the
actual number of numbered items (#1639 follow-up finding).

Adding categories 6 and 7 required updating two hardcoded "seven" mentions
(Protocol Phase 1, the Detect preamble) by hand, with nothing tying either
number to the real count of numbered items below it. A future add/remove
would have nothing but author diligence keeping them in sync — the same
"gate that cannot fail" risk this repo's own CLAUDE.md warns about — so a
stale count would silently instruct the agent to stop enumerating early.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

AGENT = (
    REPO_ROOT / "plugins" / "dev-team" / "agents" / "correctness-review.md"
)

_NUMBERED_CATEGORY_RE = re.compile(r"^\d+\. \*\*", re.MULTILINE)
_SPELLED_OUT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _detect_category_count(text: str) -> int:
    detect_section = text.split("## Detect", 1)[1].split("\n## ", 1)[0]
    return len(_NUMBERED_CATEGORY_RE.findall(detect_section))


def test_detect_preamble_count_matches_numbered_categories() -> None:
    text = _text()
    actual = _detect_category_count(text)
    match = re.search(r"looking for these (\w+) categories", text)
    assert match, "Detect preamble's category-count phrase not found"
    stated = _SPELLED_OUT.get(match.group(1).lower())
    assert stated is not None, f"unrecognized spelled-out number: {match.group(1)!r}"
    assert stated == actual, (
        f"Detect preamble says {match.group(1)!r} ({stated}) but the Detect "
        f"section has {actual} numbered categories — update the preamble"
    )


def test_protocol_phase_1_count_matches_numbered_categories() -> None:
    text = _text()
    actual = _detect_category_count(text)
    match = re.search(r"against the (\w+) Detect categories below", text)
    assert match, "Protocol Phase 1's category-count phrase not found"
    stated = _SPELLED_OUT.get(match.group(1).lower())
    assert stated is not None, f"unrecognized spelled-out number: {match.group(1)!r}"
    assert stated == actual, (
        f"Protocol Phase 1 says {match.group(1)!r} ({stated}) but the Detect "
        f"section has {actual} numbered categories — update Phase 1"
    )
