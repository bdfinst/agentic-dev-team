"""Contract for /test-improve Phase 5's per-module mutation-kill batching
(issue #1963, epic #1958).

`mutation-kill` is opus-tier at `effort: high`; each dispatch re-pays agent
priming plus the mutation tool's build/instrumentation warm-up. Phase 4 emits
Stories in `coverage-gap-ranking.json` rank order, so same-module Stories are
adjacent — one dispatch per Story paid that fixed cost repeatedly for a scope
that was already warm.

The batching is a *timing* change, never a coverage change: these tests pin
both halves — the batch dispatch, and the invariants that make it safe (steps
1-4 stay per-Story, the phase cannot close with an unprocessed batch, and a
single-Story module is byte-identical to the old behavior).
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import grep, grep_multiline, section
from skill_include_resolver import resolve_test_improve_text as _text


@pytest.fixture(scope="module")
def phase_5() -> str:
    s = section(_text(), r"^### Phase 5( —|$| \()")
    assert s, "Phase 5 section not found"
    return s


class TestBatchDispatch:
    def test_mutation_kill_dispatches_per_module_batch(self, phase_5):
        assert grep_multiline(r"once per module batch|per batch", phase_5)

    def test_grouping_comes_from_the_ranking_artifact_not_a_re_derivation(self, phase_5):
        """The module map already exists (Phase 2 computed it). Re-deriving
        one here would be a second, drift-prone source of truth."""
        assert grep(r"coverage-gap-ranking\.json", phase_5)
        assert grep_multiline(r"never by re-deriving a module map here", phase_5)

    def test_a_batch_is_a_contiguous_run_in_the_approved_order(self, phase_5):
        assert grep_multiline(
            r"maximal run of consecutive Stories", phase_5
        )

    def test_batch_dispatch_keeps_max_rounds_3(self, phase_5):
        assert grep(r"--max-rounds 3", phase_5)

    def test_batches_are_announced_to_the_operator(self, phase_5):
        assert grep(r"Mutation-kill batch", phase_5)


class TestGateSemanticsUnchanged:
    def test_phase_cannot_close_with_an_unprocessed_batch(self, phase_5):
        assert grep_multiline(
            r"not be reported closed with an\s*\n?\s*unprocessed batch", phase_5
        )

    def test_the_crwq_prompt_survives_and_applies_per_batch(self, phase_5):
        assert grep(r"\[c/r/w/q\]", phase_5)
        assert grep_multiline(r"\[c/r/w/q\].{0,80}applied to the batch", phase_5)

    def test_single_story_module_is_unchanged_behavior(self, phase_5):
        assert grep_multiline(
            r"single Story is a batch of one.{0,120}exactly", phase_5
        )

    def test_go_advisory_still_applies_per_batch(self, phase_5):
        assert grep_multiline(r"advisory.{0,200}per batch", phase_5)


class TestPerStoryStepsAreNotBatched:
    """Batching steps 1-4 would blunt the mid-phase coverage steering #1790
    added — the whole point of which was catching a flat streak *during* the
    phase rather than at the end."""

    def test_steps_1_to_4_remain_per_story(self, phase_5):
        assert grep_multiline(r"still run \*\*per Story\*\*", phase_5)

    def test_only_the_mutation_step_batches(self, phase_5):
        assert grep_multiline(r"Only\s*\n?\s*this step batches", phase_5)

    def test_the_steering_check_is_named_as_the_reason(self, phase_5):
        assert grep(r"#1790", phase_5)
        assert grep(r"coverage_delta_steering\.py", phase_5)
