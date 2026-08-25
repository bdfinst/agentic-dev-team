"""The shared context pack stays opt-in (#2023).

`review_context_pack.py` was built and wired into `/code-review` step 4 as the
default dispatch path, contradicting [ADR 0034], which had already declined a
shared-context pre-pass after measuring duplicate full-file reads at
0.38%-4.86% of a round's total input spend (median 0.8%). The justification
used a *read-volume ratio* (4.31x) — a different denominator from the one that
decision turns on. Re-measured with the repo's own
`scripts/measure_full_file_duplication.py`, the figure was 0.22%.

Nothing mechanical caught that. The ADR said in prose "a future session should
not re-open or re-attempt this fix without first reading why it was declined
here", and a future session did exactly that. This file is the mechanism that
prose wasn't: it fails if the pack drifts back to being the default, and it
fails if the reason stops being stated where someone would read it.

The pack is not being removed. It carries no known quality risk — it ships
complete file bodies, not the structural skeleton ADR 0034 warned would starve
line-level lenses. It simply has not been shown to pay for its complexity, and
#2024 tracks the >= 8-agent measurement that could change that. When it does,
this file is the thing to update — deliberately, with the number in hand.

[ADR 0034]: docs/adr/0034-do-not-build-shared-context-pre-pass-for-duplicate-full-file-reads-1611.md
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins/dev-team/skills/code-review/SKILL.md"
SCRIPT = (
    REPO_ROOT
    / "plugins/dev-team/skills/code-review/scripts/review_context_pack.py"
)
ADR_0034 = (
    REPO_ROOT
    / "docs/adr"
    / "0034-do-not-build-shared-context-pre-pass-for-duplicate-full-file-reads-1611.md"
)

#: The env var a caller sets to turn the pack on. Named here so a rename has to
#: come through this test rather than silently orphaning the opt-in.
OPT_IN_VAR = "DEV_TEAM_REVIEW_CONTEXT_PACK"


def _skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_the_pack_is_declared_opt_in_and_off_by_default() -> None:
    text = _skill()
    assert "opt-in" in text and OPT_IN_VAR in text, (
        "step 4 must name the opt-in switch; without it the pack reads as "
        "standard procedure"
    )
    assert re.search(r"off by default", text), (
        "the default posture must be stated explicitly, not left to be "
        "inferred from the absence of an instruction"
    )


def test_step_4_does_not_instruct_building_the_pack_unconditionally() -> None:
    """The original wiring opened with 'Build the shared context pack first'.
    Any imperative of that shape makes the pack the default again regardless
    of what the surrounding prose says about opting in."""
    text = _skill()
    for forbidden in (
        "Build the shared context pack first",
        "prepare the panel's file context **once** rather than",
    ):
        assert forbidden not in text, f"step 4 reverted to default-on: {forbidden!r}"


def test_the_default_context_payload_is_not_described_as_pack_served() -> None:
    """The `Context needs` bullet must describe the per-agent payload on its
    own terms. Phrasing it as 'served from the pack' makes the pack load-
    bearing for the default path even while the prose above calls it optional."""
    text = _skill()
    assert "served from the pack" not in text
    assert "**Context payload** (controlled by the agent's `Context needs`):" in text


def test_the_reason_travels_with_the_instruction() -> None:
    """A bare 'off by default' invites someone to flip it as a tidy-up. The
    ADR, the measured share-of-spend, and the denominator mistake have to be
    readable at the point of use."""
    text = _skill()
    assert "0034" in text, "step 4 must cite the ADR that declined this"
    assert "0.22%" in text or "0.8%" in text, (
        "step 4 must carry the measured share of round spend"
    )
    assert "denominator" in text or "read-volume ratio" in text, (
        "the 4.31x figure must be marked as a different measurement, or it "
        "will be cited again as justification"
    )


def test_the_script_itself_records_that_it_is_not_the_default() -> None:
    """Someone reading the module cold — a maintainer, or a future session
    grepping for the pack — must learn its status from the file, not only from
    a skill doc they may never open."""
    source = SCRIPT.read_text(encoding="utf-8")
    head = source[:2000]
    assert "OPT-IN" in head or "opt-in" in head
    assert "0034" in head, "the script must name the ADR that governs it"


def test_adr_0034_still_stands_and_is_not_silently_superseded() -> None:
    """If the >= 8-agent measurement in #2024 justifies making the pack the
    default, that is a decision reversal and needs its own ADR — the way ADR
    0037 superseded 0011's warn-default. Editing this test to pass while ADR
    0034 still reads 'Accepted' with no superseding record would be exactly
    the silent divergence #2023 is about."""
    text = ADR_0034.read_text(encoding="utf-8")
    status = text.split("## Status", 1)[1].split("##", 1)[0]
    assert "Accepted" in status
    assert "Superseded" not in status, (
        "ADR 0034 is marked superseded — update this test deliberately, "
        "citing the ADR that replaced it and the measurement behind it"
    )
