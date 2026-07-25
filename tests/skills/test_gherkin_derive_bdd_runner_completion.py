"""Contract for gherkin-derive's honest, prominent bdd-runner completion
signal (issue #1420, Slice 4: Steps 4.1-4.2).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section_outside_code

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"

_BDD_RUNNER_START = r"^\*\*`bdd-runner` mode — state completion plainly"
_EVERY_MODE_START = r"^\*\*Every mode that writes `\.feature` files"


def _text() -> str:
    return SKILL.read_text()


def _bdd_runner_completion_section() -> str:
    text = _text()
    # section_outside_code (not a raw str.find slice) both skips the fenced
    # `gherkin_stub_gate.py` command example inside this section and fails
    # loudly — via the assert below — instead of silently degrading to a
    # near-empty/anomalous slice if either bold-line anchor is ever reworded.
    section = section_outside_code(
        text, start_pattern=_BDD_RUNNER_START, boundary_pattern=_EVERY_MODE_START
    )
    assert section, "bdd-runner completion section not found in gherkin-derive/SKILL.md"
    return section


def test_not_done_statement_is_documented_as_first_line_headline():
    s = _bdd_runner_completion_section()
    assert grep(r"FIRST\s+line|headline", s, ignore_case=True)
    assert grep(r"not a secondary aside|replacing", s, ignore_case=True)


def test_names_build_and_documents_proactively_asking():
    s = _bdd_runner_completion_section()
    assert "/build" in s
    assert grep(r"ask the operator whether to continue", s, ignore_case=True)


def test_ask_is_scoped_to_standalone_only_orchestrated_runs_defer():
    s = _bdd_runner_completion_section()
    assert grep(r"standalone invocations only", s, ignore_case=True)
    assert grep(r"do not ask|Phase 3.*own human gate", s, ignore_case=True)


def test_non_interactive_case_is_print_only_never_blocking():
    s = _bdd_runner_completion_section()
    assert grep(r"non-interactive fallback", s, ignore_case=True)
    assert grep(r"never blocks the run|best-effort", s, ignore_case=True)


def test_old_binding_not_complete_phrasing_does_not_survive_as_separate_sentence():
    s = _bdd_runner_completion_section()
    assert s.count("binding is not complete") == 0


def test_no_other_step6_subsection_may_print_unqualified_completion_language():
    s = collapsed(_bdd_runner_completion_section())
    assert grep(r"No other part of this report.*unqualified", s, ignore_case=True)


def test_zero_pending_stubs_states_completion_with_no_recommendation():
    s = _bdd_runner_completion_section()
    assert "bdd-runner binding complete" in s
    assert grep(r"no recommendation and no continue", s, ignore_case=True)


def test_never_fills_in_an_already_pending_stub_distinct_from_new_scaffolding():
    s = _bdd_runner_completion_section()
    assert grep(r"never fills in an already-pending stub|never.*modif.*step-definition file", s, ignore_case=True)
    assert grep(r"distinct from.*never blocks.*Step 4|newly-discovered scenarios", s, ignore_case=True)


def test_step_6_documents_the_step_definition_merge_error_sentence_template():
    text = _text()
    section = section_outside_code(
        text,
        start_pattern=r"^\*\*Call out step-definition merge structural errors",
        boundary_pattern=_BDD_RUNNER_START,
    )
    assert section, "step-definition merge structural-error callout not found in gherkin-derive/SKILL.md"
    s = collapsed(section)
    assert "gherkin_stub_merge.py merge" in s
    assert grep(
        r'Could not merge step-definition stubs into <path>: <language> structure not recognized \(<sentinel>\)\. '
        r"No changes were made — fix the file's syntax and re-run, or report the file:line if the structure looks valid\.",
        s,
    )
    assert "unbalanced-braces" in s
    assert "dangling-annotation" in s


def test_step_6_calls_out_skipped_duplicate_step_patterns():
    # Fixed post-build-review: gherkin_stub_merge.py's skipped_duplicate_patterns
    # was returned by the script since Slice 3 but never surfaced in Step 6,
    # unlike its .feature-merge twin (skipped_duplicate_titles) which already
    # had a dedicated callout — the same silent-gap risk for step-definition
    # merges went unreported.
    text = _text()
    section = section_outside_code(
        text,
        start_pattern=r"^\*\*Call out `gherkin_stub_merge\.py`'s skipped duplicate steps",
        boundary_pattern=r"^\*\*Call out step-definition merge structural errors",
    )
    assert section, "skipped_duplicate_patterns callout not found in gherkin-derive/SKILL.md"
    s = collapsed(section)
    assert "skipped_duplicate_patterns" in s
    assert grep(r"skipped duplicate step:", s)
    assert grep(r"do not.*fold|not.*fold into the surface-count summary", s, ignore_case=True)


def test_step_6_maps_all_four_merge_sentinels_not_just_the_two_structural_ones():
    # Fixed post-build-review: unsafe-path and malformed-candidates are real,
    # documented exit-2 causes from gherkin_stub_merge.py (per Step 4's own
    # error-contract list), but the original Step 6 template only covered
    # unbalanced-braces/dangling-annotation — an operator hitting the other
    # two would be told "fix the file's syntax", which is wrong remediation
    # for a path-composition bug or this skill's own scratch file.
    text = _text()
    section = section_outside_code(
        text,
        start_pattern=r"^\*\*Call out step-definition merge structural errors",
        boundary_pattern=_BDD_RUNNER_START,
    )
    assert section, "step-definition merge structural-error callout not found in gherkin-derive/SKILL.md"
    s = collapsed(section)
    assert "unsafe-path" in s
    assert "malformed-candidates" in s
    assert grep(r"fix how the surface name was derived into a path", s)
    assert grep(r"re-author the candidates text", s)


def test_consistency_with_phase_5_gate_names_same_remediation():
    text = _text()
    section = section_outside_code(
        text,
        start_pattern=r"^\*\*Consistency with `/test-improve` Phase 5",
        boundary_pattern=_EVERY_MODE_START,
    )
    assert section, "Consistency-with-Phase-5 section not found in gherkin-derive/SKILL.md"
    assert "/build" in section
    assert grep(r"same.*pending-stub state|two different checkpoints", section, ignore_case=True)


def _step_4_section() -> str:
    text = _text()
    section = section_outside_code(
        text, start_pattern=r"^## Step 4", boundary_pattern=r"^## Step 5"
    )
    assert section, "Step 4 section not found in gherkin-derive/SKILL.md"
    return section


def test_step_4_invokes_gherkin_stub_merge_never_a_raw_write():
    s = _step_4_section()
    assert "gherkin_stub_merge.py merge" in s
    assert grep(r"never a raw `Write`", s, ignore_case=True)


def test_step_4_documents_the_exit_2_error_contract_like_step_5():
    s = collapsed(_step_4_section())
    assert grep(r"Exit 2 means no write occurred", s, ignore_case=True)
    assert grep(r"read the `--json` payload's `error` field", s, ignore_case=True)


def test_step_5_output_bullet_reflects_the_merge_based_write_path():
    text = _text()
    section = section_outside_code(
        text, start_pattern=r"^## Step 5 — Output", boundary_pattern=r"^## Step 6"
    )
    assert section, "Step 5 section not found in gherkin-derive/SKILL.md"
    bullet = collapsed(section)
    assert grep(
        r"pending stubs.*written via Step 4's `gherkin_stub_merge\.py merge`",
        bullet,
        ignore_case=True,
    )
    assert grep(r"never a raw `Write`", bullet, ignore_case=True)
