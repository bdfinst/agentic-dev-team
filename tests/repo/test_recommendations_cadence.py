"""#813 — Code-First Small Batches is the default build cadence.

Rec 3/4 (`docs/experiments/RECOMMENDATIONS.md`): one agent per unit of work
implements one behavior, writes its test, keeps the suite green, refactors on
every green — never deferring or skipping the refactor. Classic TDD stays as
an explicit opt-in with its RED hard gate. Tests are frozen during REFACTOR,
enforced mechanically via the phase state `/build` records.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

BUILD = (PLUGIN_ROOT / "skills" / "build" / "SKILL.md").read_text()
IMPLEMENTER = (PLUGIN_ROOT / "prompts" / "implementer.md").read_text()
PLAN = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text()
PLAN_TEMPLATE = (
    PLUGIN_ROOT / "skills" / "plan" / "references" / "plan-template.md"
).read_text()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TestBuildDefaultCadence:
    def test_default_is_code_first_small_batches_citing_recommendations(self) -> None:
        assert "Code-First Small Batches" in BUILD
        assert "docs/experiments/RECOMMENDATIONS.md" in BUILD

    def test_default_cycle_is_implement_test_refactor(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"IMPLEMENT\s*(→|->)\s*TEST\s*(→|->)\s*REFACTOR", flat)

    def test_suite_green_with_pasted_evidence_gates_the_refactor(self) -> None:
        flat = _flat(BUILD)
        assert re.search(
            r"(full suite|all tests).{0,120}(pasted|paste)", flat, re.IGNORECASE
        )

    def test_classic_tdd_is_an_explicit_opt_in_with_its_red_hard_gate(self) -> None:
        assert "--tdd" in BUILD
        flat = _flat(BUILD)
        assert re.search(r"RED\s*(→|->)\s*GREEN\s*(→|->)\s*REFACTOR", flat)
        assert re.search(r"hard gate.{0,200}fail", flat, re.IGNORECASE) or re.search(
            r"fail.{0,200}hard gate", flat, re.IGNORECASE
        )

    def test_cadence_metadata_and_cli_precedence(self) -> None:
        assert "**Cadence**" in BUILD
        flat = _flat(BUILD)
        assert re.search(r"(CLI |--tdd )?flag wins|CLI-over-metadata", flat, re.IGNORECASE)

    def test_resolved_cadence_is_printed_at_build_start(self) -> None:
        flat = _flat(BUILD)
        assert re.search(
            r"resolved cadence.{0,120}(print|state|announc)", flat, re.IGNORECASE
        ) or re.search(
            r"(print|state|announc).{0,120}resolved cadence", flat, re.IGNORECASE
        )

    def test_legacy_plans_are_inferred_not_silently_switched(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"RED/GREEN.{0,200}(infer|tdd)", flat, re.IGNORECASE)
        assert re.search(
            r"(state|print|announc)\w*\s(the\s)?inference.{0,120}build output",
            flat,
            re.IGNORECASE,
        ), "the cadence inference and its basis must be stated in the build output"


class TestRefactorOnEveryGreen:
    def test_refactor_is_never_deferred_or_conditional(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"never (deferred|skipped)", flat, re.IGNORECASE)
        assert re.search(
            r"(never|not) (made )?conditional|regardless of (task size|complexity)",
            flat,
            re.IGNORECASE,
        )

    def test_both_cadences_carry_the_refactor_step(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"(both|either) cadence", flat, re.IGNORECASE)


class TestTestsFrozenDuringRefactor:
    def test_build_owns_the_phase_state_writes(self) -> None:
        assert "memory/build-phase.json" in BUILD
        assert "test_files_staged" in BUILD

    def test_test_files_are_staged_at_the_test_to_refactor_transition(self) -> None:
        flat = _flat(BUILD)
        assert re.search(
            r"TEST\s*(→|->)\s*REFACTOR transition", flat
        ) or re.search(r"stage.{0,120}TEST.{0,60}REFACTOR", flat, re.IGNORECASE)

    def test_implementer_no_longer_permits_test_edits_during_refactor(self) -> None:
        assert "(or the test)" not in IMPLEMENTER
        flat = _flat(IMPLEMENTER)
        assert re.search(
            r"(never|do not|must not) (change|edit|touch).{0,40}test",
            flat,
            re.IGNORECASE,
        )

    def test_implementer_documents_the_guard_recovery_flow(self) -> None:
        flat = _flat(IMPLEMENTER)
        assert re.search(
            r"(return|go back) to the TEST phase.{0,200}re-enter REFACTOR",
            flat,
            re.IGNORECASE,
        )

    def test_implementer_documents_the_phase_state_transitions(self) -> None:
        assert "memory/build-phase.json" in IMPLEMENTER


class TestImplementerDefaultCycle:
    def test_default_cycle_is_code_first(self) -> None:
        flat = _flat(IMPLEMENTER)
        assert re.search(r"IMPLEMENT\s*(→|->)\s*TEST\s*(→|->)\s*REFACTOR", flat)

    def test_tdd_variant_keeps_the_red_hard_gate(self) -> None:
        flat = _flat(IMPLEMENTER)
        assert re.search(r"RED", IMPLEMENTER)
        assert re.search(r"must fail", flat, re.IGNORECASE)

    def test_big_batch_shapes_are_named_as_prohibited_in_both_files(self) -> None:
        for text in (BUILD, IMPLEMENTER):
            flat = _flat(text)
            assert re.search(
                r"all (the )?code.{0,40}then.{0,40}all (the )?tests",
                flat,
                re.IGNORECASE,
            ), "must name the all-code-then-all-tests shape"
            assert re.search(
                r"all (the )?tests.{0,40}then.{0,40}all (the )?code|reverse",
                flat,
                re.IGNORECASE,
            ), "must name the all-tests-then-all-code shape"


class TestPlanCarriesTheCadence:
    def test_plan_constraint_states_code_first_default_and_tdd_opt_in(self) -> None:
        flat = _flat(PLAN)
        assert "Code-First Small Batches" in PLAN
        assert re.search(r"opt-in", flat, re.IGNORECASE)

    def test_template_has_the_cadence_metadata_line(self) -> None:
        assert re.search(r"\*\*Cadence\*\*: ?<?(code-first|tdd)", PLAN_TEMPLATE)
        assert "code-first" in PLAN_TEMPLATE and "tdd" in PLAN_TEMPLATE

    def test_template_step_labels_support_both_cadences(self) -> None:
        flat = _flat(PLAN_TEMPLATE)
        assert "**IMPLEMENT**" in PLAN_TEMPLATE
        assert "**TEST**" in PLAN_TEMPLATE
        assert "**REFACTOR**" in PLAN_TEMPLATE
        assert re.search(r"RED.{0,200}GREEN", flat)
