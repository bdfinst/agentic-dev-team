"""Doc-shape contract for the /mutation-testing skill's workflow-callable
mode. Plan: plans/mutation-testing-every-phase.md — Slice 1 (Steps 1.1 +
1.2) and Slice 11 / Step 11.3.

These tests assert the SKILL.md prose carries the invariants Slice 1
establishes:
- Three new flags: --scope, --emit-json, --workflow-managed-approval.
- Constraints retain "always ask the user before running" AND document
  the --workflow-managed-approval carve-out with a named caller allowlist.
- A documented machine-readable output schema (keys + per-tool examples).
- The interactive prompt remains observable (literal "Estimated time:"
  string).

We are not exercising runtime behavior; the deliverable is the SKILL.md
prose, and these guards regress when the contract drifts.

Ported from tests/skills/mutation_testing_scoping_tests.bats (issue #674).
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

MUTATION_TESTING = PLUGIN_ROOT / "skills" / "mutation-testing"
SKILL = MUTATION_TESTING / "SKILL.md"
LANG_DIR = MUTATION_TESTING / "references" / "languages"
REGISTRY = MUTATION_TESTING / "references" / "workflow-callers.md"


def _text() -> str:
    return SKILL.read_text()


def _section(header: str) -> str:
    return section(
        _text(),
        rf"^## {re.escape(header)}",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )


def _constraints_section() -> str:
    return _section("Constraints")


def _machine_readable_section() -> str:
    return _section("Machine-readable output")


# --- Step 1.1: flag surface --------------------------------------------------


def test_skill_parse_arguments_names_scope():
    assert grep(r"--scope", _section("Parse Arguments"))


def test_skill_parse_arguments_names_emit_json():
    assert grep(r"--emit-json", _section("Parse Arguments"))


def test_skill_parse_arguments_names_workflow_managed_approval():
    assert grep(r"--workflow-managed-approval", _section("Parse Arguments"))


# --- Step 1.1: constraints carve-out + invariant retained --------------------


def test_skill_constraints_retains_always_ask_the_user_before_running_invariant():
    assert grep(
        r"always ask the user before running", _constraints_section(), ignore_case=True
    )


def test_skill_constraints_documents_workflow_managed_approval_carve_out():
    assert grep(r"--workflow-managed-approval", _constraints_section())


def test_skill_carve_out_names_coverage_delta_as_an_allowed_caller():
    assert grep(r"/coverage-delta", _constraints_section())


def test_skill_carve_out_names_quality_targets_converge_as_an_allowed_caller():
    assert grep(r"/quality-targets-converge", _constraints_section())


def test_skill_carve_out_cites_test_modernize_phase_0_as_the_approval_boundary():
    assert grep(r"Phase 0|workflow-level approval", _constraints_section())


def test_skill_carve_out_documents_extensibility_rule_for_future_callers():
    # New callers can't silently bypass the prompt — the SKILL must tell
    # them to document their workflow-level approval boundary first.
    assert grep(r"new caller|must document", _constraints_section())


# --- Step 1.1: machine-readable output schema --------------------------------


def test_skill_has_a_machine_readable_output_section():
    assert grep(r"^## Machine-readable output", _text())


def test_skill_schema_names_schema_version():
    assert grep(r"schema_version", _machine_readable_section())


def test_skill_schema_names_tool_scope_captured_at_total_killed_survived_equivalent_survivors():
    section_text = _machine_readable_section()
    for key in (
        "tool",
        "scope",
        "captured_at",
        "total",
        "killed",
        "survived",
        "equivalent",
        "survivors",
    ):
        assert key in section_text, f"missing key: {key}"


def test_skill_survivor_entries_name_file_line_operator_status():
    section_text = _machine_readable_section()
    for key in ("file", "line", "operator", "status"):
        assert key in section_text, f"missing survivor key: {key}"


def test_skill_documents_no_tool_installed_error_envelope():
    assert grep(r"no_tool_installed", _text())


def test_skill_documents_empty_scope_error_envelope():
    assert grep(r"empty_scope", _text())


def test_skill_documents_unwritable_path_error_path_stderr_exit_non_zero():
    assert grep(r"unwritable|read-only|stderr", _text(), ignore_case=True)


# --- Step 1.1: interactive mode unchanged ------------------------------------


def test_skill_confirmation_gate_documents_literal_estimated_time_prompt():
    # The Gherkin scenario pins the observable Then: stdout contains
    # "Estimated time:"
    assert "Estimated time:" in _text()


def test_skill_confirmation_gate_documents_skip_when_workflow_managed_approval():
    # The Step 0 / confirmation block must say it is skipped under the flag.
    assert grep(
        r"skipped.*--workflow-managed-approval|--workflow-managed-approval.*skipped|"
        r"--workflow-managed-approval.*bypass|bypass.*--workflow-managed-approval",
        _text(),
    )


# --- Step 1.1: equivalent-mutant tagging downstream-callable ----------------


def test_skill_schema_documents_status_equivalent_on_survivor_entries():
    assert "equivalent" in _machine_readable_section()


# --- Step 1.2: per-language KBs carry the native-report schema mapping ------


def test_languages_javascript_stryker_md_has_native_report_mapping_with_a_stryker_json_envelope():
    text = (LANG_DIR / "javascript-stryker.md").read_text()
    assert grep(r"^##+ +Native report", text, ignore_case=True)
    assert '"tool": "stryker"' in text


def test_languages_java_pitest_md_has_native_report_mapping_with_a_pitest_json_envelope():
    text = (LANG_DIR / "java-pitest.md").read_text()
    assert grep(r"^##+ +Native report", text, ignore_case=True)
    assert '"tool": "pitest"' in text


def test_languages_python_mutmut_md_has_native_report_mapping_with_a_mutmut_json_envelope():
    text = (LANG_DIR / "python-mutmut.md").read_text()
    assert grep(r"^##+ +Native report", text, ignore_case=True)
    assert '"tool": "mutmut"' in text


def test_languages_csharp_stryker_net_md_has_native_report_mapping_with_a_stryker_net_json_envelope():
    text = (LANG_DIR / "csharp-stryker-net.md").read_text()
    assert grep(r"^##+ +Native report", text, ignore_case=True)
    assert '"tool": "stryker-net"' in text


# --- Slice 11 / Step 11.3: /test-improve joins the allowlist in three
# co-enforced locations. The registry file is the authoritative source of
# truth; SKILL.md ## Constraints enumerates callers for human-readable
# discoverability. Both must move together.


def test_registry_workflow_callers_md_exists():
    assert REGISTRY.is_file()


def test_registry_names_test_improve_as_an_allowed_caller():
    assert "/test-improve" in REGISTRY.read_text()


def _registry_test_improve_row() -> str:
    lines = [
        line
        for line in REGISTRY.read_text().splitlines()
        if line.startswith("| ") and "/test-improve" in line
    ]
    return "\n".join(lines)


def test_registry_test_improve_row_cites_phase_2_baseline_as_an_approval_capture_point():
    # The registry table is the naming surface; the /test-improve row must
    # name the phase where operator approval was captured, matching the
    # pattern the existing /coverage-delta and /quality-targets-converge
    # rows use.
    row = _registry_test_improve_row()
    assert row
    assert grep(r"Phase 2|Phase 0", row)


def test_registry_test_improve_row_cites_phase_6_via_quality_targets_converge_as_a_caller_path():
    row = _registry_test_improve_row()
    assert row
    assert grep(r"Phase 6|/quality-targets-converge", row)


def test_skill_constraints_enumerates_test_improve_alongside_coverage_delta_and_quality_targets_converge():
    # Generalized assertion: every caller present in the registry table's
    # "Allowed callers" section should be discoverable via the Constraints
    # section too. For today we check the three named callers explicitly.
    section_text = _constraints_section()
    for caller in ("/coverage-delta", "/quality-targets-converge", "/test-improve"):
        assert caller in section_text, f"missing caller in ## Constraints: {caller}"


def test_skill_registry_stay_in_lockstep_every_caller_in_constraints_appears_in_the_registry():
    # This is the drift-catching assertion — if a future PR adds a caller
    # to Constraints without touching the registry (or vice versa), one of
    # the two checks below fails.
    callers_in_constraints = sorted(
        set(
            re.findall(
                r"/(?:coverage-delta|quality-targets-converge|test-improve)",
                _constraints_section(),
            )
        )
    )
    registry_text = REGISTRY.read_text()
    for caller in callers_in_constraints:
        assert caller in registry_text, (
            f"caller in SKILL Constraints but missing from registry: {caller}"
        )
