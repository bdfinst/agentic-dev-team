"""#813 / ADR 0017 — Code-First Small Batches is the sole build cadence.

Rec 3/4 (`docs/experiments/RECOMMENDATIONS.md`): one agent per unit of work
implements one behavior, writes its test, keeps the suite green, refactors on
every green — never deferring or skipping the refactor. Classic TDD's
RED-GREEN-REFACTOR opt-in was removed entirely by ADR 0017
(`docs/adr/0017-single-build-cadence-remove-classic-tdd-opt-in.md`); there is
no `--tdd` flag and no per-plan cadence to resolve. Tests are frozen during
REFACTOR, enforced mechanically via the phase state `/build` records.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

BUILD = (PLUGIN_ROOT / "skills" / "build" / "SKILL.md").read_text()
IMPLEMENTER = (PLUGIN_ROOT / "agents" / "implementer.md").read_text()
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

    def test_no_tdd_opt_in_flag_or_cadence_choice_remains(self) -> None:
        """ADR 0017 removed the dual-cadence opt-in — there is exactly one cadence."""
        assert "--tdd" not in BUILD
        assert "**Cadence**" not in BUILD
        flat = _flat(BUILD)
        assert not re.search(
            r"RED\s*(→|->)\s*GREEN\s*(→|->)\s*REFACTOR", flat
        ), "classic TDD's RED-GREEN-REFACTOR cycle should no longer be documented as an option"


class TestRefactorOnEveryGreen:
    def test_refactor_is_never_deferred_or_conditional(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"never (deferred|skipped)", flat, re.IGNORECASE)
        assert re.search(
            r"(never|not) (made )?conditional|regardless of (task size|complexity)",
            flat,
            re.IGNORECASE,
        )

    def test_refactor_step_is_mandated_in_both_build_and_implementer_docs(self) -> None:
        """The single cadence's refactor mandate must be documented consistently
        in both the orchestrator-facing build doc and the implementer agent."""
        for text in (BUILD, IMPLEMENTER):
            flat = _flat(text)
            assert re.search(r"never (deferred|skipped)", flat, re.IGNORECASE)


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

    def test_implementer_states_there_is_no_cadence_to_resolve(self) -> None:
        """ADR 0017: the implementer agent must not describe a cadence choice."""
        assert "--tdd" not in IMPLEMENTER
        flat = _flat(IMPLEMENTER)
        assert re.search(r"no cadence to resolve", flat, re.IGNORECASE)

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
    def test_plan_constraint_states_code_first_as_the_only_cadence(self) -> None:
        assert "Code-First Small Batches" in PLAN
        assert "docs/experiments/RECOMMENDATIONS.md" in PLAN

    def test_template_has_no_cadence_metadata_line(self) -> None:
        """ADR 0017 removed the per-plan cadence choice, so the template
        carries no **Cadence** metadata field."""
        assert not re.search(r"\*\*Cadence\*\*:", PLAN_TEMPLATE)

    def test_template_step_labels_use_the_single_cadence(self) -> None:
        assert "**IMPLEMENT**" in PLAN_TEMPLATE
        assert "**TEST**" in PLAN_TEMPLATE
        assert "**REFACTOR**" in PLAN_TEMPLATE
        flat = _flat(PLAN_TEMPLATE)
        assert not re.search(
            r"RED.{0,200}GREEN", flat
        ), "template should not carry classic-TDD RED/GREEN labeling"
