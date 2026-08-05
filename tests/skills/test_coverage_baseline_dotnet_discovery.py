"""Coverage for coverage-baseline/SKILL.md Step 1a's .NET row (issue #1759,
Slice 4, Step 4.1): wiring `coverage_discovery_dotnet.discover_dotnet_projects`
into the documented bootstrap -> drift-check -> weighted-merge flow, with the
hard-failure block kept textually distinct from Step 3's pre-existing
generic coverage-run-failure wording.

Content-guard tests grep the shipped SKILL.md prose; integration tests drive
the REAL Slice 1-3 (`coverage_config`) and Slice 2 (`coverage_discovery_dotnet`)
functions against synthesized `.sln`/`.csproj` fixtures, through the shared
flow-simulation helper in `coverage_baseline_flow_helpers.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from coverage_baseline_flow_helpers import (
    GENERIC_COVERAGE_RUN_FAILURE_PHRASES,
    run_baseline_flow,
    stub_dotnet,
)
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_1a_section() -> str:
    return section(_text(), r"^### 1a\. Multi-project discovery", boundary_pattern=r"^### ")


def _step_5_section() -> str:
    return section(_text(), r"^### 5\. Persist the baseline", boundary_pattern=r"^### ")


# ---------------------------------------------------------------------------
# .csproj/.sln fixture helpers (mirroring
# plugins/dev-team/tests/scripts/test_coverage_discovery_dotnet.py)
# ---------------------------------------------------------------------------


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sln(repo_root: Path, name: str = "App.sln") -> None:
    write(repo_root / name, "Microsoft Visual Studio Solution File\n")


TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""
NOT_TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType></PropertyGroup>
</Project>
"""


# ---------------------------------------------------------------------------
# Content-guard: Step 1a names the .NET discovery script and the reference
# file, and the hard-failure block is documented as its own distinct block.
# ---------------------------------------------------------------------------


def test_step_1a_names_dotnet_discovery_script():
    assert grep(r"coverage_discovery_dotnet\.py", _step_1a_section())


def test_step_1a_links_to_multi_project_discovery_reference():
    assert grep(
        r"references/multi-project-discovery\.md", _step_1a_section()
    )


def test_multi_project_discovery_reference_file_exists():
    ref = SKILL.parent / "references" / "multi-project-discovery.md"
    assert ref.is_file()


def test_step_1a_hard_failure_block_documented_as_distinct_from_generic_banner():
    step_1a = _step_1a_section()
    assert grep(r"own distinct.*block", step_1a, ignore_case=True)
    assert grep(r"[Nn]ever.*fold", step_1a)
    collapsed_step_1a = collapsed(step_1a)
    for phrase in GENERIC_COVERAGE_RUN_FAILURE_PHRASES:
        assert phrase in collapsed_step_1a  # quoted verbatim as wording NOT to reuse


def test_step_5_documents_persisting_coverage_config():
    step_5 = _step_5_section()
    assert grep(r"coverage-config\.json", step_5)
    assert grep(r"atomic_write_json", step_5)


def test_generic_coverage_run_failure_banner_is_unchanged():
    """Step 3's pre-existing failure wording must still carry both named
    phrases verbatim — it is the fixture the negative assertions below
    compare against, and its own distinctness from the new hard-failure
    block depends on these two phrases never having been edited. This
    checks phrase presence, not a full byte-for-byte comparison of Step 3's
    text."""
    step_3 = collapsed(section(_text(), r"^### 3\. Run coverage", boundary_pattern=r"^### "))
    for phrase in GENERIC_COVERAGE_RUN_FAILURE_PHRASES:
        assert phrase in step_3


# ---------------------------------------------------------------------------
# Integration: merge scenario — two real test projects of differing size.
# ---------------------------------------------------------------------------


