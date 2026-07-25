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
