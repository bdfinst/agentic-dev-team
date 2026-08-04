"""Content-guard + integration tests for multi-project coverage wiring (#1783).

The content guards pin `/coverage-baseline`'s prose contract; the integration
tests drive the real Slice 1-3 functions against synthesized fixtures, so the
prose and the code it points at cannot drift apart silently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SKILL = _PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"
_REFERENCE = (
    _PLUGIN_ROOT
    / "skills"
    / "coverage-baseline"
    / "references"
    / "multi-project-discovery.md"
)

sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))

import coverage_config as cc
import coverage_discovery_dotnet as dnd
import coverage_discovery_js as jsd

_SKILL_TEXT = _SKILL.read_text(encoding="utf-8")
_REFERENCE_TEXT = _REFERENCE.read_text(encoding="utf-8")

_DRIFT_BLOCK = "## Coverage discovery drift"
_RUN_FAILURE_BLOCK = "## Coverage run failed"


def _section(text: str, heading_pattern: str) -> str:
    """Return one `###` section's body."""
    match = re.search(heading_pattern, text, flags=re.MULTILINE)
    assert match is not None, f"section {heading_pattern!r} not found"
    rest = text[match.end() :]
    next_heading = re.search(r"^### ", rest, flags=re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


# ---------------------------------------------------------------------------
# Content guards — Step 1 rows
# ---------------------------------------------------------------------------


def test_the_reference_file_exists_and_is_linked_from_the_skill() -> None:
    assert _REFERENCE.is_file()
    assert "references/multi-project-discovery.md" in _SKILL_TEXT


def test_the_dotnet_row_invokes_dotnet_discovery() -> None:
    rows = [line for line in _SKILL_TEXT.splitlines() if line.strip().startswith("|")]
    sln_rows = [row for row in rows if ".sln" in row]

    assert len(sln_rows) == 1
    assert "coverage_discovery_dotnet.py" in sln_rows[0]
    # Gated on the solution actually being present, so a lone .csproj is untouched.
    assert "Solution present" in sln_rows[0]


def test_the_js_row_invokes_js_discovery_only_for_workspace_repos() -> None:
    rows = [line for line in _SKILL_TEXT.splitlines() if line.strip().startswith("|")]
    js_rows = [row for row in rows if "package.json` (JS/TS)" in row]

    assert len(js_rows) == 1
    assert "coverage_discovery_js.py" in js_rows[0]
    for signal in ("workspaces", "pnpm-workspace.yaml", "lerna.json"):
        assert signal in js_rows[0]
    assert "Single package" in js_rows[0]


def test_no_other_manifest_row_invokes_discovery() -> None:
    rows = [
        line
        for line in _SKILL_TEXT.splitlines()
        if line.strip().startswith("|")
        and not re.fullmatch(r"\|[\s:|-]+\|", line.strip())
    ]
    header, *body = rows
    assert "Manifest" in header

    for row in body:
        if ".sln" in row or "package.json` (JS/TS)" in row:
            continue
        assert "coverage_discovery" not in row


def test_discovery_invocations_are_plugin_root_relative_and_quoted() -> None:
    for script in ("coverage_discovery_dotnet.py", "coverage_discovery_js.py"):
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/{script}"' in _SKILL_TEXT


# ---------------------------------------------------------------------------
# Content guards — Step 1a flow
# ---------------------------------------------------------------------------


def test_the_multi_project_section_names_the_whole_flow_in_order() -> None:
    section = _section(_SKILL_TEXT, r"^### 1a\. ")

    positions = [
        section.index(needle)
        for needle in ("load_or_bootstrap", "drift_check", "weighted_merge")
    ]
    assert positions == sorted(positions)


def test_the_multi_project_section_pins_the_config_path() -> None:
    section = _section(_SKILL_TEXT, r"^### 1a\. ")

    assert (
        ".dev-team-reports/<workflow>/<slug>/data/coverage-config.json" in section
    )


def test_the_multi_project_section_forbids_a_simple_average() -> None:
    section = _section(_SKILL_TEXT, r"^### 1a\. ")

    assert "never a simple average" in section


def test_a_drift_hard_failure_writes_no_baseline() -> None:
    section = _section(_SKILL_TEXT, r"^### 1a\. ")

    assert _DRIFT_BLOCK in section
    assert "no baseline written" in section
    assert "Write no baseline" in section


def test_single_manifest_repos_skip_discovery_entirely() -> None:
    section = _section(_SKILL_TEXT, r"^### 1a\. ")

    assert "single-manifest repo skips this section entirely" in section
    assert "no `coverage-config.json`" in section


# ---------------------------------------------------------------------------
# Content guards — the two failure blocks stay distinct, in both directions
# ---------------------------------------------------------------------------


def test_the_drift_block_is_not_inside_the_generic_run_failure_step() -> None:
    run_coverage = _section(_SKILL_TEXT, r"^### \d+\. Run coverage")

    assert _RUN_FAILURE_BLOCK in run_coverage
    # Negative assertion: the drift block must not appear as the run-failure banner.
    assert f"```text\n{_DRIFT_BLOCK}" not in run_coverage


def test_the_generic_run_failure_block_is_not_inside_the_discovery_step() -> None:
    discovery = _section(_SKILL_TEXT, r"^### 1a\. ")

    assert f"```text\n{_RUN_FAILURE_BLOCK}" not in discovery


def test_the_two_failure_block_headings_are_different_strings() -> None:
    assert _DRIFT_BLOCK != _RUN_FAILURE_BLOCK
    assert _SKILL_TEXT.count(f"```text\n{_DRIFT_BLOCK}") == 1
    assert _SKILL_TEXT.count(f"```text\n{_RUN_FAILURE_BLOCK}") == 1


def test_the_run_coverage_step_says_the_two_are_never_folded_together() -> None:
    run_coverage = _section(_SKILL_TEXT, r"^### \d+\. Run coverage")

    assert "never folded together in either direction" in run_coverage


# ---------------------------------------------------------------------------
# Content guards — the reference file
# ---------------------------------------------------------------------------


def test_the_reference_documents_both_stacks_markers() -> None:
    assert "Microsoft.NET.Test.Sdk" in _REFERENCE_TEXT
    for runner in ("jest", "vitest", "mocha", "nyc", "c8"):
        assert runner in _REFERENCE_TEXT


def test_the_reference_documents_the_known_limitations() -> None:
    for limitation in (
        "Directory.Packages.props",
        "GlobalPackageReference",
        "pnpm-workspace.yaml",
        "#1765",
    ):
        assert limitation in _REFERENCE_TEXT


def test_the_reference_records_exact_string_path_identity() -> None:
    assert "exact, unmodified string match" in _REFERENCE_TEXT
    assert "no cross-stack normalization" in _REFERENCE_TEXT


def test_the_reference_records_the_superseded_1759_script() -> None:
    assert "discover_coverage_projects.py" in _REFERENCE_TEXT
    assert "coverage-delta" in _REFERENCE_TEXT


# ---------------------------------------------------------------------------
# Integration — the real Slice 1-3 functions against synthesized fixtures
# ---------------------------------------------------------------------------

_MARKER = '<PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />'


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _csproj(*refs: str) -> str:
    body = "\n".join(f"    {ref}" for ref in refs)
    return f'<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n{body}\n  </ItemGroup>\n</Project>\n'


def _dotnet_solution(root: Path, projects: dict[str, str]) -> None:
    _write(root / "App.sln", "Microsoft Visual Studio Solution File\n")
    for rel, content in projects.items():
        _write(root / rel, content)


@pytest.fixture
def stub_sln_list(monkeypatch: pytest.MonkeyPatch):
    def _stub(*rel_paths: str) -> None:
        monkeypatch.setattr(dnd, "run_dotnet_sln_list", lambda _sln: list(rel_paths))

    return _stub


def _js_workspace(root: Path, packages: dict[str, dict]) -> None:
    _write(
        root / "package.json",
        json.dumps({"name": "monorepo", "workspaces": ["packages/*"]}),
    )
    for rel, manifest in packages.items():
        _write(root / "packages" / rel / "package.json", json.dumps(manifest))


_JS_TEST_MANIFEST = {
    "name": "pkg",
    "scripts": {"test": "vitest run --coverage"},
    "devDependencies": {"vitest": "^2.0.0"},
}


def test_dotnet_baseline_merges_two_projects_into_one_weighted_number(
    tmp_path: Path, stub_sln_list
) -> None:
    _dotnet_solution(
        tmp_path,
        {
            "tests/Small.Tests/Small.Tests.csproj": _csproj(_MARKER),
            "tests/Large.Tests/Large.Tests.csproj": _csproj(_MARKER),
            "src/App/App.csproj": _csproj(),
        },
    )
    stub_sln_list(
        "tests/Small.Tests/Small.Tests.csproj",
        "tests/Large.Tests/Large.Tests.csproj",
        "src/App/App.csproj",
    )
    discovered = dnd.discover(tmp_path)
    config_path = tmp_path / "data" / "coverage-config.json"

    loaded = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")
    drift = cc.drift_check(loaded.config, discovered)
    merged = cc.weighted_merge(
        [
            {
                "path": "tests/Small.Tests/Small.Tests.csproj",
                "line_pct": 100.0,
                "statements_total": 10,
                "branch_pct": None,
                "branches_total": 0,
            },
            {
                "path": "tests/Large.Tests/Large.Tests.csproj",
                "line_pct": 50.0,
                "statements_total": 1000,
                "branch_pct": None,
                "branches_total": 0,
            },
        ]
    )

    assert drift.ok is True
    assert loaded.config["included"] == [
        "tests/Large.Tests/Large.Tests.csproj",
        "tests/Small.Tests/Small.Tests.csproj",
    ]
    # A simple average would report 75.0 — the #1759 shape.
    assert merged["line_pct"] == pytest.approx(50.5, abs=0.01)


def test_js_baseline_merges_two_packages_into_one_weighted_number(
    tmp_path: Path,
) -> None:
    _js_workspace(
        tmp_path,
        {
            "small": _JS_TEST_MANIFEST,
            "large": _JS_TEST_MANIFEST,
            "docs": {"name": "docs", "scripts": {"build": "tsc"}},
        },
    )
    discovered = jsd.discover(tmp_path)
    config_path = tmp_path / "data" / "coverage-config.json"

    loaded = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")
    drift = cc.drift_check(loaded.config, discovered)
    merged = cc.weighted_merge(
        [
            {
                "path": "packages/small",
                "line_pct": 100.0,
                "statements_total": 10,
                "branch_pct": 100.0,
                "branches_total": 4,
            },
            {
                "path": "packages/large",
                "line_pct": 50.0,
                "statements_total": 1000,
                "branch_pct": 25.0,
                "branches_total": 400,
            },
        ]
    )

    assert drift.ok is True
    assert loaded.config["included"] == ["packages/large", "packages/small"]
    assert merged["line_pct"] == pytest.approx(50.5, abs=0.01)
    assert merged["branch_pct"] == pytest.approx(25.74, abs=0.01)


def test_an_unaccounted_project_hard_fails_and_no_baseline_is_written(
    tmp_path: Path, stub_sln_list
) -> None:
    data_dir = tmp_path / "data"
    config_path = data_dir / "coverage-config.json"
    baseline_path = data_dir / "baseline-coverage.json"
    cc.atomic_write_json(
        config_path,
        {
            "included": ["tests/Old.Tests/Old.Tests.csproj"],
            "excluded": [],
            "bootstrapped_at": "2026-01-01T00:00:00Z",
        },
    )
    _dotnet_solution(
        tmp_path,
        {
            "tests/Old.Tests/Old.Tests.csproj": _csproj(_MARKER),
            "tests/New.Tests/New.Tests.csproj": _csproj(_MARKER),
        },
    )
    stub_sln_list(
        "tests/Old.Tests/Old.Tests.csproj", "tests/New.Tests/New.Tests.csproj"
    )
    discovered = dnd.discover(tmp_path)

    loaded = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")
    drift = cc.drift_check(loaded.config, discovered)

    assert loaded.bootstrapped is False
    assert drift.ok is False
    assert any("tests/New.Tests/New.Tests.csproj" in error for error in drift.errors)
    assert not baseline_path.exists()


def test_a_conflicting_config_entry_hard_fails(tmp_path: Path, stub_sln_list) -> None:
    config_path = tmp_path / "data" / "coverage-config.json"
    cc.atomic_write_json(
        config_path,
        {
            "included": ["tests/A.Tests/A.Tests.csproj"],
            "excluded": [
                {"path": "tests/A.Tests/A.Tests.csproj", "reason": "also excluded"}
            ],
            "bootstrapped_at": "2026-01-01T00:00:00Z",
        },
    )
    _dotnet_solution(tmp_path, {"tests/A.Tests/A.Tests.csproj": _csproj(_MARKER)})
    stub_sln_list("tests/A.Tests/A.Tests.csproj")
    discovered = dnd.discover(tmp_path)

    loaded = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")
    drift = cc.drift_check(loaded.config, discovered)

    assert drift.ok is False
    assert any("both 'included' and 'excluded'" in error for error in drift.errors)


def test_a_preexisting_baseline_with_no_config_bootstraps_without_changing_it(
    tmp_path: Path, stub_sln_list
) -> None:
    data_dir = tmp_path / "data"
    baseline = {
        "captured_at": "2026-07-01T09:30:00Z",
        "tool": "coverlet",
        "line_pct": 41.2,
        "branch_pct": 28.7,
    }
    cc.atomic_write_json(data_dir / "baseline-coverage.json", baseline)
    _dotnet_solution(tmp_path, {"tests/A.Tests/A.Tests.csproj": _csproj(_MARKER)})
    stub_sln_list("tests/A.Tests/A.Tests.csproj")
    discovered = dnd.discover(tmp_path)

    loaded = cc.load_or_bootstrap(
        data_dir / "coverage-config.json", discovered, "2026-08-04T12:00:00Z"
    )
    notice = cc.measurement_basis_notice(
        loaded.config["bootstrapped_at"], baseline["captured_at"]
    )

    assert loaded.bootstrapped is True
    assert loaded.notice is not None
    assert (
        json.loads((data_dir / "baseline-coverage.json").read_text(encoding="utf-8"))
        == baseline
    )
    # The pre-existing baseline predates the bootstrap, so it is flagged as not
    # comparable rather than silently compared against a merged number.
    assert notice is not None


def test_zero_real_test_projects_is_a_diagnosable_hard_failure(
    tmp_path: Path, stub_sln_list
) -> None:
    _dotnet_solution(tmp_path, {"src/App/App.csproj": _csproj()})
    stub_sln_list("src/App/App.csproj")
    discovered = dnd.discover(tmp_path)

    loaded = cc.load_or_bootstrap(
        tmp_path / "data" / "coverage-config.json", discovered, "2026-08-04T12:00:00Z"
    )

    assert loaded.config["included"] == []
    with pytest.raises(cc.DiscoveryError) as excinfo:
        cc.weighted_merge([])

    # Names the markers discovery recognizes, so the operator can check theirs.
    assert "structural marker" in str(excinfo.value)
    assert "multi-project-discovery.md" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Integration — no regression for single-project and mixed-stack repos
# ---------------------------------------------------------------------------


def test_a_single_csproj_repo_is_untouched(tmp_path: Path) -> None:
    _write(tmp_path / "App" / "App.csproj", _csproj(_MARKER))

    assert dnd.discover(tmp_path) is cc.DISCOVERY_NOT_APPLICABLE
    assert not (tmp_path / "coverage-config.json").exists()


def test_a_single_package_json_repo_is_untouched(tmp_path: Path) -> None:
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "solo", **_JS_TEST_MANIFEST}),
    )

    assert jsd.discover(tmp_path) is cc.DISCOVERY_NOT_APPLICABLE
    assert not (tmp_path / "coverage-config.json").exists()


def test_a_mixed_stack_repo_discovers_each_stack_independently(
    tmp_path: Path, stub_sln_list
) -> None:
    # A .sln and a workspace package.json in one repo: each stack sees only its
    # own projects, and neither suppresses the other.
    _dotnet_solution(tmp_path, {"tests/A.Tests/A.Tests.csproj": _csproj(_MARKER)})
    stub_sln_list("tests/A.Tests/A.Tests.csproj")
    _js_workspace(tmp_path, {"web": _JS_TEST_MANIFEST})

    dotnet_result = dnd.discover(tmp_path)
    js_result = jsd.discover(tmp_path)

    assert [project.path for project in dotnet_result] == [
        "tests/A.Tests/A.Tests.csproj"
    ]
    assert [project.path for project in js_result] == ["packages/web"]