def test_dotnet_merge_scenario_produces_weighted_merged_percentage(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    project_b = "tests/ProjectB/ProjectB.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_b, TEST_CSPROJ)

    with stub_dotnet([project_a, project_b]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    config_path = tmp_path / "coverage-config.json"
    reports = {
        project_a: {
            "covered_statements": 10,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        },
        project_b: {
            "covered_statements": 500,
            "total_statements": 1000,
            "covered_branches": 0,
            "total_branches": 0,
        },
    }

    baseline_path = tmp_path / "baseline-coverage.json"
    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "solution",
        reports,
        baseline_path=baseline_path,
    )

    assert result.stopped is False
    assert result.merged["line_pct"] == pytest.approx(50.5, abs=0.01)
    assert sorted(result.config["included"]) == sorted([project_a, project_b])
    assert config_path.is_file()  # bootstrapped by the flow
    assert result.baseline_written is True


# ---------------------------------------------------------------------------
# Integration: unaccounted project blocks capture with drift_check's exact
# message, and never surfaces Step 3's generic banner wording.
# ---------------------------------------------------------------------------


def test_dotnet_unaccounted_project_hard_fails_without_generic_banner_text(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    project_c = "tests/ProjectC/ProjectC.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_c, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": []}}', encoding="utf-8"
    )

    baseline_path = tmp_path / "baseline-coverage.json"
    original_baseline = (
        '{"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}'
    )
    baseline_path.write_text(original_baseline, encoding="utf-8")

    with stub_dotnet([project_a, project_c]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "solution",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert project_c in result.message
    assert result.message.startswith("Coverage capture stopped:")
    # Remediation text: the exact actionable instruction drift_check's
    # hard_failure_message produces for an unaccounted project.
    assert '"included"' in result.message
    assert '"excluded"' in result.message
    assert '"reason"' in result.message
    assert 'Add each to "included"' in result.message
    for phrase in GENERIC_COVERAGE_RUN_FAILURE_PHRASES:
        assert phrase not in result.message
    assert result.baseline_written is False
    # The pre-existing baseline is untouched (bytes identical) — the flow
    # never reached the write step. If the early-return-on-hard-failure were
    # deleted, the flow would fall through to the merge+write step and
    # change these bytes, so this assertion is genuinely falsifiable.
    assert baseline_path.read_text(encoding="utf-8") == original_baseline


# Note: a "genuine tool crash still shows the unchanged generic banner" test
# was removed here (issue #1759 Slice 4 review) — it asserted two facts with
# no causal link between them. The error-signal half is already covered by
# test_dotnet_not_on_path_is_tool_missing_discovery_error in
# plugins/dev-team/tests/scripts/test_coverage_discovery_dotnet.py; the
# banner-presence half is already covered by
# test_generic_coverage_run_failure_banner_is_unchanged above.


# ---------------------------------------------------------------------------
# Integration: bootstrap scenario — pre-existing baseline, no config yet.
# ---------------------------------------------------------------------------


def test_dotnet_bootstrap_scenario_prints_notice_and_writes_fresh_baseline(tmp_path):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)

    baseline_path = tmp_path / "baseline-coverage.json"
    original_baseline = (
        '{"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}'
    )
    baseline_path.write_text(original_baseline, encoding="utf-8")

    config_path = tmp_path / "coverage-config.json"
    assert not config_path.exists()

    with stub_dotnet([project_a]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "solution",
        {project_a: {
            "covered_statements": 5,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        }},
        baseline_path=baseline_path,
    )

    assert result.stopped is False
    assert result.notice is not None
    assert "did not exist; created it from fresh discovery" in result.notice
    assert config_path.is_file()
    assert result.config["included"] == [project_a]
    assert result.baseline_written is True
    # The flow reached the persist step on this success path — the
    # previously-captured fixture value is overwritten with the fresh
    # measurement, not left byte-for-byte unchanged.
    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written == {"line_pct": 50.0, "branch_pct": None}
    assert baseline_path.read_text(encoding="utf-8") != original_baseline
