"""Doc-shape contract for decoupling /coverage-baseline from its original
sole caller (epic #443, issue #432). The worker must run for any workflow,
namespacing its memory output under a --workflow parameter (default
test-improve) and no longer requiring a hard disabled-tests.json
precondition.

Note (issue #674 port): the bats original asserted a --workflow default of
`test-upgrade` and a `/test-modernize` call site — both retired by #566's
consolidation of /test-modernize + /test-upgrade into /test-improve. The
assertions below track the current shipped contract (default
`test-improve`, caller `/test-improve`) — same invariant (a real
orchestrator passes a namespaced --workflow), current names.

Ported from tests/skills/coverage_baseline_decouple_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"
TEST_IMPROVE = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


# --- frontmatter no longer names a single exclusive caller ------------------


def test_coverage_baseline_frontmatter_drops_phase_3_worker_for_a_single_caller():
    assert "Phase-3 worker" not in _text()


def test_coverage_baseline_frontmatter_describes_a_multi_workflow_worker():
    assert grep(r"multi-workflow", _text(), ignore_case=True)


# --- --workflow parameter, default test-improve -----------------------------


def test_coverage_baseline_documents_the_workflow_parameter():
    assert "--workflow" in _text()


def test_coverage_baseline_workflow_defaults_to_test_improve():
    # Parse Arguments must state the default so a bare call is
    # workflow-agnostic.
    assert grep(
        r"default(ing|s)?[^.]*test-improve|test-improve[^.]*default",
        _text(),
        ignore_case=True,
    )


# --- no hard disabled-tests.json precondition -------------------------------


def test_coverage_baseline_no_longer_hard_requires_disabled_tests_json_to_exist():
    # The old Step 1 'Require memory/.../disabled-tests.json to exist ...
    # stop' precondition must be gone so other workflows can run.
    assert not grep(r"Require .*disabled-tests\.json.* to exist", _text())


# --- memory paths are workflow-namespaced, not hardcoded --------------------


def test_coverage_baseline_memory_path_is_namespaced_by_workflow():
    assert grep(r"memory/<workflow>/", _text())


def test_coverage_baseline_no_hardcoded_memory_test_modernize_path_remains():
    assert not grep(r"memory/test-modernize/", _text())


# --- current orchestrator call site passes --workflow test-improve ---------


def test_test_improve_invokes_coverage_baseline_with_workflow_test_improve():
    assert grep(
        r"/coverage-baseline[^`]*--workflow test-improve", TEST_IMPROVE.read_text()
    )
