"""#813 / ADR 0017 — Code-First Small Batches is the sole build cadence.

Rec 3/4 (`docs/experiments/RECOMMENDATIONS.md`): one agent per unit of work
implements one behavior, writes its test, keeps the suite green, refactors on
every green — never deferring or skipping the refactor. Classic TDD's
RED-GREEN-REFACTOR opt-in was removed entirely by ADR 0017
(`docs/adr/0017-single-build-cadence-remove-classic-tdd-opt-in.md`); there is
no `--tdd` flag and no per-plan cadence to resolve. Tests are frozen during
REFACTOR, enforced mechanically via the phase state `/build` records.

Issue #1387 retired the standalone `implementer` agent (it self-identified as
a Software Engineer variant carrying no distinct persona) and folded its
per-step dispatch context into `/build`'s own instructions: the orchestrator
now dispatches `software-engineer` directly, and `skills/build/SKILL.md` is
the sole carrier of the per-behavior cycle, phase-state bookkeeping, and
"design is settled" constraint that `implementer.md`'s prompt used to encode.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

BUILD = (PLUGIN_ROOT / "skills" / "build" / "SKILL.md").read_text()
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

    def test_build_states_there_is_no_cadence_to_resolve(self) -> None:
        """ADR 0017: the build dispatch instructions must not describe a cadence choice."""
        flat = _flat(BUILD)
        assert re.search(r"no cadence to resolve", flat, re.IGNORECASE)


class TestRefactorOnEveryGreen:
    def test_refactor_is_never_deferred_or_conditional(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"never (deferred|skipped)", flat, re.IGNORECASE)
        assert re.search(
            r"(never|not) (made )?conditional|regardless of (task size|complexity)",
            flat,
            re.IGNORECASE,
        )

    def test_big_batch_shapes_are_named_as_prohibited(self) -> None:
        flat = _flat(BUILD)
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


class TestTestsFrozenDuringRefactor:
    def test_build_owns_the_phase_state_writes(self) -> None:
        assert "memory/build-phase.json" in BUILD
        assert "test_files_staged" in BUILD

    def test_test_files_are_staged_at_the_test_to_refactor_transition(self) -> None:
        flat = _flat(BUILD)
        assert re.search(
            r"TEST\s*(→|->)\s*REFACTOR transition", flat
        ) or re.search(r"stage.{0,120}TEST.{0,60}REFACTOR", flat, re.IGNORECASE)

    def test_build_no_longer_permits_test_edits_during_refactor(self) -> None:
        assert "(or the test)" not in BUILD
        flat = _flat(BUILD)
        assert re.search(
            r"(never|do not|must not) (change|edit|touch).{0,40}test",
            flat,
            re.IGNORECASE,
        )

    def test_build_documents_the_guard_recovery_flow(self) -> None:
        flat = _flat(BUILD)
        assert re.search(
            r"(return|go back) to the TEST phase.{0,200}re-enter REFACTOR",
            flat,
            re.IGNORECASE,
        )


class TestBuildDispatchesSoftwareEngineer:
    def test_build_dispatches_software_engineer_not_a_retired_implementer_agent(
        self,
    ) -> None:
        """Issue #1387: the standalone `implementer` agent was retired and
        folded into `software-engineer` — /build must dispatch it by name."""
        assert "`software-engineer`" in BUILD
        assert "`implementer`" not in BUILD
        assert not (PLUGIN_ROOT / "agents" / "implementer.md").exists()

    def test_build_states_the_design_is_settled_constraint(self) -> None:
        flat = _flat(BUILD)
        assert re.search(r"design is settled", flat, re.IGNORECASE)


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
