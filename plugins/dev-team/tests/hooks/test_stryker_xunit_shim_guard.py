"""Unit tests for hooks/stryker_xunit_shim_guard.py (#1083).

The gate blocks Stryker.NET runs that would bind to a xunit.v3 test project
(project mode) or to one via solution mode, since Stryker cannot observe kills
through xunit.v3 and reports a false ~0% score. Runs from a xunit.v2 `.Mutation`
shim directory pass untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "stryker_xunit_shim_guard.py"

_V3_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <RootNamespace>Acme.Widgets.Tests</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="xunit.v3" Version="1.0.0" />
    <PackageReference Include="Moq" Version="4.20.70" />
  </ItemGroup>
</Project>
"""

_V2_SHIM_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <AssemblyName>Acme.Widgets.Tests.Mutation</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="xunit" Version="2.9.2" />
  </ItemGroup>
</Project>
"""


def _run(payload: dict, extra_env: dict = None) -> subprocess.CompletedProcess:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        **(extra_env or {}),
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _v3_project(root: Path) -> Path:
    d = root / "tests" / "Acme.Widgets.Tests"
    d.mkdir(parents=True)
    (d / "Acme.Widgets.Tests.csproj").write_text(_V3_CSPROJ)
    return d


def _v2_shim(root: Path) -> Path:
    d = root / "tests" / "Acme.Widgets.Tests.Mutation"
    d.mkdir(parents=True)
    (d / "Acme.Widgets.Tests.Mutation.csproj").write_text(_V2_SHIM_CSPROJ)
    return d


def test_non_stryker_command_passes(tmp_path):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet test"}})
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_non_bash_tool_passes(tmp_path):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Edit", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 0


def test_stryker_on_v3_project_autoscaffolds_and_blocks(tmp_path):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker"}})
    # Still blocks the wrong invocation...
    assert proc.returncode == 2
    assert proc.stdout.startswith("[BLOCK]")
    # ...but has auto-scaffolded the shim and reported it (not silent).
    assert "auto-scaffolded" in proc.stdout.lower()
    shim = tmp_path / "tests" / "Acme.Widgets.Tests.Mutation" / "Acme.Widgets.Tests.Mutation.csproj"
    assert shim.exists()
    assert (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation" / "stryker-config.json").exists()


def test_dotnet_dash_stryker_also_triggers(tmp_path):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet-stryker --reporter json"}})
    assert proc.returncode == 2


def test_v3_only_constructs_refuse_scaffold(tmp_path):
    d = _v3_project(tmp_path)
    (d / "AutoTests.cs").write_text(
        "public class T { [AutoData] public void X() {} }")
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 2
    assert "can't be auto-built" in proc.stdout
    assert "AutoTests.cs" in proc.stdout
    # No shim was written when porting is required.
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_existing_shim_not_regenerated(tmp_path):
    _v3_project(tmp_path)
    shim = _v2_shim(tmp_path)
    marker = shim / "sentinel"
    marker.write_text("keep")
    proc = _run({"tool_name": "Bash", "cwd": str(tmp_path / "tests" / "Acme.Widgets.Tests"),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 2
    assert "already exists" in proc.stdout
    assert marker.read_text() == "keep"  # untouched


def test_run_from_shim_dir_passes(tmp_path):
    _v3_project(tmp_path)
    shim = _v2_shim(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(shim),
                 "tool_input": {"command": "dotnet-stryker"}})
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_cd_prefix_into_shim_passes(tmp_path):
    _v3_project(tmp_path)
    _v2_shim(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(tmp_path / "tests"),
                 "tool_input": {"command": "cd Acme.Widgets.Tests.Mutation && dotnet-stryker"}})
    assert proc.returncode == 0


def test_solution_mode_at_root_scaffolds_and_blocks(tmp_path):
    _v3_project(tmp_path)
    (tmp_path / "Acme.sln").write_text("")
    proc = _run({"tool_name": "Bash", "cwd": str(tmp_path),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 2
    assert "solution mode" in proc.stdout
    # The v3 project found in the solution is scaffolded too.
    assert (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation"
            / "Acme.Widgets.Tests.Mutation.csproj").exists()


def test_solution_root_without_v3_passes(tmp_path):
    (tmp_path / "Acme.sln").write_text("")
    v2 = tmp_path / "tests" / "Plain.Tests"
    v2.mkdir(parents=True)
    (v2 / "Plain.Tests.csproj").write_text(_V2_SHIM_CSPROJ.replace(".Mutation", ""))
    proc = _run({"tool_name": "Bash", "cwd": str(tmp_path),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 0


def test_skip_env_bypasses(tmp_path):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker"}},
                extra_env={"DEV_TEAM_STRYKER_XUNIT3_GATE_SKIP": "1"})
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_malformed_stdin_passes():
    proc = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json{{{",
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0
