"""Contract for Phase-0's relative-cost disclosure (issue #1965, epic #1958).

Knob 1 defaults to `kill-loop`, which buys the workflow's largest single cost
multiplier — an opus-tier `mutation-kill` dispatch per module batch, up to 3
rounds each. Knob 2's `bdd-runner` answer buys all of Phase 3 plus the
Phase-5 stub gate. An operator pressing Enter through the battery was
accepting both without the price ever being named, which is the opposite of
the informed-consent posture the battery already applies to knob 6's
filesystem mutation.

Disclosure only: no default, canonical token, or gate changes. These tests
pin both halves — that the cost is stated, and that nothing else moved.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import grep, grep_multiline, section
from skill_include_resolver import resolve_test_improve_text as _text


@pytest.fixture(scope="module")
def phase_0() -> str:
    s = section(_text(), r"^### Phase 0( —|$| \()")
    assert s, "Phase 0 section not found"
    return s


class TestMutationKnobDisclosure:
    def test_mutation_knob_states_relative_cost(self, phase_0):
        assert grep(r"Relative cost", phase_0)

    def test_each_of_the_three_modes_has_a_stated_cost(self, phase_0):
        assert grep_multiline(r"`off` adds none", phase_0)
        assert grep_multiline(r"`kill-loop` adds roughly one", phase_0)
        assert grep_multiline(r"`baseline\+kill-loop` adds a full mutation baseline", phase_0)

    def test_cost_is_qualitative_not_a_fabricated_figure(self, phase_0):
        """`/cost-report` is the named instrument for actuals — the prompt
        must not invent a dollar number."""
        assert grep_multiline(r"never as a fabricated dollar\s*\n?\s*figure", phase_0)
        assert grep(r"/cost-report", phase_0)

    def test_disclosure_is_not_framed_as_a_recommendation(self, phase_0):
        assert grep_multiline(r"disclosure, not a recommendation", phase_0)


class TestBddKnobDisclosure:
    def test_bdd_knob_states_relative_cost(self, phase_0):
        assert grep_multiline(r"`none` skips Phase 3 entirely", phase_0)

    def test_bdd_runner_cost_names_the_stub_gate(self, phase_0):
        assert grep_multiline(r"`bdd-runner` adds those plus parser", phase_0)
        assert grep_multiline(r"pending-stub[\s>]*gate", phase_0)


class TestNothingElseMoved:
    """Disclosure must not become a behavior change smuggled in beside it."""

    def test_mutation_default_is_still_kill_loop(self, phase_0):
        assert grep(r"\[kill-loop\]", phase_0)
        assert grep(r"kill-loop.*default|default.*kill-loop", phase_0, ignore_case=True)

    def test_bdd_default_is_still_none(self, phase_0):
        assert grep_multiline(r"\*\*Default `none`\*\*", phase_0)

    def test_canonical_mutation_tokens_are_unchanged(self, phase_0):
        for token in ("`off`", "`kill-loop`", "`baseline+kill-loop`"):
            assert token.replace("+", r"\+") or token
            assert grep(token.replace("+", r"\+"), phase_0), token

    def test_battery_is_still_six_knobs(self, phase_0):
        assert grep(r"six knobs", phase_0)
        assert not grep(r"seven knobs", phase_0)
