"""Contract for /build's Step-6 backstop instrumentation and its opt-in
suppression flag (issue #1962, epic #1958).

Step 6's backstop `/code-review` reviews files an inline checkpoint
(sub-steps 4/6) already reviewed in the same run — and under an enclosing
orchestrator (`/test-improve` Phase 5 runs its own end-of-phase panel over
the cumulative diff) it is a third layer over the same code. Whether that
layer earns its cost was unmeasurable, because `review-value.jsonl` carried
only checkpoint rows.

This pins the measure-then-flip ordering the epic committed to: the
instrumentation exists *now*, the flag exists but defaults off, and nothing
in the shipped tree turns it on until `/harness-audit`'s backstop-redundancy
readout says the layer is ~all no-op.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
HARNESS_AUDIT = PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md"
TELEMETRY = PLUGIN_ROOT / "knowledge" / "telemetry-schema.md"
PHASE_5 = (
    PLUGIN_ROOT / "skills" / "test-improve" / "references" / "phase-5-improve.md"
)
PHASE_7 = (
    PLUGIN_ROOT / "skills" / "test-improve" / "references" / "phase-7-refactor.md"
)


@pytest.fixture(scope="module")
def build() -> str:
    return BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step_6(build) -> str:
    s = section(build, r"^### 6\. Run code review")
    assert s, "Step 6 section not found in build/SKILL.md"
    return s


class TestBackstopInstrumentation:
    def test_step_6_appends_a_build_backstop_row(self, step_6):
        assert grep(r'source: "build-backstop"', step_6)

    def test_backstop_row_uses_its_own_checkpoint_value(self, step_6):
        assert grep(r'checkpoint: "backstop"', step_6)

    def test_backstop_row_respects_the_same_consent_and_kill_switch(self, step_6):
        """Counts-only telemetry stays behind the same two switches as the
        checkpoint rows — a new row type must not widen what's recorded."""
        assert grep(r"telemetry\.json", step_6)
        assert grep(r"DEV_TEAM_REVIEW_VALUE", step_6)

    def test_emitter_schema_names_both_sources_and_the_backstop_checkpoint(self, build):
        sub_step_7 = section(build, r"^7\. \*\*Record review value")
        haystack = sub_step_7 or build
        assert grep(r"build-checkpoint\|build-backstop", haystack)
        assert grep(r"step\|slice\|backstop", haystack)


class TestSuppressionFlag:
    def test_flag_is_declared_in_the_argument_hint(self, build):
        assert grep(r"--backstop-review=skip", section(build, r"^argument-hint:") or build)

    def test_flag_defaults_off(self, build):
        args = section(build, r"^## Parse Arguments")
        assert args, "Parse Arguments section not found"
        assert grep_multiline(
            r"--backstop-review=skip.{0,900}[Dd]efault \*\*off\*\*", args
        )

    def test_flag_narrows_only_step_6(self, build):
        """The inline checkpoints, full suite, runtime verification,
        invariants, and Farley step must be explicitly out of its reach —
        this is a duplicate-layer removal, not review traded for speed."""
        args = section(build, r"^## Parse Arguments")
        assert grep_multiline(r"--backstop-review=skip.{0,400}\*\*only\*\*", args)
        for survivor in ("4.9", "4.10", "Step 5", "Farley"):
            assert survivor in args, f"{survivor!r} not named as surviving the flag"

    def test_suppression_is_recorded_not_silent(self, step_6):
        assert grep(r'outcome: "skipped"', step_6)
        assert grep_multiline(r"never\s*\n?\s*a silent absence", step_6)

    def test_flag_requires_an_enclosing_reviewer_and_is_never_self_inferred(
        self, step_6, build
    ):
        args = section(build, r"^## Parse Arguments")
        assert grep(r"enclosing reviewer", args)
        assert grep_multiline(r"never infers it|not a shortcut this skill may take", step_6)


class TestMeasureThenFlipOrderingIsHeld:
    """The epic's stated discipline: the flag ships unused until the data
    says the layer is redundant. A future PR that flips it on must delete
    these two tests deliberately, citing the measurement."""

    @pytest.mark.parametrize("phase_file", [PHASE_5, PHASE_7], ids=lambda p: p.name)
    def test_test_improve_does_not_yet_pass_the_flag(self, phase_file):
        assert "--backstop-review" not in phase_file.read_text(encoding="utf-8")

    def test_harness_audit_publishes_the_gating_measurement(self):
        audit = HARNESS_AUDIT.read_text(encoding="utf-8")
        assert grep(r"build-backstop", audit)
        assert grep(r"backstop_runs_after_a_checkpoint", audit)
        # The readout must warn against flipping on a small sample.
        assert grep_multiline(r"handful of rows is not a finding", audit)


class TestSchemaDocsStayInSync:
    def test_telemetry_schema_documents_the_new_source(self):
        telemetry = TELEMETRY.read_text(encoding="utf-8")
        assert "build-backstop" in telemetry
        assert grep(r"`skipped`", telemetry)

    def test_backstop_rows_stay_in_fix_rate_analysis(self):
        """They are fix-applying (the --internal panel runs the fix loop), so
        unlike read-only `code-review` rows they must NOT be filtered out."""
        audit = HARNESS_AUDIT.read_text(encoding="utf-8")
        assert grep(r'== "build-checkpoint" or \. == "build-backstop"', audit)

    def test_skipped_rows_are_excluded_from_rates(self):
        audit = HARNESS_AUDIT.read_text(encoding="utf-8")
        assert grep(r'select\(\.outcome != "skipped"\)', audit)
