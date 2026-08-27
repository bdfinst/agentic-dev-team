"""The index trust protocol must live OUTSIDE Repowise's generated block.

`.claude/CLAUDE.md` is part hand-written, part generated: everything between
`REPOWISE:START` and `REPOWISE:END` is rewritten wholesale by `repowise init`
on every re-index.

Guidance on when *not* to re-read a `verified` file used to sit inside that
block. Repowise 0.45.0 regenerated it from a leaner template and the guidance
vanished — 52 lines deleted, silently, in a diff that looked like a routine
re-index. Nothing failed, because nothing was watching: content inside a
"do not edit below this line" region has no owner in this repo.

The fix is placement, not wording — the protocol was moved above the marker,
where a re-index cannot reach it. This test is what keeps it there. It
deliberately asserts on LOCATION rather than on the exact prose, so the
section can be reworded freely but cannot drift back under the marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CLAUDE_MD = Path(__file__).resolve().parents[2] / ".claude" / "CLAUDE.md"

START_MARKER = "<!-- REPOWISE:START"

# Substrings of the guidance that must survive a re-index. Kept short and
# behavioral so rewording the surrounding prose does not break the test.
PROTECTED_GUIDANCE = [
    "verified",
    "just to be safe",
    "_meta.stale_warning",
    "symbol_bodies",
]


@pytest.fixture(scope="module")
def parts() -> tuple[str, str]:
    """(text above the generated block, text from the marker onward)."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert text.count(START_MARKER) == 1, (
        f"expected exactly one {START_MARKER} marker in {CLAUDE_MD}"
    )
    idx = text.index(START_MARKER)
    return text[:idx], text[idx:]


def test_trust_protocol_section_exists_above_the_generated_block(
    parts: tuple[str, str],
) -> None:
    above, _ = parts
    assert "# Index trust protocol" in above, (
        "The index trust protocol heading is missing from the repo-owned region "
        "above REPOWISE:START. If a re-index removed it, restore it ABOVE the "
        "marker — not inside the generated block, which is rewritten wholesale."
    )


@pytest.mark.parametrize("phrase", PROTECTED_GUIDANCE)
def test_protected_guidance_survives_above_the_marker(
    phrase: str, parts: tuple[str, str]
) -> None:
    above, _ = parts
    assert phrase in above, (
        f"{phrase!r} is not in the repo-owned region above REPOWISE:START. "
        "This guidance must not depend on Repowise's generated block, which "
        "any re-index may rewrite without warning."
    )


def test_the_section_explains_why_its_placement_matters(
    parts: tuple[str, str],
) -> None:
    """A future editor tidying the file must be able to see the trap.

    Without the rationale in the file, moving this section back under the
    marker looks like harmless de-duplication.
    """
    above, _ = parts
    assert "REPOWISE:START" in above, (
        "The trust-protocol section must name the marker it deliberately sits "
        "above, so its placement reads as intentional rather than accidental."
    )
