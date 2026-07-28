"""Doc-shape contract for /quality-targets-converge mutation-history.json
reuse (Slice 4 of plans/mutation-testing-every-phase.md, issue #287).

Step 2 gains a "Mutation — reuse rule" sub-step that runs BEFORE the
existing /mutation-testing invocation. Files with a non-stale, non-tool-
unavailable history entry are reused; absent / stale / tool_unavailable
entries are measured fresh and written back as synthetic entries.

Step 4 (priority order) and Step 5 (loop body) are out of scope. The
snapshot fixture pins their byte content — drift there is a contract
violation. No git merge-base at test time (anti-flake for shallow clones).

Ported from tests/skills/quality_targets_converge_mutation_reuse_tests.bats
(issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, REPO_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "quality-targets-converge" / "SKILL.md"
SNAPSHOT = (
    REPO_ROOT / "tests" / "fixtures" / "quality-targets-converge-steps-4-5.snapshot.md"
)


def _text() -> str:
    return SKILL.read_text()


def _step2() -> str:
    return section(_text(), r"^### 2\.", boundary_pattern=r"^### 3\.")


# --- Slice 3 (plans/test-improve-baseline-persistence.md): tracked storage,
# no opt-in gate. Step 3.1: coverage reads the tracked data/ path.


def test_step_2_coverage_bullet_names_tracked_dev_team_reports_data_path():
    assert (
        ".dev-team-reports/<workflow>/<slug>/data/coverage-history.json" in _step2()
    )


# --- Reuse rule placement: BEFORE existing /mutation-testing call ----------


def test_step_2_mutation_reuse_rule_heading_or_label_appears():
    assert grep(r"reuse rule|mutation.+reuse", _step2(), ignore_case=True)


def test_step_2_reuse_rule_appears_before_the_fresh_mutation_testing_invocation():
    # Line-order check: the reuse-rule bullet must come before the bullet
    # that actually invokes /mutation-testing for fresh measurement. We
    # anchor the "fresh" line on "Invoke `/mutation-testing" (with the
    # backtick) to avoid matching incidental prose references.
    lines = _step2().splitlines()
    reuse_idx = next(
        (
            i
            for i, ln in enumerate(lines)
            if grep(r"reuse rule|mutation.+reuse", ln, ignore_case=True)
        ),
        None,
    )
    mut_idx = next(
        (i for i, ln in enumerate(lines) if "Invoke `/mutation-testing" in ln), None
    )
    assert reuse_idx is not None
    assert mut_idx is not None
    assert reuse_idx < mut_idx


# --- Reuse rule body: mtime check + tool_unavailable exclusion ------------


def test_step_2_reuse_rule_names_git_log_format_for_the_mtime_check():
    assert grep(r"git log.+%cI|format=%cI", _step2())


def test_step_2_reuse_rule_excludes_tool_unavailable_history_entries():
    assert "tool_unavailable" in _step2()


def test_step_2_documents_synthetic_phase_5_write_back_for_freshly_measured_files():
    assert grep(
        r"converge-<iteration>|synthetic.+(entry|writeback|write-back)|write.?back",
        _step2(),
        ignore_case=True,
    )


def test_step_2_reuse_rule_names_mutation_history_json_as_the_source():
    assert "mutation-history.json" in _step2()


# --- converge-<n>.json schema additions ----------------------------------


def test_step_2_converge_iteration_json_example_names_reused_from_history():
    assert "reused_from_history" in _step2()


def test_step_2_converge_iteration_json_example_names_measured_fresh():
    assert "measured_fresh" in _step2()


def test_step_2_converge_iteration_json_example_names_total_files():
    assert "total_files" in _step2()


# --- Backward-compat fallback --------------------------------------------


def test_step_2_documents_fallback_when_mutation_history_json_is_absent():
    # Without this, an old orchestrator run from before the contract is
    # silently broken. Demand a labeled paragraph.
    assert grep(
        r"(backward.?compat|fallback).+absent|absent.+(fallback|backward)|"
        r"absent.+fall through|fall through.+absent",
        _step2(),
        ignore_case=True,
    )


# --- Operator visibility -------------------------------------------------


def test_step_2_or_6_operator_report_names_mutation_reused_n_measured_m_cost_saving_signal():
    # The reuse rule's only operator-visible justification is the
    # reused-vs-measured count. The Phase-5 converge report must surface it.
    assert grep(r"reused.+measured|mutation: reused", _text(), ignore_case=True)


# --- Issue #1369: "accepted" survivors filtered the same way "equivalent"
# ones already are, so a documented deferral never reads as a regression.


def test_step_2_filters_status_accepted_alongside_status_equivalent():
    assert grep(r'"equivalent".+"accepted"|"accepted".+"equivalent"', _step2())


# --- Step 4 and Step 5 byte-identical to snapshot ------------------------


def test_step_4_step_5_step_text_byte_identical_to_snapshot_fixture():
    # Bash command substitution ($(...)) strips ALL trailing newlines from
    # both the extracted section and `cat`'d snapshot before the bats `=`
    # comparison — mirror that here rather than comparing raw file bytes.
    current = section(_text(), r"^### 4\.", boundary_pattern=r"^### 6\.")
    expected = SNAPSHOT.read_text()
    assert current.rstrip("\n") == expected.rstrip("\n")
