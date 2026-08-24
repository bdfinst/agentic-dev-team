"""Contract for `/test-health --no-mutation` and its `/test-improve` caller
(issue #1961, epic #1958).

Before this flag, `/test-health` Step 5 invoked `mutation-testing`
unconditionally and `/test-improve` Phase 1 filtered only the *report
section* when the run's Phase-0 mutation mode was `off` — so an operator who
chose the lightweight mode still paid for a mutation tool run whose output
was then discarded. The flag makes the skip real, and the Phase-1 caller
threads it on exactly the one mode where nothing downstream consumes the
result.

Content-guard tests over the shipped prose, matching the pattern in
test_test_health_gherkin_signal.py.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section
from skill_include_resolver import resolve_test_improve_text

TEST_HEALTH = PLUGIN_ROOT / "skills" / "test-health" / "SKILL.md"


@pytest.fixture(scope="module")
def health() -> str:
    return TEST_HEALTH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def phase_1() -> str:
    s = section(resolve_test_improve_text(), r"^### Phase 1( —|$| \()")
    assert s, "Phase 1 section not found in the resolved /test-improve text"
    return s


class TestTestHealthFlagSurface:
    def test_argument_hint_declares_the_flag(self, health):
        hint = section(health, r"^argument-hint:")
        assert grep(r"--no-mutation", hint or health)

    def test_parse_arguments_documents_the_flag(self, health):
        args = section(health, r"^## Parse Arguments")
        assert args, "Parse Arguments section not found"
        assert grep(r"--no-mutation", args)

    def test_flag_defaults_off_so_standalone_runs_are_unchanged(self, health):
        """The standalone strategic audit still measures mutation ROI — the
        flag is opt-in for a caller that has already scoped mutation out."""
        args = section(health, r"^## Parse Arguments")
        assert grep_multiline(
            r"--no-mutation.{0,600}[Dd]efault\s+\*\*off\*\*", args
        )

    def test_a_skip_is_distinguished_from_a_waiver(self, health):
        args = section(health, r"^## Parse Arguments")
        assert grep_multiline(r"skip is \*\*not\*\* a waiver|not a waiver", args)


class TestTestHealthStep5Honors:
    def test_step_5_skips_the_mutation_invocation_under_the_flag(self, health):
        step_5 = section(health, r"^### 5\. Test-design \+ mutation health")
        assert step_5, "Step 5 section not found"
        assert grep(r"--no-mutation", step_5)
        assert grep_multiline(
            r"--no-mutation.{0,200}(skips|do not run)", step_5, ignore_case=True
        )

    def test_step_5_forbids_substituting_an_estimated_figure(self, health):
        """A skipped measurement must not be replaced by a guess — the same
        never-estimate rule the mutation tooling carries everywhere else."""
        step_5 = section(health, r"^### 5\. Test-design \+ mutation health")
        assert grep_multiline(
            r"do not estimate|never a number", step_5, ignore_case=True
        )

    def test_step_5_keeps_test_design_running_under_the_flag(self, health):
        """Only the mutation sub-run is gated; `/test-design` is unaffected."""
        step_5 = section(health, r"^### 5\. Test-design \+ mutation health")
        assert grep_multiline(
            r"--no-mutation.{0,600}/test-design`? still runs", step_5
        )


class TestTestImprovePhase1ThreadsIt:
    def test_off_mode_invokes_test_health_with_the_flag(self, phase_1):
        assert grep(r"/test-health --no-mutation", phase_1)

    def test_non_off_modes_invoke_test_health_without_a_mutation_flag(self, phase_1):
        assert grep_multiline(
            r"`kill-loop`.{0,200}no\s*\n?\s*mutation flag|"
            r"`baseline\+kill-loop`.{0,200}no mutation flag",
            phase_1,
        )

    def test_phase_1_states_the_skipped_measurement_had_no_consumer(self, phase_1):
        """The justification is the load-bearing part: `off` also means no
        Phase-5 kill loop, so nothing downstream reads survivor ordering."""
        assert grep_multiline(
            r"no consumer.{0,200}Phase-5 kill loop|"
            r"Phase-5 kill loop will consume survivor ordering",
            phase_1,
        )
