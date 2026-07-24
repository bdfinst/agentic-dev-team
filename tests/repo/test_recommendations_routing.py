"""#813 — task-size routing reserves the pipeline for large multi-file work.

Rec 2 (`docs/experiments/RECOMMENDATIONS.md`): the pipeline's cost premium is
4.74x on small tasks, 2.57x medium, 1.33x large — so well-specified
single-module `standard` tasks route to the no-plan fast path, and the full
three-phase workflow is reserved for large, multi-file work. The classifier
stays the single source of truth (classification -> route is 1:1), the
bias-up rule is retained, and the routing decision is operator-visible.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

CLASSIFIER = (PLUGIN_ROOT / "knowledge" / "task-size-classifier.md").read_text()
ORCHESTRATOR = (PLUGIN_ROOT / "agents" / "orchestrator.md").read_text()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TestClassifierComputesTheSingleModuleSignal:
    def test_single_module_is_an_explicit_input_signal(self) -> None:
        assert "`single_module`" in CLASSIFIER, (
            "the classifier must define an explicit single_module signal"
        )

    def test_fast_path_eligibility_for_single_module_standard_is_classifier_owned(
        self,
    ) -> None:
        flat = _flat(CLASSIFIER)
        assert re.search(r"single[-_ ]module .{0,40}standard", flat, re.IGNORECASE)
        assert "fast path" in flat.lower()

    def test_exclusions_are_stated_with_the_eligibility_rule(self) -> None:
        flat = _flat(CLASSIFIER)
        for exclusion in ("slice_count", "has_complex_step", "decision_axis_triggered"):
            assert exclusion in flat, f"missing fast-path exclusion signal: {exclusion}"

    def test_bias_up_rule_is_retained(self) -> None:
        assert re.search(r"classify up", CLASSIFIER, re.IGNORECASE)

    def test_classifier_cites_recommendation_2(self) -> None:
        assert "docs/experiments/RECOMMENDATIONS.md" in CLASSIFIER


class TestOrchestratorRoutesPerTheClassifier:
    def _task_size_gate(self) -> str:
        start = ORCHESTRATOR.index("## Task Size Gate")
        end = ORCHESTRATOR.index("## Command Delegation")
        return ORCHESTRATOR[start:end]

    def test_routing_table_sends_single_module_standard_to_the_fast_path(self) -> None:
        gate = _flat(self._task_size_gate())
        assert re.search(
            r"single[-_ ]module .{0,60}standard.{0,120}fast path",
            gate,
            re.IGNORECASE,
        ) or re.search(
            r"standard.{0,60}single[-_ ]module.{0,160}fast path",
            gate,
            re.IGNORECASE,
        ), "the routing table must send single-module standard tasks to the fast path"

    def test_decision_axis_task_never_takes_the_fast_path(self) -> None:
        gate = _flat(self._task_size_gate())
        assert re.search(
            r"decision axis.{0,200}(full|three-phase|cannot|never)",
            gate,
            re.IGNORECASE,
        )

    def test_multi_slice_or_complex_step_takes_the_full_pipeline(self) -> None:
        gate = _flat(self._task_size_gate())
        assert re.search(r"more than one slice|multi-slice|slice_count", gate, re.IGNORECASE)
        assert re.search(r"complex.{0,20}step", gate, re.IGNORECASE)

    def test_gate_cites_rec_2_with_the_measured_premiums(self) -> None:
        gate = self._task_size_gate()
        assert "docs/experiments/RECOMMENDATIONS.md" in gate
        for premium in ("4.74", "2.57", "1.33"):
            assert premium in gate, f"missing Rec 2 cost premium: {premium}"

    def test_routing_decision_is_surfaced_to_the_operator_not_only_the_log(self) -> None:
        gate = _flat(self._task_size_gate())
        assert re.search(
            r"operator-facing (response|output)", gate, re.IGNORECASE
        ), "routing decision + rationale must appear in the operator-facing response"
        assert "memory/decisions.md" in gate
