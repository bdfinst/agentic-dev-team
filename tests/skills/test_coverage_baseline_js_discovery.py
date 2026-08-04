"""Coverage for coverage-baseline/SKILL.md Step 1a's JS/TS row (issue #1759,
Slice 4, Step 4.2): wiring `coverage_discovery_js.discover_js_packages` into
the documented bootstrap -> drift-check -> weighted-merge flow, mirroring
test_coverage_baseline_dotnet_discovery.py's .NET coverage.

The shared mechanics reference file (`references/multi-project-discovery.md`)
and the JS/TS row of Step 1a were both already written in Step 4.1's SKILL.md
edit — the discover -> bootstrap/drift-check -> merge -> persist mechanics
are genuinely identical prose for both stacks (only the discovery step
differs), so the plan's own "extract the shared mechanics once" instruction
(Step 4.2 IMPLEMENT) was already satisfied then rather than split
artificially across two edits. This file adds the JS/TS-specific content-
guard and integration coverage Step 4.2 calls for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from coverage_baseline_flow_helpers import (
    GENERIC_COVERAGE_RUN_FAILURE_PHRASES,
    run_baseline_flow,
)
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_js as cdj  # noqa: E402

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_1a_section() -> str:
    return section(_text(), r"^### 1a\. Multi-project discovery", boundary_pattern=r"^### ")


# ---------------------------------------------------------------------------
# package.json fixture helpers (mirroring
# plugins/dev-team/tests/scripts/test_coverage_discovery_js.py)
# ---------------------------------------------------------------------------


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def pkg(root: Path, data: dict) -> None:
    write(root / "package.json", data)


TEST_PKG = {
    "name": "test-pkg",
    "scripts": {"test": "jest"},
    "devDependencies": {"jest": "^29"},
}


# ---------------------------------------------------------------------------
# Content-guard: Step 1a names the JS/TS discovery script and the reference
# file, mirroring Step 4.1's dotnet assertions.
# ---------------------------------------------------------------------------


def test_step_1a_names_js_discovery_script():
    assert grep(r"coverage_discovery_js\.py", _step_1a_section())


def test_step_1a_links_to_multi_project_discovery_reference():
    assert grep(r"references/multi-project-discovery\.md", _step_1a_section())


def test_multi_project_discovery_reference_file_exists():
    ref = SKILL.parent / "references" / "multi-project-discovery.md"
    assert ref.is_file()


def test_both_rows_link_to_the_shared_reference_file():
    """Both the .csproj and package.json rows individually link to Step 1a
    (the shared reference file's anchor point) on their own table row —
    extracted line-by-line, not grepped across the whole file, so this
    actually fails if either row drops its link while the other keeps it."""
    step_1a_anchor = r"#1a-multi-project-discovery"
    lines = _text().splitlines()

    csproj_line = next(line for line in lines if line.startswith("| `*.csproj` |"))
    package_json_line = next(
        line for line in lines if line.startswith("| `package.json` (JS/TS) |")
    )

    assert grep(step_1a_anchor, csproj_line)
    assert grep(step_1a_anchor, package_json_line)


def test_step_1a_documents_workspace_signal_precedence_sources():
    step_1a = _step_1a_section()
    assert grep(r"workspaces", step_1a)
    assert grep(r"pnpm-workspace\.yaml", step_1a)
    assert grep(r"lerna\.json", step_1a)


def test_step_1a_js_hard_failure_block_documented_as_distinct_from_generic_banner():
    step_1a = _step_1a_section()
    assert grep(r"own distinct.*block", step_1a, ignore_case=True)
    assert grep(r"[Nn]ever.*fold", step_1a)
    collapsed_step_1a = collapsed(step_1a)
    for phrase in GENERIC_COVERAGE_RUN_FAILURE_PHRASES:
        assert phrase in collapsed_step_1a  # quoted verbatim as wording NOT to reuse


# ---------------------------------------------------------------------------
# Integration: merge scenario — two real test packages of differing size.
# ---------------------------------------------------------------------------


def test_js_merge_scenario_produces_weighted_merged_percentage(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "b", TEST_PKG)

    discovered = cdj.discover_js_packages(tmp_path)

    config_path = tmp_path / "coverage-config.json"
    reports = {
        "packages/a": {
            "covered_statements": 10,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        },
        "packages/b": {
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
        "workspace",
        reports,
        baseline_path=baseline_path,
    )

    assert result.stopped is False
    assert result.merged["line_pct"] == pytest.approx(50.5, abs=0.01)
    assert sorted(result.config["included"]) == ["packages/a", "packages/b"]
    assert config_path.is_file()
    assert result.baseline_written is True


# ---------------------------------------------------------------------------
# Integration: unaccounted package hard-fails without the generic banner.
# ---------------------------------------------------------------------------


def test_js_unaccounted_package_hard_fails_without_generic_banner_text(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "c", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        json.dumps({"included": ["packages/a"], "excluded": []}), encoding="utf-8"
    )

    baseline_path = tmp_path / "baseline-coverage.json"
    original_baseline = (
        '{"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}'
    )
    baseline_path.write_text(original_baseline, encoding="utf-8")

    discovered = cdj.discover_js_packages(tmp_path)

    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "workspace",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert "packages/c" in result.message
    assert result.message.startswith("Coverage capture stopped:")
    # Remediation text: the exact actionable instruction drift_check's
    # hard_failure_message produces for an unaccounted package.
    assert '"included"' in result.message
    assert '"excluded"' in result.message
    assert '"reason"' in result.message
    assert 'Add each to "included"' in result.message
    for phrase in GENERIC_COVERAGE_RUN_FAILURE_PHRASES:
        assert phrase not in result.message
    assert result.baseline_written is False
    # The pre-existing baseline is untouched — the flow never reached the
    # write step. If the early-return-on-hard-failure were deleted, the
    # flow would fall through to the merge+write step and change these
    # bytes, so this assertion is genuinely falsifiable.
    assert baseline_path.read_text(encoding="utf-8") == original_baseline


# ---------------------------------------------------------------------------
# Integration: bootstrap scenario — pre-existing baseline, no config yet.
# ---------------------------------------------------------------------------


def test_js_bootstrap_scenario_prints_notice_and_writes_fresh_baseline(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    baseline_path = tmp_path / "baseline-coverage.json"
    original_baseline = (
        '{"captured_at": "2026-01-01T00:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}'
    )
    baseline_path.write_text(original_baseline, encoding="utf-8")

    config_path = tmp_path / "coverage-config.json"
    discovered = cdj.discover_js_packages(tmp_path)

    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "workspace",
        {"packages/a": {
            "covered_statements": 5,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        }},
        baseline_path=baseline_path,
    )

    assert result.stopped is False
    assert "did not exist; created it from fresh discovery" in result.notice
    assert config_path.is_file()
    assert result.config["included"] == ["packages/a"]
    assert result.baseline_written is True
    # The flow reached the persist step on this success path — the
    # previously-captured fixture value is overwritten with the fresh
    # measurement, not left byte-for-byte unchanged.
    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written == {"line_pct": 50.0, "branch_pct": None}
    assert baseline_path.read_text(encoding="utf-8") != original_baseline


# Note: a "genuine tool crash still shows the unchanged generic banner" test
# was removed here (issue #1759 Slice 4 review) — it asserted two facts with
# no causal link between them. The error-signal half is already covered by
# test_pnpm_workspace_yaml_flow_style_array_is_discovery_error in
# plugins/dev-team/tests/scripts/test_coverage_discovery_js.py (the exact
# same fixture shape); the banner-presence half is already covered by
# test_generic_coverage_run_failure_banner_is_unchanged in
# test_coverage_baseline_dotnet_discovery.py (same shared SKILL.md text).
