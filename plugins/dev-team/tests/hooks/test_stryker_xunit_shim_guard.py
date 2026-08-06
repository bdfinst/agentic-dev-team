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

from _repo_root import REPO_ROOT as _REPO_ROOT

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


def _run(payload: dict, extra_env: dict | None = None) -> subprocess.CompletedProcess:
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


def test_mtp_floor_run_is_exempt(tmp_path):
    # The sanctioned no-shim floor (#1156/#1159): an explicit -t mtp run drives
    # the real v3 suite and yields a real score, so it must NOT be blocked or
    # scaffolded.
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker -t mtp --reporter json"}})
    assert proc.returncode == 0
    assert proc.stdout == ""
    # No shim was scaffolded by the floor path.
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


@pytest.mark.parametrize(
    "cmd",
    [
        "dotnet stryker --test-runner mtp",
        "dotnet stryker -t=mtp",
        "dotnet stryker --test-runner=mtp",
        'dotnet stryker --test-runner "mtp"',
    ],
)
def test_mtp_runner_variants_exempt(tmp_path, cmd):
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": cmd}})
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_vstest_runner_still_blocks(tmp_path):
    # An explicit non-mtp runner is NOT the floor — the false-score block stands.
    d = _v3_project(tmp_path)
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker -t vstest"}})
    assert proc.returncode == 2


