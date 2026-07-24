"""Tests for the xunit.v2 shim generator's #1159 hardening — operator-selected
compile exclusions and the SolutionPath-trap-avoiding config."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_GEN = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "stryker-xunit-v2-shim"
    / "scripts"
    / "generate_shim.py"
)

_V3_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <RootNamespace>Acme.Widgets.Tests</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="xunit.v3" Version="1.0.0" />
    <PackageReference Include="Moq" Version="4.20.70" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="..\\..\\src\\Acme.Widgets\\Acme.Widgets.csproj" />
  </ItemGroup>
</Project>
"""


def _make_project(root: Path) -> Path:
    d = root / "tests" / "Acme.Widgets.Tests"
    d.mkdir(parents=True)
    csproj = d / "Acme.Widgets.Tests.csproj"
    csproj.write_text(_V3_CSPROJ)
    return csproj


def _run_gen(csproj: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_GEN), str(csproj), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _shim_dir(root: Path) -> Path:
    return root / "tests" / "Acme.Widgets.Tests.Mutation"


def test_config_pins_test_projects_and_omits_solution_path(tmp_path):
    csproj = _make_project(tmp_path)
    proc = _run_gen(csproj)
    assert proc.returncode == 0, proc.stderr
    config = json.loads((_shim_dir(tmp_path) / "stryker-config.json").read_text())
    sc = config["stryker-config"]
    # test-projects pins the shim; SolutionPath must be absent (the #557/#1156 trap).
    assert sc["test-projects"] == ["Acme.Widgets.Tests.Mutation.csproj"]
    assert "SolutionPath" not in sc
    assert "solution-path" not in sc


def test_compile_exclude_appends_to_shim_compile_set(tmp_path):
    csproj = _make_project(tmp_path)
    proc = _run_gen(
        csproj,
        "--compile-exclude",
        "..\\Acme.Widgets.Tests\\ExplicitTests.cs",
        "--compile-exclude",
        "..\\Acme.Widgets.Tests\\TestContextUsage.cs",
    )
    assert proc.returncode == 0, proc.stderr
    shim_csproj = (_shim_dir(tmp_path) / "Acme.Widgets.Tests.Mutation.csproj").read_text()
    assert "ExplicitTests.cs" in shim_csproj
    assert "TestContextUsage.cs" in shim_csproj
    # Still inside the <Compile ... Exclude="..."> attribute alongside obj/bin.
    assert "obj\\**\\*.cs" in shim_csproj


def test_compile_exclude_single_value(tmp_path):
    csproj = _make_project(tmp_path)
    proc = _run_gen(csproj, "--compile-exclude", "..\\Acme.Widgets.Tests\\OneFile.cs")
    assert proc.returncode == 0, proc.stderr
    shim_csproj = (_shim_dir(tmp_path) / "Acme.Widgets.Tests.Mutation.csproj").read_text()
    assert "OneFile.cs" in shim_csproj
    # Appended after the two defaults with a single separator, no doubled ';'.
    assert "bin\\**\\*.cs;..\\Acme.Widgets.Tests\\OneFile.cs" in shim_csproj
    assert ";;" not in shim_csproj


def test_compile_exclude_drops_empty_and_trims(tmp_path):
    csproj = _make_project(tmp_path)
    proc = _run_gen(
        csproj,
        "--compile-exclude", "",
        "--compile-exclude", "   ",
        "--compile-exclude", "  ..\\Acme.Widgets.Tests\\Padded.cs  ",
    )
    assert proc.returncode == 0, proc.stderr
    exclude_line = next(
        ln for ln in (_shim_dir(tmp_path) / "Acme.Widgets.Tests.Mutation.csproj")
        .read_text().splitlines() if "Exclude=" in ln
    )
    # Empty/whitespace entries dropped → no doubled/trailing separators.
    assert ";;" not in exclude_line
    assert not exclude_line.rstrip('">').endswith(";")
    # The padded path is present, trimmed.
    assert "..\\Acme.Widgets.Tests\\Padded.cs" in exclude_line
    assert "Padded.cs  " not in exclude_line


def test_no_compile_exclude_keeps_default_excludes_only(tmp_path):
    csproj = _make_project(tmp_path)
    proc = _run_gen(csproj)
    assert proc.returncode == 0
    shim_csproj = (_shim_dir(tmp_path) / "Acme.Widgets.Tests.Mutation.csproj").read_text()
    assert 'Exclude="..\\Acme.Widgets.Tests\\obj\\**\\*.cs;..\\Acme.Widgets.Tests\\bin\\**\\*.cs"' in shim_csproj


def test_non_v3_csproj_refuses(tmp_path):
    d = tmp_path / "tests" / "Plain"
    d.mkdir(parents=True)
    csproj = d / "Plain.csproj"
    csproj.write_text('<Project><ItemGroup><PackageReference Include="xunit" Version="2.9.2" /></ItemGroup></Project>')
    proc = _run_gen(csproj)
    assert proc.returncode != 0
    assert "xunit.v3" in proc.stderr
