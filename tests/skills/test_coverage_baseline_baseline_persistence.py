"""Doc-shape contract for /coverage-baseline writing directly to tracked
storage and guarding an existing tracked baseline before re-capturing
(plans/test-improve-baseline-persistence.md, Slice 1).

Scope, distinct from test_coverage_baseline_decouple.py (workflow-namespacing
decoupling): the existing-baseline guard (Step 1.2) that sits between
"Detect the coverage tool" and "Run coverage", and the atomic, direct-to-
tracked-storage persist step (Step 1.3).
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _guard_section() -> str:
    return section(_text(), r"^### 2\. Existing-baseline guard", boundary_pattern=r"^### ")


# --- Step 1.2: existing-baseline guard --------------------------------------


def test_names_the_existing_baseline_guard():
    assert "existing-baseline guard" in _text()


def test_does_not_use_the_reserved_existing_copy_guard_term():
    # "existing-copy guard" is reserved elsewhere in the plan for a
    # different, unrelated mechanism this slice does not touch.
    assert "existing-copy guard" not in _text()


def test_guard_checks_the_tracked_data_path_for_the_resolved_slug():
    assert grep(
        r"\.dev-team-reports/<workflow>/<slug>/data/baseline-coverage\.json",
        _guard_section(),
    )


def test_guard_cites_the_shared_decision_defaults_axis():
    guard = _guard_section()
    assert grep(
        r"knowledge/decision-defaults\.md",
        guard,
    )
    assert "Re-capture" in guard


def test_guard_on_keep_skips_straight_to_report_without_running_coverage():
    guard = _guard_section()
    assert grep(r"skip straight to Step 7 \(Report\)", guard)
    assert grep(r"Do not dispatch a coverage run", guard, ignore_case=True)


def test_guard_on_keep_reuses_existing_captured_at():
    assert grep(r"report its `captured_at`", _guard_section())


def test_guard_names_unrecognized_answer_reprompts_branch_explicitly():
    # The SKILL.md's own prose must be explicit about this branch, not only
    # reachable by opening decision-defaults.md.
    assert grep(r"re-prompt", _text(), ignore_case=True)


def test_guard_names_malformed_file_treated_as_absent_branch_explicitly():
    assert grep(r"malformed|corrupt", _text(), ignore_case=True)
    assert grep(r"treated as absent|treat.*as absent", _text(), ignore_case=True)


def test_guard_step_precedes_run_coverage_step():
    text = _text()
    guard_match = re.search(r"^### \d+\.\s*Existing-baseline guard", text, re.MULTILINE)
    run_match = re.search(r"^### \d+\.\s*Run coverage", text, re.MULTILINE)
    assert guard_match is not None
    assert run_match is not None
    assert guard_match.start() < run_match.start()


# --- Step 1.3: persist directly to tracked data/, atomically ----------------


def test_persist_writes_to_the_tracked_data_path():
    assert grep(
        r"\.dev-team-reports/<workflow>/<slug>/data/baseline-coverage\.json",
        _text(),
    )


def test_persist_uses_temp_file_then_rename_idiom():
    text = _text()
    assert "temp-file-then-rename" in text
    assert grep(r"\.tmp", text)
    assert grep(r"mv -f", text)


def test_persist_no_longer_writes_the_bare_claude_memory_baseline_path():
    # The old direct, non-atomic write target must be gone.
    assert not grep(
        r"\.claude/memory/<workflow>/<slug>/baseline-coverage\.json",
        _text(),
    )


def test_persist_still_appends_to_the_phase_2_process_memory_file():
    # phase-2.md (process bookkeeping) is unchanged — only the baseline
    # data file's write target and write mode moved.
    assert grep(r"\.claude/memory/<workflow>/<slug>/phase-2\.md", _text())
