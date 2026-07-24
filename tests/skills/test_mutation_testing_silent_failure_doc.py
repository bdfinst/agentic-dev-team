"""Doc-shape contract for issues #554, #557, #558, #559 additions to the
/mutation-testing skill:

  #554/#557 — Step 1c smoke gate (workflow-enforced; halts on Killed=0 with
              Survived>0; parses mutation-report.json, not stdout)
  #557      — SolutionPath trap warning + xunit.v3 -> Step 1c link
  #558      — Long-run inspection section (progress, health, error
              inspection) + dots reporter recommendation
  #558/#559 — Shipped wrapper + status-loop pointers, copy-both instruction

Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slices 1, 2, 5.

Section-scanning ignores fenced code blocks. Prose is the deliverable;
these guards regress when the contract drifts.

Ported from tests/skills/mutation_testing_silent_failure_doc_tests.bats
(issue #674).

Note: Slice 5 doc-shape guards (shipped wrapper + copy-both instruction)
live in mutation_testing_wrapper_reference_tests.bats (not in this port's
scope) — they ship with PR2 alongside the actual wrapper + status-loop
scripts. Splitting them out lets PR1 land without PR2's content.
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    first_line_outside_code,
    grep,
    section_outside_code,
)

MUTATION_TESTING = PLUGIN_ROOT / "skills" / "mutation-testing"
SKILL = MUTATION_TESTING / "SKILL.md"
CSHARP = MUTATION_TESTING / "references" / "languages" / "csharp-stryker-net.md"


def _text() -> str:
    return SKILL.read_text()


def _csharp_text() -> str:
    return CSHARP.read_text()


def _step_1c_section() -> str:
    return section_outside_code(_text(), r"^## Step 1c")


def _longrun_section() -> str:
    return section_outside_code(_text(), r"^## Long-run inspection")


# =============================================================================
# Slice 1 — SKILL.md · Step 1c smoke gate (#554, #557)
# =============================================================================


def test_skill_step_1c_smoke_gate_section_exists_between_step_1b_and_step_2():
    # Step 1c must live between Step 1b and Step 2 — otherwise it isn't the
    # workflow-enforced gate the plan promises; it's just prose floating
    # anywhere.
    text = _text()
    step1b_line = first_line_outside_code(text, r"^## Step 1b")
    step1c_line = first_line_outside_code(text, r"^## Step 1c")
    step2_line = first_line_outside_code(text, r"^## Step 2")
    assert step1b_line is not None
    assert step1c_line is not None
    assert step2_line is not None
    assert step1b_line < step1c_line
    assert step1c_line < step2_line


def test_skill_step_1c_names_killed_0_survived_0_failure_signature():
    s = _step_1c_section()
    assert grep(r"Killed", s) and grep(r"Survived", s) and grep(r"0", s)


def test_skill_step_1c_names_mutation_report_json_as_the_parse_source():
    assert grep(r"mutation-report\.json", _step_1c_section())


def test_skill_step_1c_warns_against_parsing_stdout_ansi_progress_reporter():
    # The whole point of the gate is deterministic parsing — must call out
    # that stdout / ANSI progress reporter is NOT the source.
    assert grep(r"(stdout|progress reporter|ANSI)", _step_1c_section())


def test_skill_step_1c_halt_message_references_554_and_557():
    s = _step_1c_section()
    assert "#554" in s
    assert "#557" in s


def test_skill_step_1c_halt_message_enumerates_diagnostic_checklist():
    # Checklist must name at least the three things the plan calls out:
    # manual mutation-kills-the-test check, SolutionPath review,
    # unintended-project enumeration.
    s = _step_1c_section()
    assert grep(r"manual", s, ignore_case=True)
    assert "SolutionPath" in s
    assert grep(r"(test.?project|enumerat)", s, ignore_case=True)


def test_skill_step_1c_defines_behavior_for_killed_0_survived_0_no_signal_probe():
    # The Killed==0 && Survived==0 case must be explicitly addressed —
    # otherwise a no-mutants-generated probe silently authorizes the full
    # run.
    assert grep(
        r"(no.?signal|no.?scored.?mutants|zero.?mutants|killed.*0.*survived.*0|"
        r"survived.*0.*killed.*0|pick a different probe|different probe file)",
        _step_1c_section(),
        ignore_case=True,
    )


def test_skill_step_1c_authorizes_proceeding_when_killed_gt_0():
    assert grep(r"(proceed|authoriz|continue)", _step_1c_section(), ignore_case=True)


# =============================================================================
# Slice 1 — SKILL.md · Long-run inspection section (#558)
# =============================================================================


def test_skill_long_run_inspection_section_exists_between_step_2_and_step_3():
    # The section anchors between Step 2 (Run) and Step 3 (Parse) — that's
    # where a long-running Stryker/pitest/mutmut invocation lives. Section
    # title fixed as "Long-run inspection" (case-sensitive).
    text = _text()
    step2_line = first_line_outside_code(text, r"^## Step 2")
    longrun_line = first_line_outside_code(text, r"^## Long-run inspection")
    step3_line = first_line_outside_code(text, r"^## Step 3")
    assert step2_line is not None
    assert longrun_line is not None
    assert step3_line is not None
    assert step2_line < longrun_line
    assert longrun_line < step3_line


def test_skill_long_run_inspection_names_progress_health_error_inspection_signals():
    s = _longrun_section()
    assert grep(r"progress", s, ignore_case=True)
    assert grep(r"health", s, ignore_case=True)
    assert grep(r"error inspection", s, ignore_case=True)


def test_skill_long_run_inspection_documents_10_minute_default_cadence():
    assert grep(r"(10[- ]?minute|10 min|600 ?s|10-min)", _longrun_section())


def test_skill_long_run_inspection_notes_language_files_may_add_signatures():
    assert grep(
        r"(language.?file|per-language|references/languages|tool-specific)",
        _longrun_section(),
    )


def test_skill_long_run_inspection_names_portable_bash_wrapper_as_an_example():
    # Section must name concrete implementations (per plan-review
    # Acceptance Critic's phrasing fix) — not just describe an abstract
    # contract.
    assert grep(r"wrapper", _longrun_section())


def test_skill_long_run_inspection_names_in_session_monitor_as_an_alternative():
    assert "Monitor" in _longrun_section()


# =============================================================================
# Slice 2 — csharp-stryker-net.md (#557: SolutionPath trap + Step 1c link
#                                 + dots reporter)
# =============================================================================


def test_csharp_stryker_net_solutionpath_trap_warning_exists():
    assert grep(r"SolutionPath.*trap|trap.*SolutionPath", _csharp_text())


def test_csharp_stryker_net_solutionpath_warning_enumerates_three_remediation_paths():
    # Three paths: remove SolutionPath; exclude the main test project;
    # downgrade to xunit.v2.
    text = _csharp_text()
    idx = text.find("SolutionPath")
    assert idx != -1
    s = text[idx:]
    assert grep(r"(remove|omit).*(solutionpath|solution.?path)", s, ignore_case=True)
    assert grep(r"(exclude|omit).*(test.?project|main test)", s, ignore_case=True)
    assert grep(r"(downgrade|xunit\.?v2)", s, ignore_case=True)


def test_csharp_stryker_net_xunit_v3_section_links_to_step_1c():
    # The xunit.v3 section must point at SKILL.md's Step 1c rather than
    # duplicate the smoke procedure. Existing section heading is
    # "## xunit.v3 detection" (case-sensitive; the reference already uses
    # it).
    s = section_outside_code(_csharp_text(), r"^## xunit\.v3")
    assert "Step 1c" in s


def test_csharp_stryker_net_reporters_guidance_names_dots():
    # The reporters recommendation must include "dots" — that's the
    # survives-redirection reporter the status loop parses.
    assert '"dots"' in _csharp_text()
