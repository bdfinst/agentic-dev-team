"""#915 — /build SKILL.md must not contradict itself on when a slice's
parent checkbox may flip to `[x]`.

Sub-step 5 ("Mark step done") used to say "When every step under a slice
is `[x]`, check off the parent" with no qualifier — a literal read flips the
slice checkbox the instant the last step checkbox is checked, before
sub-steps 4.9 (verify runtime behavior) and 4.10 (run slice invariants) have
even run. Those two sub-steps independently say the slice may not be marked
`[x]` until they pass. Sub-step 5's clause must explicitly defer to both, or
the contradiction (and the risk of a plan file showing a slice "done" before
its invariants actually passed) comes back.
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

BUILD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"


@pytest.fixture(scope="module")
def build_text() -> str:
    return BUILD.read_text(encoding="utf-8")


def test_slice_checkbox_flip_defers_to_verify_and_invariants(build_text: str) -> None:
    assert (
        "sub-steps 4.9 (runtime verification) and 4.10 (invariants) both pass"
        in build_text
    )


def test_slice_checkbox_flip_no_longer_unqualified(build_text: str) -> None:
    # The pre-#915 wording flipped the parent checkbox with no gate at all.
    # If this exact unqualified sentence reappears, the contradiction is back.
    assert "is `[x]`, check off the parent `- [ ] Slice N: <title>`." not in build_text


def test_slice_checkbox_flip_bullet_gates_on_verify_and_invariants(
    build_text: str,
) -> None:
    # Co-location check: the 4.9/4.10 gate must live in the SAME bullet as the
    # checkbox-flip instruction, not just appear somewhere else in the file.
    # A passing "defers to 4.9/4.10" substring check alone wouldn't catch a
    # rewording that relocates the flip instruction away from its gate.
    matching_lines = [
        line
        for line in build_text.splitlines()
        if "check off the parent `- [ ] slice n: <title>`" in line.lower()
    ]
    assert len(matching_lines) == 1, (
        "expected exactly one bullet mentioning the Slice N checkbox flip"
    )
    bullet = matching_lines[0]
    assert "4.9" in bullet
    assert "4.10" in bullet