def test_v3_only_constructs_refuse_scaffold(tmp_path):
    d = _v3_project(tmp_path)
    (d / "AutoTests.cs").write_text(
        "public class T { [AutoData] public void X() {} }")
    proc = _run({"tool_name": "Bash", "cwd": str(d),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 2
    assert "AutoTests.cs" in proc.stdout
    # No shim was written when porting is required.
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


# --- the operator decision gate (#1791) -------------------------------------
#
# Detection existed; a guaranteed operator decision did not. These pin the
# enforceable half: with shim-breaking constructs present the guard blocks with
# the classified breakdown and the four options, and STAYS blocked until the
# operator's choice is recorded — a rendered question alone is text an agent can
# paraphrase or skip.
#
# #1870 dropped the DEV_TEAM_XUNIT3_SHIM_DECISION_FILE env-var relocation seam
# entirely. The guard reads/writes the decision store via the payload `cwd`
# (project_dir); `_record()` below runs the CLI with that same directory as its
# real OS subprocess cwd so both sides resolve to the identical store path —
# project_dir sits outside a git checkout (pytest's tmp_path), so
# `artifact_paths.project_root()` falls back to project_dir itself on both
# sides rather than walking up to a real repo root.


def _blocked_project(root: Path) -> Path:
    d = _v3_project(root)
    (d / "AutoTests.cs").write_text(
        "public class T {\n    [Theory, AutoData]\n    public void X(int a) {}\n}\n"
    )
    return d


def _run_in(project_dir: Path, command: str = "dotnet stryker"):
    return _run(
        {"tool_name": "Bash", "cwd": str(project_dir),
         "tool_input": {"command": command}},
    )


def _answer(project_dir: Path, choice: str) -> str:
    """Walk the real loop: ask, take the printed fingerprint, record the answer.

    Recording against the fingerprint the guard actually published — rather
    than a bare `record --choice X` — is the only realistic path now that a
    fingerprint is mandatory, and it exercises ask -> record -> re-run end to
    end instead of just the recorded state.
    """
    asked = _run_in(project_dir)
    fingerprint = _fingerprint_from(asked.stdout)
    assert fingerprint, f"the gate published no fingerprint:\n{asked.stdout}"
    _record(project_dir, choice, fingerprint)
    return fingerprint


def _record(project_dir: Path, choice: str, fingerprint: str) -> None:
    module = (
        _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
        / "xunit_v3_operator_gate.py"
    )
    args = ["python3", str(module), "record", "--project",
            "Acme.Widgets.Tests", "--choice", choice,
            "--fingerprint", fingerprint]
    done = subprocess.run(
        args,
        cwd=str(project_dir),
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
        },
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr


def test_blockers_without_a_decision_ask_the_operator(tmp_path):
    d = _blocked_project(tmp_path)
    proc = _run_in(d)
    assert proc.returncode == 2
    out = proc.stdout
    # What's blocking, in the detector's classified terms.
    assert "autofixture-auto-data" in out
    assert "AutoTests.cs" in out
    assert "can't compile" in out
    # All four options with their tradeoffs, and whose call it is.
    for choice in ("port", "exclude", "skip", "degrade"):
        assert choice in out
    assert "Tradeoff" in out
    assert "operator" in out.lower()
    # And the command that records the answer, so the gate can be satisfied.
    assert "xunit_v3_operator_gate.py" in out
    assert "record" in out
    # Nothing was built or degraded on the operator's behalf.
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_asking_twice_does_not_scaffold_behind_the_operators_back(tmp_path):
    d = _blocked_project(tmp_path)
    _run_in(d)
    proc = _run_in(d)
    assert proc.returncode == 2
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_recorded_exclude_scaffolds_with_the_flagged_file_excluded(tmp_path):
    d = _blocked_project(tmp_path)
    _answer(d, "exclude")
    proc = _run_in(d)
    assert proc.returncode == 2
    shim = tmp_path / "tests" / "Acme.Widgets.Tests.Mutation"
    csproj = shim / "Acme.Widgets.Tests.Mutation.csproj"
    assert csproj.exists(), proc.stdout
    # The operator's exclusion reached the shim's compile set in the exact shape
    # the generator's own Exclude values use — shim-relative and backslashed. A
    # bare "AutoTests.cs in the text" check would pass for either separator form
    # and so would not pin the shape the exclusion depends on.
    assert r"..\Acme.Widgets.Tests\AutoTests.cs" in csproj.read_text()
    assert "Acme.Widgets.Tests.Mutation" in proc.stdout


def test_exclusions_keep_the_subdirectory_when_the_flagged_file_is_nested(tmp_path):
    d = _v3_project(tmp_path)
    nested = d / "Widgets" / "Deep"
    nested.mkdir(parents=True)
    (nested / "AutoTests.cs").write_text(
        "public class T {\n    [Theory, AutoData]\n    public void X(int a) {}\n}\n"
    )
    _answer(d, "exclude")
    proc = _run_in(d)
    csproj = (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation"
              / "Acme.Widgets.Tests.Mutation.csproj")
    assert csproj.exists(), proc.stdout
    assert r"..\Acme.Widgets.Tests\Widgets\Deep\AutoTests.cs" in csproj.read_text()


def test_exclude_scaffold_failure_is_reported_not_swallowed(tmp_path):
    d = _blocked_project(tmp_path)
    _answer(d, "exclude")
    # Make the shim's parent directory unwritable so the generator cannot create
    # it: the guard must say scaffolding failed rather than claim success.
    tests_dir = tmp_path / "tests"
    original = tests_dir.stat().st_mode
    tests_dir.chmod(0o500)
    try:
        proc = _run_in(d)
    finally:
        tests_dir.chmod(original)
    assert proc.returncode == 2
    assert "exclusions failed" in proc.stdout, proc.stdout
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_recorded_degrade_hands_back_the_no_shim_floor_command(tmp_path):
    d = _blocked_project(tmp_path)
    _answer(d, "degrade")
    proc = _run_in(d)
    assert proc.returncode == 2
    assert "-t mtp" in proc.stdout
    # coverage-analysis is config-file-only in Stryker.NET — telling the
    # operator to pass it as a CLI flag is the command-retry churn of #1777.
    assert "--coverage-analysis" not in proc.stdout
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


@pytest.mark.parametrize("choice", ["port", "skip"])
def test_recorded_port_or_skip_blocks_until_the_sources_are_clean(tmp_path, choice):
    d = _blocked_project(tmp_path)
    _answer(d, choice)
    proc = _run_in(d)
    assert proc.returncode == 2
    assert choice in proc.stdout
    assert "AutoTests.cs" in proc.stdout
    # The shim is only built once the flagged constructs are gone.
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_skip_says_deactivating_alone_will_not_clear_a_body_construct(tmp_path):
    # Deactivating a test removes it from the RUN, not from the SOURCE the shim
    # compiles, so `skip` cannot clear the gate for a body/data-attribute
    # construct. Without saying so, the operator re-runs into the same block and
    # concludes the gate is broken.
    d = _blocked_project(tmp_path)
    _answer(d, "skip")
    proc = _run_in(d)
    assert "not from the" in proc.stdout or "NOTE:" in proc.stdout
    assert "'port'" in proc.stdout and "'exclude'" in proc.stdout


def test_port_choice_then_clean_sources_scaffolds_normally(tmp_path):
    d = _blocked_project(tmp_path)
    _answer(d, "port")
    (d / "AutoTests.cs").write_text(
        "public class T {\n    [Theory]\n    [InlineData(1)]\n    public void X(int a) {}\n}\n"
    )
    proc = _run_in(d)
    assert proc.returncode == 2
    assert "auto-scaffolded" in proc.stdout.lower()
    assert (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation"
            / "Acme.Widgets.Tests.Mutation.csproj").exists()


def test_a_new_blocker_reasks_instead_of_riding_the_old_decision(tmp_path):
    d = _blocked_project(tmp_path)
    first = _run_in(d)
    fingerprint = _fingerprint_from(first.stdout)
    _record(d, "exclude", fingerprint)
    # A second blocking file appears after the operator answered.
    (d / "SkipTests.cs").write_text(
        'public class S {\n    [Fact]\n    public void Y() { Assert.Skip("x"); }\n}\n'
    )
    proc = _run_in(d)
    assert proc.returncode == 2
    assert "SkipTests.cs" in proc.stdout
    assert "Tradeoff" in proc.stdout, (
        "a decision made about a smaller blocker set must re-ask, not silently "
        "exclude a file the operator never saw"
    )
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def _fingerprint_from(text: str) -> str | None:
    for line in text.splitlines():
        if "--fingerprint" in line:
            parts = line.split("--fingerprint", 1)[1].split()
            if parts:
                return parts[0].strip("\"'")
    return None


def test_the_block_body_publishes_the_fingerprint_to_record_against(tmp_path):
    d = _blocked_project(tmp_path)
    proc = _run_in(d)
    assert _fingerprint_from(proc.stdout), (
        "the question must publish the blocker-set fingerprint, or a recorded "
        "decision cannot be scoped to the blockers the operator saw"
    )


def test_unclassifiable_v3_usage_still_reaches_the_operator(tmp_path):
    # The guard's token scan is broader than the detector's classified set:
    # `TestContext` without `.Current` matches the token but no construct. It
    # must still be surfaced, labelled for manual triage, not dropped.
    d = _v3_project(tmp_path)
    (d / "CtxTests.cs").write_text(
        "public class C { void X() { var t = TestContext; } }\n"
    )
    proc = _run_in(d)
    assert proc.returncode == 2
    assert "CtxTests.cs" in proc.stdout
    assert "unclassified" in proc.stdout.lower()
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_paths_in_the_block_body_are_short_and_copy_pasteable(tmp_path):
    # The gate resolves the run dir but used the RAW event cwd for its relative
    # paths, so whenever the cwd traverses a symlink (macOS /var -> /private/var
    # is the everyday case) the emitted command was a ../../../.. crawl back to
    # the filesystem root. A command nobody can paste is a command that gets
    # retyped — the churn #1777 is about. The link here reproduces that without
    # depending on a platform's own symlinked temp dir.
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    _v3_project(real)
    proc = _run({"tool_name": "Bash", "cwd": str(link / "tests" / "Acme.Widgets.Tests"),
                 "tool_input": {"command": "dotnet stryker"}})
    assert proc.returncode == 2
    # The shim is a SIBLING of the test project: exactly one level up, never a
    # crawl back through the symlink's parent chain.
    assert "../../" not in proc.stdout, proc.stdout
    assert "../Acme.Widgets.Tests.Mutation" in proc.stdout


def test_floor_command_omits_a_no_op_cd_when_already_in_the_project_dir(tmp_path):
    d = _blocked_project(tmp_path)
    _answer(d, "degrade")
    proc = _run_in(d)
    assert "cd .\n" not in proc.stdout
    assert "dotnet-stryker -t mtp" in proc.stdout


def test_clean_v3_project_never_asks(tmp_path):
    # No shim-breaking constructs: nothing to decide, so the pre-existing
    # auto-scaffold path must stay exactly as it was.
    d = _v3_project(tmp_path)
    (d / "PlainTests.cs").write_text(
        "public class P {\n    [Fact]\n    public void X() {}\n}\n"
    )
    proc = _run_in(d)
    assert proc.returncode == 2
    assert "Tradeoff" not in proc.stdout
    assert (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation"
            / "Acme.Widgets.Tests.Mutation.csproj").exists()


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


def test_solution_mode_with_blockers_asks_the_operator_too(tmp_path):
    # Solution mode reaches the same handler, but only its no-blockers path was
    # covered — the operator gate through this entry point was inferred from
    # code-sharing rather than exercised.
    _blocked_project(tmp_path)
    (tmp_path / "Acme.sln").write_text("")
    proc = _run_in(tmp_path)
    assert proc.returncode == 2
    assert "solution mode" in proc.stdout
    assert "autofixture-auto-data" in proc.stdout
    for choice in ("port", "exclude", "skip", "degrade"):
        assert choice in proc.stdout
    assert not (tmp_path / "tests" / "Acme.Widgets.Tests.Mutation").exists()


def test_floor_command_cds_into_the_project_when_run_from_elsewhere(tmp_path):
    # The omission of a no-op `cd .` was pinned; the presence and content of a
    # real `cd <relpath>` was not. Solution mode runs from the repo root, so the
    # project is a genuine relative hop away.
    _blocked_project(tmp_path)
    (tmp_path / "Acme.sln").write_text("")
    asked = _run_in(tmp_path)
    fingerprint = _fingerprint_from(asked.stdout)
    assert fingerprint
    _record(tmp_path, "degrade", fingerprint)
    proc = _run_in(tmp_path)
    assert "cd tests/Acme.Widgets.Tests" in proc.stdout, proc.stdout


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
