"""Unit tests for skills/mutation-testing/scripts/mutation_kill_loop.py.

Covers a regression fix: ``run_scoped_stryker`` invoked its configured
``stryker_bin`` as a bare subprocess argv[0] — correct for a global
Stryker.NET install, but the skill's own docs recommend a local tool-
manifest install instead, whose command name is never placed on ``PATH``
(only reachable via ``dotnet stryker``). ``run_scoped_stryker`` now builds
its argv through ``csharp_stryker_net_wrapper.build_stryker_argv``, which
auto-detects the local-tool-manifest shape from ``stryker_bin`` alone.
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(
        _REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "mutation-testing"
        / "scripts"
    ),
)

from mutation_kill_loop import LoopConfig, run_scoped_stryker


def _config() -> LoopConfig:
    # solution=None skips the .sln hide/restore dance entirely — this test
    # is only about the constructed Stryker argv, not the sln ceremony.
    return LoopConfig(project=None, test_projects=["Foo.Tests.csproj"], mutate=[], solution=None)


def test_default_stryker_bin_invokes_via_the_dotnet_verb(tmp_path, monkeypatch):
    # resolve_dotnet_root's preset wins unconditionally over probing, so
    # this stubs out the DOTNET_ROOT dependency without asserting anything
    # about it — the test is only about the constructed Stryker argv, and
    # must pass identically on a machine with no .NET SDK installed.
    monkeypatch.setenv("DOTNET_ROOT", str(tmp_path))
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_scoped_stryker(_config(), "Foo.cs", output_dir=tmp_path)

    assert captured["argv"][:2] == ["dotnet", "stryker"]
    assert "--config-file" in captured["argv"]


def test_explicit_global_install_binary_is_invoked_directly(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTNET_ROOT", str(tmp_path))
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_scoped_stryker(_config(), "Foo.cs", output_dir=tmp_path, stryker_bin="dotnet-stryker")

    assert captured["argv"][0] == "dotnet-stryker"
    assert captured["argv"][1] == "--config-file"
