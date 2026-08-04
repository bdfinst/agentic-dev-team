"""Coverage for coverage-baseline/SKILL.md Step 1a's boundary cases (issue
#1759, Slice 4, Step 4.4): zero real test projects/packages discovered, and
a config entry listed in both `included` and `excluded` — both wired into
the same hard-failure path as an unaccounted-for project.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from coverage_baseline_flow_helpers import (
    ZERO_REAL_TEST_MESSAGE_TEMPLATE,
    run_baseline_flow,
    stub_dotnet,
    zero_real_test_message,
)
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd  # noqa: E402
import coverage_discovery_js as cdj  # noqa: E402

SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_1a_section() -> str:
    return section(_text(), r"^### 1a\. Multi-project discovery", boundary_pattern=r"^### ")


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


NOT_TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType></PropertyGroup>
</Project>
"""
TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""
TEST_PKG = {
    "name": "test-pkg",
    "scripts": {"test": "jest"},
    "devDependencies": {"jest": "^29"},
}
NOT_TEST_PKG = {"name": "helper-pkg", "scripts": {"build": "tsc"}}


# ---------------------------------------------------------------------------
# Content-guard: the exact zero-real-test message is documented verbatim
# (kept in sync with the shared helper's template, which every integration
# test below asserts against).
# ---------------------------------------------------------------------------


def test_zero_real_test_message_documented_verbatim_for_both_stacks():
    """The SKILL.md carries the template with the literal placeholder
    `<solution|workspace>`, not a resolved value — check the unresolved
    template text (shared with the flow-helpers module every integration
    test below imports) appears verbatim."""
    step_1a = collapsed(_step_1a_section())
    template_text = collapsed(
        ZERO_REAL_TEST_MESSAGE_TEMPLATE.format(kind="<solution|workspace>")
    )
    assert template_text in step_1a


def test_step_1a_names_markers_discovery_recognizes():
    step_1a = collapsed(_step_1a_section())
    assert "Microsoft.NET.Test.Sdk" in step_1a
    assert grep(r"jest.*vitest.*mocha.*nyc.*c8", step_1a, ignore_case=True)


# ---------------------------------------------------------------------------
# Integration: zero real test projects/packages — hard failure, no baseline.
# ---------------------------------------------------------------------------


def test_dotnet_zero_real_test_projects_is_hard_failure(tmp_path):
    write(tmp_path / "App.sln", "Microsoft Visual Studio Solution File\n")
    rel = "src/Foo/Foo.csproj"
    write(tmp_path / rel, NOT_TEST_CSPROJ)

    with stub_dotnet([rel]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    config_path = tmp_path / "coverage-config.json"
    baseline_path = tmp_path / "baseline-coverage.json"
    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "solution",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert result.message == zero_real_test_message("solution")
    assert not config_path.exists()
    assert result.baseline_written is False
    assert not baseline_path.exists()


def test_js_zero_real_test_packages_is_hard_failure(tmp_path):
    write(
        tmp_path / "package.json",
        {"name": "root", "private": True, "workspaces": ["packages/*"]},
    )
    write(tmp_path / "packages" / "a" / "package.json", NOT_TEST_PKG)

    discovered = cdj.discover_js_packages(tmp_path)

    config_path = tmp_path / "coverage-config.json"
    baseline_path = tmp_path / "baseline-coverage.json"
    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "workspace",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert result.message == zero_real_test_message("workspace")
    assert not config_path.exists()
    assert result.baseline_written is False
    assert not baseline_path.exists()


# ---------------------------------------------------------------------------
# Integration: conflicting config entry (path in both included and
# excluded) exercised through the real flow, not just Slice 1's
# module-level test.
# ---------------------------------------------------------------------------


def test_dotnet_conflicting_config_entry_is_hard_failure(tmp_path):
    write(tmp_path / "App.sln", "Microsoft Visual Studio Solution File\n")
    rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(tmp_path / rel, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    write(
        config_path,
        {"included": [rel], "excluded": [{"path": rel, "reason": "listed twice by mistake"}]},
    )

    with stub_dotnet([rel]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    baseline_path = tmp_path / "baseline-coverage.json"
    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "solution",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert "listed in both" in result.message
    assert rel in result.message
    assert result.baseline_written is False
    assert not baseline_path.exists()


def test_js_conflicting_config_entry_is_hard_failure(tmp_path):
    write(
        tmp_path / "package.json",
        {"name": "root", "private": True, "workspaces": ["packages/*"]},
    )
    write(tmp_path / "packages" / "a" / "package.json", TEST_PKG)

    config_path = tmp_path / "coverage-config.json"
    write(
        config_path,
        {
            "included": ["packages/a"],
            "excluded": [{"path": "packages/a", "reason": "listed twice by mistake"}],
        },
    )

    discovered = cdj.discover_js_packages(tmp_path)

    baseline_path = tmp_path / "baseline-coverage.json"
    result = run_baseline_flow(
        discovered,
        config_path,
        "2026-08-04T12:00:00Z",
        "workspace",
        baseline_path=baseline_path,
    )

    assert result.stopped is True
    assert "listed in both" in result.message
    assert "packages/a" in result.message
    assert result.baseline_written is False
    assert not baseline_path.exists()


# ---------------------------------------------------------------------------
# Integration: a stale `included` entry (no longer present in fresh
# discovery) is silently skipped in the merge step — the legitimate case
# _merge_included_reports must NOT raise for, distinct from the "wired
# wrong test fixture" case (present in both `included` and `discovered`
# with no matching report) that raises loudly instead.
# ---------------------------------------------------------------------------


def test_stale_included_entry_absent_from_discovery_is_silently_skipped_in_merge(tmp_path):
    write(
        tmp_path / "package.json",
        {"name": "root", "private": True, "workspaces": ["packages/*"]},
    )
    write(tmp_path / "packages" / "a" / "package.json", TEST_PKG)
    # "packages/stale" is still listed in coverage-config.json's "included"
    # from a prior run, but no longer exists on disk — fresh discovery will
    # not report it at all.

    config_path = tmp_path / "coverage-config.json"
    write(
        config_path,
        {"included": ["packages/a", "packages/stale"], "excluded": []},
    )

    discovered = cdj.discover_js_packages(tmp_path)

    baseline_path = tmp_path / "baseline-coverage.json"
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

    # No crash, no hard failure — "packages/stale" is silently skipped
    # because it's absent from BOTH included-report lookup and discovery.
    assert result.stopped is False
    assert result.merged["line_pct"] == 50.0
    assert result.baseline_written is True
