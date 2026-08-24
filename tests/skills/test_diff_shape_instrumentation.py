"""Contract for the `diff_shape` instrumentation and the test-only lens gate's
measure-first ordering (issue #1964, epic #1958).

Under `/test-improve`'s default `refactor-mode: no-refactor`, Phase 5's diff is
structurally guaranteed test-only — `/build` rejects production-code changes in
that mode — yet the four opus-tier `Scope: always` lenses run on it anyway. The
existing gates cannot exploit that: change-shape covers doc/config only, and a
newly-added test file trips change-impact's `structure` signal.

This slice ships the *measurement*, not the gate. These tests pin that
ordering: `diff_shape` is recorded, `/harness-audit` reports the split, and
nothing narrows a roster until the data justifies each lens individually.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
CODE_REVIEW = PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
HARNESS_AUDIT = PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md"
TELEMETRY = PLUGIN_ROOT / "knowledge" / "telemetry-schema.md"


@pytest.fixture(scope="module")
def build() -> str:
    return BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def audit() -> str:
    return HARNESS_AUDIT.read_text(encoding="utf-8")


class TestEmitterRecordsDiffShape:
    def test_build_emitter_schema_carries_diff_shape(self, build):
        assert grep(r'"diff_shape":"test-only\|mixed"', build)

    def test_value_comes_from_the_helper_not_from_eyeballing(self, build):
        """Same deterministic-tools-over-inference rule the gates follow: the
        classification is a program's output, not a judgement call."""
        assert grep(r"change_shape\.py", build)
        assert grep_multiline(r"Do not eyeball the file\s*\n?\s*list", build)

    def test_mapping_from_is_test_only_is_explicit(self, build):
        assert grep_multiline(
            r"`isTestOnly`.{0,120}`true`.{0,40}`\"test-only\"`", build
        )

    def test_include_bias_is_stated_so_test_only_is_never_over_claimed(self, build):
        assert grep_multiline(r"never over-claimed", build)


class TestSchemaDocsCarryTheField:
    def test_telemetry_schema_documents_diff_shape(self):
        telemetry = TELEMETRY.read_text(encoding="utf-8")
        assert "diff_shape" in telemetry
        assert grep(r"Absent on pre-#1964 rows", telemetry)

    def test_performance_metrics_documents_diff_shape(self):
        perf = (PLUGIN_ROOT / "skills" / "performance-metrics" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "diff_shape" in perf


class TestHarnessAuditReportsTheSplit:
    def test_audit_groups_outcomes_by_lens_and_shape(self, audit):
        assert grep(r"test_only_no_op", audit)
        assert grep(r"mixed_no_op", audit)

    def test_audit_requires_the_mixed_control(self, audit):
        """A lens that no-ops equally on both shapes is a quiet lens, not one
        this diff shape defeats — gating on that would be reading noise."""
        assert grep_multiline(r"as the control", audit)
        assert grep_multiline(r"quiet lens", audit)

    def test_audit_requires_stating_the_sample_size(self, audit):
        assert grep_multiline(r"not enough data yet", audit)

    def test_audit_names_the_two_never_on_intuition_lenses(self, audit):
        assert grep_multiline(
            r"not candidates regardless|are \*\*not\*\* candidates regardless", audit
        )
        for lens in ("security-review", "correctness-review"):
            assert lens in audit


class TestGateIsNotYetWired:
    """The measure-then-flip contract, pinned. A PR that populates
    `TEST_ONLY_SKIP_LENSES` must cite the measured split and update this."""

    def test_code_review_documents_the_field_as_gating_nothing(self):
        cr = CODE_REVIEW.read_text(encoding="utf-8")
        assert grep(r"isTestOnly", cr)
        assert grep_multiline(r"\*\*gates nothing\*\*", cr)

    def test_code_review_forbids_narrowing_on_it_today(self):
        cr = CODE_REVIEW.read_text(encoding="utf-8")
        assert grep_multiline(
            r"do not narrow a roster on it until it does gate something", cr
        )

    def test_change_shape_gate_section_still_prints_the_new_field(self):
        cr = CODE_REVIEW.read_text(encoding="utf-8")
        assert grep(r'"isTestOnly": <bool>', cr)
