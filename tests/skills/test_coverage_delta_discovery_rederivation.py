"""Coverage for coverage-delta/SKILL.md Step 2/2a/5 (issue #1759, Slice 5,
Steps 5.1-5.2): re-deriving multi-project discovery fresh on every call
(never a frozen project/package list), applying `drift_check`'s hard-failure
rule the same way `coverage-baseline` does, printing
`measurement_basis_notice`'s result verbatim when non-`None`, and surfacing
`drift_check`'s `stale_warning_message` verbatim as a named, non-blocking
Step 5 (Report) warning line.

Content-guard tests grep the shipped SKILL.md prose; integration tests drive
the REAL Slice 1-3 (`coverage_config`) and Slice 2 (`coverage_discovery_dotnet`)
functions against synthesized `.sln`/`.csproj` fixtures, through the shared
flow-simulation helper in `coverage_delta_flow_helpers.py`.
"""

from __future__ import annotations

import sys

from coverage_baseline_flow_helpers import stub_dotnet
from coverage_delta_flow_helpers import (
    COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES,
    run_delta_flow,
)
from coverage_flow_shared import sln, write
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd

SKILL = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_2_section() -> str:
    return section(_text(), r"^### 2\. Re-run coverage", boundary_pattern=r"^### ")


def _step_2a_section() -> str:
    return section(
        _text(), r"^### 2a\. Multi-project re-derivation", boundary_pattern=r"^### "
    )


def _step_5_section() -> str:
    return section(_text(), r"^### 5\. Report", boundary_pattern=r"^## ")


TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""




# ---------------------------------------------------------------------------
# Content-guard: Step 2's narrowed tool-vs-list wording; Step 2a names both
# discovery scripts, links to the shared reference file, documents the
# hard-failure block and the measurement-basis notice; Step 5 documents the
# stale-exclusion warning.
# ---------------------------------------------------------------------------


def test_step_2_narrows_instruction_to_tool_never_project_list():
    step_2 = collapsed(_step_2_section())
    assert "the tool only, never the project/package list" in step_2


def test_step_2_documents_printing_measurement_basis_notice():
    step_2 = _step_2_section()
    assert grep(r"measurement_basis_notice", step_2)
    assert grep(r"bootstrapped_at", step_2)
    assert grep(r"captured_at", step_2)


def test_step_2a_names_both_discovery_scripts():
    step_2a = _step_2a_section()
    assert grep(r"coverage_discovery_dotnet", step_2a)
    assert grep(r"coverage_discovery_js", step_2a)


def test_step_2a_links_to_multi_project_discovery_reference():
    assert grep(
        r"\.\./coverage-baseline/references/multi-project-discovery\.md",
        _step_2a_section(),
    )


def test_step_2a_hard_failure_block_documented_as_distinct_and_verbatim():
    step_2a = _step_2a_section()
    assert grep(r"own distinct.*block", step_2a, ignore_case=True)
    assert grep(r"verbatim", step_2a, ignore_case=True)
    assert grep(r"Coverage capture stopped:", step_2a)
    # Negative: coverage-delta's OWN generic run-failure wording (Step 2)
    # must be absent from the hard-failure block itself.
    collapsed_step_2a = collapsed(step_2a)
    for phrase in COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES:
        assert phrase not in collapsed_step_2a


def test_step_2_generic_run_failure_banner_is_unchanged():
    """Step 2's pre-existing failure wording must still carry both named
    phrases verbatim — it is the fixture the negative assertion above
    compares against, and its own distinctness from Step 2a's hard-failure
    block depends on these two phrases never having been edited. This
    checks phrase presence, not a full byte-for-byte comparison of Step 2's
    text."""
    step_2 = collapsed(_step_2_section())
    for phrase in COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES:
        assert phrase in step_2


def test_step_5_documents_stale_warning_as_named_nonblocking_line():
    step_5 = _step_5_section()
    assert grep(r"stale_warning_message", step_5)
    assert grep(r"verbatim", step_5, ignore_case=True)
    assert grep(r"non-blocking", step_5, ignore_case=True)


