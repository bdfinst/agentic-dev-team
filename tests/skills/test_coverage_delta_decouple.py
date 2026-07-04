"""Doc-shape contract for decoupling /coverage-delta from its original sole
caller (epic #443, issue #433). The worker must run for any workflow,
resolving its baseline / coverage-history / mutation-history paths under a
--workflow namespace (default test-improve) rather than a hardcoded one.

Note (issue #674 port): the bats original asserted a --workflow default of
`test-upgrade` and a `/test-modernize` call site — both retired by #566's
consolidation of /test-modernize + /test-upgrade into /test-improve. The
assertions below track the current shipped contract (default
`test-improve`, caller `/test-improve`) — same invariant, current names.

Ported from tests/skills/coverage_delta_decouple_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"
TEST_IMPROVE = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


# --- frontmatter no longer names a single exclusive caller ------------------


def test_coverage_delta_frontmatter_drops_phase_4_worker_for_a_single_caller():
    assert "Phase-4 worker" not in _text()


def test_coverage_delta_frontmatter_describes_a_multi_workflow_worker():
    assert grep(r"multi-workflow", _text(), ignore_case=True)


# --- --workflow parameter, default test-improve -----------------------------


def test_coverage_delta_documents_the_workflow_parameter():
    assert "--workflow" in _text()


def test_coverage_delta_workflow_defaults_to_test_improve():
    assert grep(
        r"default(ing|s)?[^.]*test-improve|test-improve[^.]*default",
        _text(),
        ignore_case=True,
    )


# --- memory paths are workflow-namespaced, not hardcoded --------------------


def test_coverage_delta_baseline_path_namespaced_by_workflow():
    assert grep(r"memory/<workflow>/<slug>/baseline-coverage\.json", _text())


def test_coverage_delta_coverage_history_path_namespaced_by_workflow():
    assert grep(r"memory/<workflow>/<slug>/coverage-history\.json", _text())


def test_coverage_delta_mutation_history_path_namespaced_by_workflow():
    assert grep(r"memory/<workflow>/<slug>/mutation-history\.json", _text())


def test_coverage_delta_no_hardcoded_memory_test_modernize_path_remains():
    assert not grep(r"memory/test-modernize/", _text())


# --- current orchestrator call site passes --workflow test-improve ---------


def test_test_improve_invokes_coverage_delta_with_workflow_test_improve():
    assert grep(
        r"/coverage-delta[^`]*--workflow test-improve", TEST_IMPROVE.read_text()
    )
