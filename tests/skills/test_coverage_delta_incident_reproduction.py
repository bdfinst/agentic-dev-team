"""Reproduces issue #1759's actual incident shape as a two-timepoint fixture
(Slice 5, Step 5.3): an excluded test project stays visible, with its
original exclusion reason, across two sequential `/coverage-delta`-shaped
runs — even after the excluded project gains real, non-stub assertions
between the two runs. `coverage-delta`'s own re-derivation (Step 2a) never
auto-flags the reason as stale on that basis; only a path's *absence* from
fresh discovery does (see `coverage_config.drift_check`'s
`stale_exclusions`).

The T1->T2 mutation that matters is `project_stubs`'s COVERAGE REPORT gaining
a genuinely different, nonzero value at T2 (representing its 81 new real
assertions) — NOT the `.csproj` file content, which `_classify_project` never
inspects (a comment inserted into it is narrative flavor only, invisible to
the code under test). `coverage-config.json`'s exclusion entry for
`project_stubs` stays byte-for-byte unchanged between T1 and T2. The test
asserts `result_t2.merged` equals `weighted_merge` over the included
project(s) alone, and separately computes what `weighted_merge` WOULD
produce if `project_stubs` were wrongly included — making the incident's
~30x-style underreported-delta gap concrete and assertable rather than only
narrated.

Drives the REAL discover_* -> drift_check -> weighted_merge chain through
`coverage_delta_flow_helpers.run_delta_flow`, reading an existing
`coverage-config.json`/baseline rather than bootstrapping — this is the
worker's actual runtime shape, not a re-derived simulation.
"""

from __future__ import annotations

import sys

import pytest
from coverage_baseline_flow_helpers import stub_dotnet
from coverage_delta_flow_helpers import run_delta_flow
from coverage_flow_shared import sln, write
from skill_doc_helpers import PLUGIN_ROOT

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd
from coverage_config import weighted_merge

TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""


def test_incident_shape_exclusion_and_reason_stay_visible_across_both_timepoints(
    tmp_path,
):
    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"  # real, accounted-for test project
    project_stubs = "tests/ProjectStubs/ProjectStubs.csproj"  # excluded, all-pending-stubs

    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_stubs, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": '
        f'[{{"path": "{project_stubs}", "reason": "all pending stubs"}}]}}',
        encoding="utf-8",
    )
    baseline = {
        "captured_at": "2026-08-04T12:00:00Z",
        "line_pct": 41.2,
        "branch_pct": 28.7,
    }

    # T1: the excluded project's fixture is all pending stubs. Discovery
    # still finds it on disk (classified TEST — it still declares the
    # Microsoft.NET.Test.Sdk reference), but the run's coverage report only
    # covers the accounted-for project, project_a.
    with stub_dotnet([project_a, project_stubs]):
        discovered_t1 = cdd.discover_dotnet_projects(tmp_path)

    result_t1 = run_delta_flow(
        discovered_t1,
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
    )

    assert result_t1.stopped is False
    excluded_t1 = {e["path"]: e for e in result_t1.config["excluded"]}
    assert project_stubs in excluded_t1
    assert excluded_t1[project_stubs]["reason"] == "all pending stubs"
    # T1's exclusion is not flagged stale — the project is still discovered.
    assert result_t1.stale_warning_message is None
    # The exclusion and its reason are visible in genuinely rendered output
    # (not a round-trip of what this test itself wrote into config_path).
    assert result_t1.active_exclusions_message is not None
    assert project_stubs in result_t1.active_exclusions_message
    assert "all pending stubs" in result_t1.active_exclusions_message

    # T2: the SAME project now has real assertions added to its fixture
    # content (narrative only — `_classify_project` never inspects test-file
    # content, so this alone changes nothing observable to the code under
    # test). Its coverage-config.json exclusion entry is UNCHANGED (this
    # test never rewrites config_path between T1 and T2) — the mutation
    # that actually matters is project_stubs's coverage report gaining a
    # real, nonzero value at T2, representing its 81 new real assertions.
    write(tmp_path / project_stubs, TEST_CSPROJ.replace(
        "</Project>",
        "  <!-- real assertions now exist in this project's test files -->\n</Project>",
    ))

    with stub_dotnet([project_a, project_stubs]):
        discovered_t2 = cdd.discover_dotnet_projects(tmp_path)

    project_a_report_t2 = {
        "covered_statements": 5,
        "total_statements": 10,
        "covered_branches": 0,
        "total_branches": 0,
    }
    project_stubs_report_t2 = {
        "covered_statements": 60,
        "total_statements": 81,
        "covered_branches": 20,
        "total_branches": 30,
    }

    result_t2 = run_delta_flow(
        discovered_t2,
        config_path,
        baseline,
        {
            project_a: project_a_report_t2,
            # project_stubs stays excluded, but its report is supplied here
            # exactly as coverage-delta's own Step 2a would supply it for
            # every discovered project — proving the drop below is
            # `weighted_merge` correctly honoring the exclusion, not this
            # test never having exercised project_stubs's contribution.
            project_stubs: project_stubs_report_t2,
        },
    )

    assert result_t2.stopped is False
    excluded_t2 = {e["path"]: e for e in result_t2.config["excluded"]}
    # The exclusion and its ORIGINAL reason are still reported at T2 —
    # gaining real assertions did not change or remove either.
    assert project_stubs in excluded_t2
    assert excluded_t2[project_stubs]["reason"] == "all pending stubs"
    # drift_check does NOT auto-flag the reason as stale just because the
    # project's content changed — only a path's absence from discovery
    # triggers staleness (project_stubs is still discovered at T2).
    assert result_t2.stale_warning_message is None
    assert result_t2.stale_exclusions == []
    assert result_t2.config["excluded"] == result_t1.config["excluded"]
    # The exclusion stays visible in genuinely rendered output at T2 too —
    # gaining real assertions changed neither the exclusion nor its
    # visibility.
    assert result_t2.active_exclusions_message is not None
    assert project_stubs in result_t2.active_exclusions_message
    assert "all pending stubs" in result_t2.active_exclusions_message

    # The concrete gap: result_t2.merged is EXACTLY what weighted_merge
    # produces over the included project(s) alone — project_stubs's 81 real
    # assertions never reach the denominator/numerator despite a report
    # being available for it.
    assert result_t2.merged == weighted_merge([project_a_report_t2])

    # What the merged figure WOULD be if project_stubs were wrongly
    # included — the ~30x-style gap the incident describes, made assertable
    # rather than just narrated. Branch coverage is where the drop is most
    # dramatic: project_a alone reports total_branches=0 (no branch signal
    # at all, so branch_pct is None), while project_stubs alone would
    # contribute a real, measured 66.67% branch coverage — a signal that is
    # currently silently and entirely dropped, not merely diluted.
    would_be_merged_if_wrongly_included = weighted_merge(
        [project_a_report_t2, project_stubs_report_t2]
    )
    assert result_t2.merged["branch_pct"] is None
    assert would_be_merged_if_wrongly_included["branch_pct"] == pytest.approx(
        66.666, abs=0.01
    )
    assert would_be_merged_if_wrongly_included["line_pct"] == pytest.approx(
        71.42, abs=0.01
    )
    assert would_be_merged_if_wrongly_included != result_t2.merged