def test_step_5_documents_format_active_exclusions_every_run():
    """Distinct from the stale-warning assertion above: Step 5 must also
    document printing `format_active_exclusions`'s result — informational,
    always-shown context about what is currently excluded and why, on
    EVERY run, not only when an exclusion goes stale."""
    step_5 = collapsed(_step_5_section())
    assert grep(r"format_active_exclusions", step_5)
    assert grep(r"verbatim", step_5, ignore_case=True)
    assert "every run" in step_5


# ---------------------------------------------------------------------------
# Integration: discovery never reuses a frozen list — a project unaccounted
# for on the second call hard-fails even though the first call succeeded.
# ---------------------------------------------------------------------------


def test_second_call_hard_fails_on_a_newly_unaccounted_project(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    project_c = "tests/ProjectC/ProjectC.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_c, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": []}}', encoding="utf-8"
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    # First call: discovery reports only project_a — matches config, succeeds.
    with stub_dotnet([project_a]):
        discovered_1 = cdd.discover_dotnet_projects(tmp_path)
    result_1 = run_delta_flow(
        discovered_1,
        config_path,
        baseline,
        {
            project_a: {
                "covered_statements": 10,
                "total_statements": 10,
                "covered_branches": 0,
                "total_branches": 0,
            }
        },
    )
    assert result_1.stopped is False

    # Second call: discovery now reports project_c too — never in config's
    # included/excluded — hard-fails even though nothing about the config
    # or the coverage tool changed between calls.
    with stub_dotnet([project_a, project_c]):
        discovered_2 = cdd.discover_dotnet_projects(tmp_path)
    result_2 = run_delta_flow(discovered_2, config_path, baseline)

    assert result_2.stopped is True
    assert project_c in result_2.hard_failure_message
    assert result_2.hard_failure_message.startswith("Coverage capture stopped:")
    for phrase in COVERAGE_DELTA_GENERIC_RUN_FAILURE_PHRASES:
        assert phrase not in result_2.hard_failure_message
    assert result_2.delta_written is False


# ---------------------------------------------------------------------------
# Integration: measurement-basis notice appears/disappears per
# measurement_basis_notice's own contract, called through the documented
# flow rather than re-derived comparison logic.
# ---------------------------------------------------------------------------


def test_basis_notice_appears_when_baseline_predates_bootstrap(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": [], '
        f'"bootstrapped_at": "2026-08-04T12:00:00Z"}}',
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    with stub_dotnet([project_a]):
        discovered = cdd.discover_dotnet_projects(tmp_path)
    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is False
    assert result.basis_notice is not None
    assert "predates multi-project discovery" in result.basis_notice
    assert "bootstrapped 2026-08-04T12:00:00Z" in result.basis_notice


def test_basis_notice_absent_once_a_fresh_baseline_is_captured(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": [], '
        f'"bootstrapped_at": "2026-01-01T00:00:00Z"}}',
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    with stub_dotnet([project_a]):
        discovered = cdd.discover_dotnet_projects(tmp_path)
    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is False
    assert result.basis_notice is None


# ---------------------------------------------------------------------------
# Integration: a stale exclusion surfaces as a specific, non-blocking
# warning and the run still completes.
# ---------------------------------------------------------------------------


def test_stale_exclusion_is_nonblocking_and_run_still_completes(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": '
        '[{"path": "tests/ProjectB/ProjectB.csproj", "reason": "all pending stubs"}]}',
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    # project_b no longer appears in discovery at all — a stale exclusion.
    with stub_dotnet([project_a]):
        discovered = cdd.discover_dotnet_projects(tmp_path)
    delta_path = tmp_path / "coverage-delta.json"
    result = run_delta_flow(
        discovered,
        config_path,
        baseline,
        {
            project_a: {
                "covered_statements": 5,
                "total_statements": 10,
                "covered_branches": 0,
                "total_branches": 0,
            }
        },
        delta_path=delta_path,
    )

    assert result.stopped is False
    assert result.stale_warning_message is not None
    assert "tests/ProjectB/ProjectB.csproj" in result.stale_warning_message
    assert "all pending stubs" in result.stale_warning_message
    assert result.delta_written is True
    assert delta_path.is_file()
