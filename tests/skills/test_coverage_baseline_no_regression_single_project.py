"""Coverage for coverage-baseline/SKILL.md Step 1b (issue #1759, Slice 4,
Step 4.3): single-project repos (a `.csproj` with no `.sln`, or a
`package.json` with no workspace signal) take the pre-existing
single-command path completely unchanged, and a mixed-stack repo (both a
`.sln` and a workspace-configured `package.json`) is explicitly out of
scope — `coverage-baseline`'s existing first-match manifest order resolves
to one tool, with no new cross-stack merge behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from coverage_baseline_flow_helpers import stub_dotnet
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd
import coverage_discovery_js as cdj
from coverage_config import DISCOVERY_NOT_APPLICABLE, TestClassification

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_1b_section() -> str:
    return section(
        _text(), r"^### 1b\. Single-project and mixed-stack", boundary_pattern=r"^### "
    )


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Content-guard
# ---------------------------------------------------------------------------


def test_step_1b_states_single_project_repos_unaffected():
    step_1b = collapsed(_step_1b_section())
    assert "no .sln" in step_1b or "no `.sln`" in step_1b
    assert grep(r"unchanged", step_1b, ignore_case=True)
    assert grep(r"no discovery call", step_1b, ignore_case=True)
    assert grep(r"no `?coverage-config\.json`? write", step_1b, ignore_case=True)


def test_step_1b_names_mixed_stack_as_out_of_scope():
    step_1b = collapsed(_step_1b_section())
    assert grep(r"out of scope", step_1b, ignore_case=True)
    assert grep(r"both", step_1b, ignore_case=True)
    assert grep(r"first-match order", step_1b, ignore_case=True)
    assert grep(r"no new cross-stack merge", step_1b, ignore_case=True)


def test_manifest_table_lists_package_json_before_csproj():
    """First-match order: package.json (JS/TS) is listed above `*.csproj`
    in Step 1's table — a mixed-stack repo resolves to the JS/TS tool,
    unchanged by this feature."""
    text = _text()
    package_json_idx = text.index("| `package.json` (JS/TS) |")
    csproj_idx = text.index("| `*.csproj` |")
    assert package_json_idx < csproj_idx


# ---------------------------------------------------------------------------
# Integration: DISCOVERY_NOT_APPLICABLE -> no coverage-config.json is ever
# written for a single-project repo.
# ---------------------------------------------------------------------------


def test_dotnet_single_project_reports_not_applicable_and_writes_no_config(tmp_path):
    write(tmp_path / "src" / "Foo" / "Foo.csproj", "<Project></Project>")

    discovered = cdd.discover_dotnet_projects(tmp_path)

    assert discovered is DISCOVERY_NOT_APPLICABLE
    # The documented flow never reaches load_or_bootstrap on this path.
    assert not list(tmp_path.rglob("coverage-config.json"))


def test_js_single_project_reports_not_applicable_and_writes_no_config(tmp_path):
    write(tmp_path / "package.json", {"name": "root"})

    discovered = cdj.discover_js_packages(tmp_path)

    assert discovered is DISCOVERY_NOT_APPLICABLE
    assert not list(tmp_path.rglob("coverage-config.json"))


# ---------------------------------------------------------------------------
# Integration: mixed-stack repo — both discovery functions still resolve
# correctly and independently; no cross-stack confusion.
# ---------------------------------------------------------------------------


def test_mixed_stack_repo_each_discovery_function_resolves_its_own_stack_only(tmp_path):
    # .NET side
    write(tmp_path / "App.sln", "Microsoft Visual Studio Solution File\n")
    dotnet_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / dotnet_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    # JS/TS side, in the same repo root
    write(
        tmp_path / "package.json",
        {"name": "root", "private": True, "workspaces": ["packages/*"]},
    )
    write(
        tmp_path / "packages" / "a" / "package.json",
        {"name": "a", "scripts": {"test": "jest"}, "devDependencies": {"jest": "^29"}},
    )

    with stub_dotnet([dotnet_rel]):
        dotnet_result = cdd.discover_dotnet_projects(tmp_path)
    js_result = cdj.discover_js_packages(tmp_path)

    # Each stack's discovery is unaffected by the other stack's files present
    # in the same repo root — no cross-stack confusion, no combined result.
    assert dotnet_result == [
        {"path": dotnet_rel, "classification": TestClassification.TEST}
    ]
    assert js_result == [
        {"path": "packages/a", "classification": TestClassification.TEST}
    ]
