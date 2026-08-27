"""Pytest tests for csharp_stryker_net_wrapper.py — the shipped Stryker.NET
wrapper (#559, #564, #572).

Fixture strategy: temp dir with a dummy .sln + a fake ``dotnet`` shim on
PATH that records arg vectors, invocation timestamps, and env vars into
``$RECORD_DIR/``. The shim's exit code is controlled by env sentinels so
we can drive normal / non-zero / signal-trapped paths.

Contract preserved from the bash version's 32 bats tests. Every test's
Given/When/Then is the same behavioral contract; the only mechanical
difference is that we import the wrapper as a Python module and call
``main()`` directly rather than invoking a shell script over stdin.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure the wrapper's dir is on the path so we can import it as a module.
WRAPPER_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(WRAPPER_DIR))

import csharp_stryker_net_wrapper as wrapper


# =============================================================================
# Fixture helpers
# =============================================================================
@pytest.fixture
def hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Per-test hermetic workspace: temp dir + `.sln` + shim project.

    Portable across macOS, Linux, and native Windows. Does NOT install a
    filesystem `dotnet` shim on PATH — that approach ran into PATHEXT +
    which-lookup + subprocess.CreateProcess quirks on Windows. Instead the
    ``TestMainContract`` tests monkeypatch ``wrapper.build_project`` and
    ``wrapper.run_stryker`` directly, capturing invocations in a plain
    Python list. Simpler, faster, cross-platform by construction.

    Returns an object with:
      root         — Path to the temp dir (used as cwd)
      sln          — Path to $root/Foo.sln
      sln_hidden   — Path to $root/Foo.sln.stryker-hidden
      shim_project — Path to $root/tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj
      logfile      — Path to $root/wrapper.log
      calls        — list[dict] appended to by the monkeypatched
                     ``build_project`` and ``run_stryker`` in main-contract
                     tests. Each dict has {"kind": "build"|"stryker", ...}.
    """
    root = tmp_path
    sln = root / "Foo.sln"
    sln.write_text("solution stub")
    shim_dir = root / "tests" / "Foo.Tests.Mutation"
    shim_dir.mkdir(parents=True)
    shim_project = shim_dir / "Foo.Tests.Mutation.csproj"
    shim_project.write_text('<Project Sdk="Microsoft.NET.Sdk" />')

    # Pre-set DOTNET_ROOT so wrapper.main()'s probe short-circuits and
    # doesn't need a real SDK. Every platform.
    monkeypatch.setenv("DOTNET_ROOT", str(root / "fake-dotnet-root"))
    monkeypatch.chdir(root)

    class HermeticCtx:
        pass

    ctx = HermeticCtx()
    ctx.root = root
    ctx.sln = sln
    ctx.sln_hidden = Path(str(sln) + ".stryker-hidden")
    ctx.shim_project = shim_project
    ctx.logfile = root / "wrapper.log"
    ctx.calls = []  # populated by monkeypatched build_project / run_stryker
    return ctx


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    ctx,
    *,
    stryker_exit_code: int = 0,
    stryker_asserts_pid: bool = False,
):
    """Patch wrapper.build_project and wrapper.run_stryker to record calls
    into ctx.calls instead of spawning subprocesses. Cross-platform.
    """

    def fake_build(project: str, cwd=None) -> int:
        # Assert .sln is present at build time (contract: pre-build BEFORE
        # hide). If it's already hidden, that's a regression.
        assert ctx.sln.exists(), (
            f"build_project({project}) fired AFTER .sln was hidden — "
            f"pre-build ordering violated"
        )
        ctx.calls.append({"kind": "build", "project": project})
        return 0

    def fake_stryker(stryker_bin, stryker_args, logfile):
        # Assert .sln is hidden at Stryker time (contract: hide THEN run).
        assert not ctx.sln.exists(), (
            "run_stryker fired but .sln was still present — hide-before-"
            "stryker contract violated"
        )
        # Assert DOTNET_ROOT is exported (main() sets os.environ).
        ctx.calls.append(
            {
                "kind": "stryker",
                "stryker_bin": stryker_bin,
                "stryker_args": list(stryker_args),
                "logfile": str(logfile),
                "DOTNET_ROOT": os.environ.get("DOTNET_ROOT", ""),
            }
        )
        return stryker_exit_code

    monkeypatch.setattr(wrapper, "build_project", fake_build)
    monkeypatch.setattr(wrapper, "run_stryker", fake_stryker)
    # Critical: also stub out signal-handler installation. Without this,
    # main() calls signal.signal(SIGINT, ...) which globally replaces the
    # process's SIGINT handler with a handler that raises KeyboardInterrupt.
    # That handler persists for the rest of the pytest session — subsequent
    # tests can be killed by any spurious signal (verified: this caused
    # test #42 in the Windows CI job to crash with "KeyboardInterrupt:
    # signal 2" during unrelated status-loop tests).
    monkeypatch.setattr(wrapper, "_install_signal_handlers", list)


def run_wrapper(hermetic, *extra_args):
    """Invoke wrapper.main() with the given hermetic fixture's paths.

    Stryker-bin doesn't matter (run_stryker is monkeypatched) — pass a
    literal string so the CLI parser is exercised end-to-end.
    """
    args = [
        "--sln",
        str(hermetic.sln),
        "--shim-project",
        str(hermetic.shim_project),
        "--stryker-bin",
        "fake-stryker-bin",
        "--logfile",
        str(hermetic.logfile),
        *extra_args,
    ]
    return wrapper.main(args)


# =============================================================================
# probe_dotnet_root — pure function; direct tests
# =============================================================================
class TestProbeDotnetRoot:
    """Direct unit tests for the DOTNET_ROOT probe function. These replace
    the ``probe-fn:`` bats tests in mutation_testing_wrapper_tests.bats.
    """

    def test_returns_first_candidate_with_executable_dotnet(self, tmp_path):
        c = tmp_path / "with-dotnet"
        c.mkdir()
        exe = c / "dotnet"
        exe.write_text("#!/usr/bin/env python3\n")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        assert wrapper.probe_dotnet_root([str(c)]) == str(c)

    def test_returns_first_candidate_with_dotnet_exe_marker(self, tmp_path):
        """Windows-style: dotnet.exe present, no shared/, no non-.exe dotnet."""
        c = tmp_path / "with-dotnet-exe"
        c.mkdir()
        exe = c / "dotnet.exe"
        exe.write_text("stub")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        assert wrapper.probe_dotnet_root([str(c)]) == str(c)

    def test_returns_first_candidate_with_shared_dir_marker(self, tmp_path):
        c = tmp_path / "sdk-layout"
        (c / "shared").mkdir(parents=True)
        assert wrapper.probe_dotnet_root([str(c)]) == str(c)

    def test_skips_empty_candidate_segments(self, tmp_path):
        c = tmp_path / "valid"
        (c / "shared").mkdir(parents=True)
        assert wrapper.probe_dotnet_root(["", str(c), ""]) == str(c)

    def test_returns_none_when_no_candidate_hits(self, tmp_path):
        assert (
            wrapper.probe_dotnet_root(
                [str(tmp_path / "nope-1"), str(tmp_path / "nope-2")]
            )
            is None
        )

    def test_hit_order_position_1_wins_over_position_3(self, tmp_path):
        first = tmp_path / "homebrew-as"
        (first / "shared").mkdir(parents=True)
        third = tmp_path / "debian"
        (third / "shared").mkdir(parents=True)
        assert wrapper.probe_dotnet_root(
            [
                str(first),
                str(tmp_path / "homebrew-intel"),
                str(third),
            ]
        ) == str(first)

    def test_hit_order_position_4_wins_over_position_5(self, tmp_path):
        fedora = tmp_path / "fedora"
        (fedora / "shared").mkdir(parents=True)
        user = tmp_path / "user-scope"
        (user / "shared").mkdir(parents=True)
        assert wrapper.probe_dotnet_root(
            [
                str(tmp_path / "a"),
                str(tmp_path / "b"),
                str(tmp_path / "c"),
                str(fedora),
                str(user),
            ]
        ) == str(fedora)

    def test_handles_paths_with_spaces(self, tmp_path):
        """Windows Program Files style: path with a space, shared/ marker."""
        c = tmp_path / "Program Files" / "dotnet"
        (c / "shared").mkdir(parents=True)
        assert wrapper.probe_dotnet_root([str(c)]) == str(c)


# =============================================================================
# resolve_dotnet_root — probe + PATH fallback + no-SDK error
# =============================================================================
class TestResolveDotnetRoot:
    def test_preset_dotnet_root_is_authoritative(self, tmp_path):
        # Preset wins even when the probe would find something.
        c = tmp_path / "candidate"
        (c / "shared").mkdir(parents=True)
        root, err = wrapper.resolve_dotnet_root(
            preset="/custom/dotnet",
            candidates=[str(c)],
        )
        assert root == "/custom/dotnet"
        assert err is None

    def test_probe_hits_short_circuit_before_path_fallback(self, tmp_path):
        c = tmp_path / "probe-hit"
        (c / "shared").mkdir(parents=True)
        root, err = wrapper.resolve_dotnet_root(preset=None, candidates=[str(c)])
        assert root == str(c)
        assert err is None

    def test_path_fallback_when_no_probe_candidate_hits(self, tmp_path, monkeypatch):
        # No probe candidates hit. But `dotnet` is on PATH — fall back to
        # dirname of that. Windows `shutil.which` respects PATHEXT, so the
        # shim needs a recognized extension there; POSIX takes the plain
        # binary with the executable bit set.
        bin_dir = tmp_path / "custom-install" / "bin"
        bin_dir.mkdir(parents=True)
        if os.name == "nt":
            exe = bin_dir / "dotnet.cmd"
            exe.write_text("@echo off\r\n")
        else:
            exe = bin_dir / "dotnet"
            exe.write_text("#!/usr/bin/env sh\n")
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(bin_dir))
        root, err = wrapper.resolve_dotnet_root(
            preset=None,
            candidates=[str(tmp_path / "no-such-1"), str(tmp_path / "no-such-2")],
        )
        assert root == str(bin_dir)
        assert err is None

    def test_no_sdk_error_has_actionable_content(self, tmp_path, monkeypatch):
        # Strip PATH so `dotnet` is not on PATH either.
        monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
        root, err = wrapper.resolve_dotnet_root(
            preset=None,
            candidates=[str(tmp_path / "no-such")],
        )
        assert root is None
        assert err is not None
        # Actionable: names at least one probed path.
        assert str(tmp_path / "no-such") in err
        # Names the escape hatch (set DOTNET_ROOT explicitly).
        assert "DOTNET_ROOT" in err
        # Points at the install URL.
        assert "dotnet.microsoft.com/download" in err


# =============================================================================
# check_stale_hidden_sln — deterministic refuse
# =============================================================================
class TestCheckStaleHidden:
    def test_returns_none_when_only_fresh_sln_present(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        sln.write_text("stub")
        hidden = Path(str(sln) + ".stryker-hidden")
        assert wrapper.check_stale_hidden_sln(sln, hidden) is None

    def test_returns_none_when_only_hidden_sln_present(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stub")
        assert wrapper.check_stale_hidden_sln(sln, hidden) is None

    def test_returns_error_when_both_present(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        sln.write_text("stub")
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stale")
        err = wrapper.check_stale_hidden_sln(sln, hidden)
        assert err is not None
        assert str(hidden) in err
        assert str(sln) in err


# =============================================================================
# hide_sln + restore_sln — idempotent, don't clobber
# =============================================================================
class TestHideRestore:
    def test_hide_moves_sln_to_hidden(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        sln.write_text("stub")
        hidden = Path(str(sln) + ".stryker-hidden")
        wrapper.hide_sln(sln, hidden)
        assert not sln.exists()
        assert hidden.exists()
        assert hidden.read_text() == "stub"

    def test_hide_is_no_op_when_already_hidden(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stub")
        wrapper.hide_sln(sln, hidden)
        assert not sln.exists()
        assert hidden.exists()

    def test_restore_moves_hidden_to_sln(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stub")
        assert wrapper.restore_sln(sln, hidden) is True
        assert sln.exists()
        assert sln.read_text() == "stub"

    def test_restore_does_not_clobber_a_fresh_sln(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        sln.write_text("fresh")
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stale")
        # #1955: the guard's precondition wasn't met (a fresh .sln already
        # exists alongside the hidden one) — restoration was skipped, and
        # the caller can now tell.
        assert wrapper.restore_sln(sln, hidden) is False
        # Fresh .sln untouched.
        assert sln.read_text() == "fresh"


# =============================================================================
# restore_sln failure signal (#1955) — the guard's precondition not being met,
# or the rename itself raising, must be reported to the caller as False
# rather than silently returning None.
# =============================================================================
class TestRestoreSlnFailureSignal:
    def test_returns_false_when_neither_file_exists(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        hidden = Path(str(sln) + ".stryker-hidden")
        # The hide never happened (or something else removed the hidden
        # file) — nothing to restore, and the caller should know it.
        assert wrapper.restore_sln(sln, hidden) is False

    def test_returns_false_when_rename_raises_oserror(self, tmp_path, monkeypatch):
        sln = tmp_path / "Foo.sln"
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stub")

        def _explode(self, target):
            raise OSError("simulated locked file")

        monkeypatch.setattr(Path, "rename", _explode)

        assert wrapper.restore_sln(sln, hidden) is False
        # The rename failed — the hidden file is still there, untouched.
        assert hidden.exists()
        assert not sln.exists()


# =============================================================================
# End-to-end main() — the full wrapper contract
# =============================================================================
class TestMainContract:
    """Tests use monkeypatched wrapper.build_project and wrapper.run_stryker
    to intercept at the Python level — no filesystem shim, no PATH tricks.
    That makes every test in this class cross-platform by construction.
    """

    def test_normal_exit_restores_sln(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic)
        assert rc == 0
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()
        assert hermetic.sln.read_text() == "solution stub"

    def test_builds_sln_and_shim_project_before_hiding(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic)
        assert rc == 0
        # The fake_build assertion inside _install_fakes verifies .sln is
        # present at build time — that's the pre-build-ordering contract.
        # Here we additionally verify the call sequence.
        builds = [c for c in hermetic.calls if c["kind"] == "build"]
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        assert len(builds) == 2, f"expected 2 builds, got {builds}"
        assert builds[0]["project"] == str(hermetic.sln)
        assert builds[1]["project"] == str(hermetic.shim_project)
        assert len(strykers) == 1

    def test_stryker_nonzero_exit_propagates_and_restores(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic, stryker_exit_code=42)
        rc = run_wrapper(hermetic)
        assert rc == 42
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()

    # =========================================================================
    # Scenario (#1955): a failed .sln restore is surfaced as a distinct exit
    # code rather than silently reporting success.
    # =========================================================================
    def test_failed_restore_after_clean_stryker_run_surfaces_exit_code(
        self, hermetic, monkeypatch, capsys
    ):
        _install_fakes(monkeypatch, hermetic)
        monkeypatch.setattr(wrapper, "restore_sln", lambda sln, sln_hidden: False)

        rc = run_wrapper(hermetic)

        assert rc == wrapper.EXIT_RESTORE_SLN_FAILED
        captured = capsys.readouterr()
        assert str(hermetic.sln) in captured.err
        assert str(hermetic.sln_hidden) in captured.err

    def test_failed_restore_does_not_override_a_real_stryker_failure(
        self, hermetic, monkeypatch, capsys
    ):
        # A real Stryker failure (42) takes priority — the restore failure
        # is still logged, but doesn't clobber the more informative exit
        # code the operator needs to act on.
        _install_fakes(monkeypatch, hermetic, stryker_exit_code=42)
        monkeypatch.setattr(wrapper, "restore_sln", lambda sln, sln_hidden: False)

        rc = run_wrapper(hermetic)

        assert rc == 42
        assert "failed to restore" in capsys.readouterr().err

    def test_refuses_when_stale_hidden_sln_coexists_with_fresh_sln(
        self, hermetic, monkeypatch, capsys
    ):
        _install_fakes(monkeypatch, hermetic)
        # Set up the stale-hidden collision.
        hermetic.sln_hidden.write_text("stale-hidden-content")
        rc = run_wrapper(hermetic)
        assert rc == wrapper.EXIT_STALE_HIDDEN_SLN
        captured = capsys.readouterr()
        # Error names the stale path.
        assert str(hermetic.sln_hidden) in captured.err
        # Fresh .sln untouched.
        assert hermetic.sln.read_text() == "solution stub"
        # And no build / stryker was invoked (refusal was before build).
        assert hermetic.calls == []

    def test_forwards_arguments_to_stryker_unchanged(self, hermetic, monkeypatch):
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(
            hermetic,
            "--mutate",
            "**/Foo.cs",
            "-O",
            "StrykerOutput/probe",
        )
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        assert len(strykers) == 1
        argv = strykers[0]["stryker_args"]
        assert "--mutate" in argv
        assert "**/Foo.cs" in argv
        assert "-O" in argv
        assert "StrykerOutput/probe" in argv

    def test_preset_dotnet_root_is_preserved_in_subprocess_env(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setenv("DOTNET_ROOT", "/custom/dotnet/root")
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic)
        assert rc == 0
        # Every stryker invocation saw the custom DOTNET_ROOT.
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        assert len(strykers) >= 1
        for s in strykers:
            assert s["DOTNET_ROOT"] == "/custom/dotnet/root"

    def test_no_bare_tee_pipeline_in_source(self):
        """Source-lint: the wrapper must not pipe Stryker output through
        `| tee` — that masks the tool's exit code (#550).
        """
        source = (WRAPPER_DIR / "csharp_stryker_net_wrapper.py").read_text()
        # Python subprocess doesn't use shell tee, but guard against a naive
        # ``os.system("... | tee ...")`` sneaking in.
        assert "| tee " not in source
        assert "os.system" not in source or "# noqa: os.system-allowed" in source


# =============================================================================
# default_concurrency + injection — cores-2 default (#667, #681)
# =============================================================================
class TestConcurrencyDefault:
    """Step 2.1: wrapper injects a computed default `-c` value unless the
    caller already forwards one. See plans/mutation-kill-slice-loop-
    refinements.md Slice 2.
    """

    def test_injects_computed_default_when_no_concurrency_present(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic)
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "6"]

    def test_does_not_override_existing_short_form_pass_through(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic, "-c", "3")
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "3"]

    def test_default_concurrency_falls_back_when_cpu_count_is_none(self):
        assert wrapper.default_concurrency(None) == 1

    def test_default_concurrency_computes_cores_minus_two(self):
        assert wrapper.default_concurrency(8) == 6

    def test_default_concurrency_floors_at_one(self):
        assert wrapper.default_concurrency(2) == 1
        assert wrapper.default_concurrency(1) == 1


# =============================================================================
# --stryker-concurrency / STRYKER_MUTANT_CONCURRENCY override (#667, #681)
# =============================================================================
class TestConcurrencyOverride:
    """Step 2.2: explicit CLI flag / env var override the computed default,
    with CLI winning over env, and pass-through always winning over both
    (logging a one-line override note when it conflicts with an explicit
    value). Deliberately NOT named `--concurrency`/`-c` — see the plan's
    naming note (post-review-1 revision).
    """

    def test_explicit_stryker_concurrency_flag_is_forwarded(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic, "--stryker-concurrency", "8")
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "8"]

    def test_env_var_used_when_no_cli_flag(self, hermetic, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        monkeypatch.setenv("STRYKER_MUTANT_CONCURRENCY", "6")
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic)
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "6"]

    def test_cli_flag_wins_over_env_var(self, hermetic, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        monkeypatch.setenv("STRYKER_MUTANT_CONCURRENCY", "6")
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic, "--stryker-concurrency", "8")
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "8"]

    def test_does_not_override_existing_long_form_pass_through(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic, "--concurrency", "3")
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["--concurrency", "3"]

    def test_pass_through_wins_over_explicit_value_and_logs_override(
        self, hermetic, monkeypatch, capsys
    ):
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        _install_fakes(monkeypatch, hermetic)
        rc = run_wrapper(hermetic, "--stryker-concurrency", "8", "-c", "3")
        assert rc == 0
        strykers = [c for c in hermetic.calls if c["kind"] == "stryker"]
        argv = strykers[0]["stryker_args"]
        assert argv == ["-c", "3"]
        captured = capsys.readouterr()
        assert "-c 3" in captured.err
        assert "--stryker-concurrency 8" in captured.err


# =============================================================================
# Concurrent run_stryker() tracking — slice-level parallelism (#561, #732)
# =============================================================================
# csharp_stryker_net_slice_runner.py calls wrapper.run_stryker() concurrently
# from multiple ThreadPoolExecutor worker threads (one per in-flight slice).
# The signal handler's job is to terminate every live Stryker subprocess, not
# just whichever slice happens to be the last one to register. These tests
# use fake Popen-like objects (no real dotnet/Stryker process) so they run
# everywhere, unconditionally — no opt-in env var required.
class _FakePopen:
    """Stand-in for subprocess.Popen: blocks in wait() until terminate() (or
    an external release()) fires, and counts terminate() calls.
    """

    def __init__(self):
        self._terminated = threading.Event()
        self.terminate_calls = 0

    def poll(self):
        return 0 if self._terminated.is_set() else None

    def terminate(self):
        self.terminate_calls += 1
        self._terminated.set()

    def wait(self, timeout=None):
        self._terminated.wait(timeout)
        return 0 if self._terminated.is_set() else None


class TestConcurrentRunStrykerTracking:
    def test_signal_handler_terminates_every_concurrently_running_slice(
        self, tmp_path, monkeypatch
    ):
        fake_procs: list[_FakePopen] = []
        registry_lock = threading.Lock()

        def fake_popen(*args, **kwargs):
            proc = _FakePopen()
            with registry_lock:
                fake_procs.append(proc)
            return proc

        monkeypatch.setattr(wrapper.subprocess, "Popen", fake_popen)

        # Two "slices" call run_stryker() concurrently, exactly as two
        # ThreadPoolExecutor workers would. daemon=True so that if the bug
        # under test leaves one of them permanently blocked in proc.wait(),
        # the test process can still exit instead of hanging CI forever —
        # the ``assert`` below is what should fail, not the process itself.
        threads = [
            threading.Thread(
                target=wrapper.run_stryker,
                kwargs={
                    "stryker_bin": "fake-stryker",
                    "stryker_args": [],
                    "logfile": tmp_path / f"slice-{i}.log",
                },
                daemon=True,
            )
            for i in range(2)
        ]
        for t in threads:
            t.start()

        # Wait until both fake subprocesses are registered and blocked.
        for _ in range(200):
            with registry_lock:
                if len(fake_procs) == 2:
                    break
            time.sleep(0.01)
        assert len(fake_procs) == 2, "both slices should have spawned a process"

        # Exercise the exact termination logic the SIGINT/SIGTERM handler
        # runs, without actually delivering an OS signal — real signal
        # delivery (os.kill(self, SIGINT)) is platform-fragile (it crashed
        # the whole interpreter on native Windows CI rather than raising a
        # catchable KeyboardInterrupt) and is already covered, opt-in and
        # POSIX-only, by TestSignalHandlingPOSIX below.
        wrapper._terminate_all_tracked_processes()

        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive()

        # Every live slice process must be terminated — not just one of them.
        assert [p.terminate_calls for p in fake_procs] == [1, 1]


# =============================================================================
# Signal handling — POSIX only
# =============================================================================
# Windows signal semantics differ fundamentally from POSIX:
#   - Popen.terminate() on Windows calls TerminateProcess(), which is
#     equivalent to SIGKILL — Python signal handlers in the child never run.
#   - Python on Windows doesn't deliver SIGTERM to threads / from other
#     processes via kill; only console-specific SIGINT/SIGBREAK.
#
# The wrapper's signal contract (restore .sln + kill Stryker) is a POSIX
# concept. On Windows, the equivalent guarantee comes from Popen's process-
# tree cleanup on Ctrl-C in a console, which we can't reproduce in pytest.
#
# This class is POSIX-only. The wrapper's cross-platform contract on
# Windows is: normal-exit and non-zero-exit restore .sln (covered by
# TestMainContract, which runs everywhere).
@pytest.mark.skipif(
    sys.platform == "win32" or os.environ.get("MUTATION_WRAPPER_SIGNAL_TESTS") != "1",
    reason=(
        "POSIX signal semantics + needs a real .NET SDK for the wrapper's "
        "dotnet-build step. Opt in with MUTATION_WRAPPER_SIGNAL_TESTS=1 on "
        "a host that has `dotnet` on PATH."
    ),
)
class TestSignalHandlingPOSIX:
    """SIGINT / SIGTERM subprocess tests. Spawn the wrapper with a Python
    fake-Stryker that blocks on a sentinel file, signal the parent, and
    verify the child is reaped + .sln restored.
    """

    def _make_fake_stryker(self, hermetic) -> Path:
        """Write a Python fake-Stryker script that records its PID and
        blocks until the sentinel file is removed. Returns its Path.
        """
        fake_stryker = hermetic.root / "fake_stryker.py"
        fake_stryker.write_text(
            "import os, sys, time, signal as sigmod\n"
            "pid_file = os.environ['STRYKER_PID_FILE']\n"
            "sentinel = os.environ['STRYKER_BLOCK_SENTINEL']\n"
            "with open(pid_file, 'w') as f:\n"
            "    f.write(str(os.getpid()))\n"
            "sigmod.signal(sigmod.SIGTERM, lambda s, f: sys.exit(143))\n"
            "sigmod.signal(sigmod.SIGINT, lambda s, f: sys.exit(130))\n"
            "while os.path.exists(sentinel):\n"
            "    time.sleep(0.1)\n"
        )
        return fake_stryker

    def _spawn_wrapper_subprocess(self, hermetic, sentinel_path: Path):
        """Spawn the wrapper in a subprocess with a Python fake-Stryker that
        blocks on `sentinel_path`. Returns (proc, stryker_pid_file_path).
        """
        stryker_pid_file = hermetic.root / "stryker.pid"
        fake_stryker = self._make_fake_stryker(hermetic)

        # This class spawns the REAL wrapper subprocess, so the monkeypatched
        # build_project does NOT apply — the wrapper runs a real `dotnet build
        # <sln>`. main() aborts before spawning Stryker if that build returns
        # non-zero (see the wrapper's `if rc != 0: return rc`), so the `.sln`
        # must be a VALID solution the SDK builds clean. The global fixture's
        # "solution stub" is not — a real build fails it with MSB5010. Write a
        # validly-formatted empty solution instead: the SDK builds it with a
        # harmless "no project to restore" warning and exits 0, which is all
        # the signal path needs (it never inspects the build output). This is
        # why the class requires a real .NET SDK on PATH (#1222).
        hermetic.sln.write_text(
            "Microsoft Visual Studio Solution File, Format Version 12.00\n"
            "# Visual Studio Version 17\n"
        )

        env = os.environ.copy()
        env["STRYKER_BLOCK_SENTINEL"] = str(sentinel_path)
        env["STRYKER_PID_FILE"] = str(stryker_pid_file)

        # Point --stryker-bin at a Python-invocation. Simplest: use the
        # current interpreter as the stryker-bin and pass the fake-stryker
        # script as the first arg. The wrapper forwards `"$@"` to it.
        proc = subprocess.Popen(
            [
                sys.executable,
                str(WRAPPER_DIR / "csharp_stryker_net_wrapper.py"),
                "--sln",
                str(hermetic.sln),
                "--shim-project",
                "",  # skip shim; only the .sln is built
                "--stryker-bin",
                sys.executable,
                "--logfile",
                str(hermetic.logfile),
                str(fake_stryker),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(hermetic.root),
        )
        # Wait for the fake Stryker to be running (its PID file appears).
        for _ in range(100):
            if stryker_pid_file.exists():
                break
            time.sleep(0.05)
        # Note: if the wrapper failed before spawning stryker (e.g. no .NET SDK
        # on PATH, or `dotnet build` returned non-zero), the PID file will be
        # absent. Surface that clearly.
        if not stryker_pid_file.exists():
            proc.terminate()
            out, err = proc.communicate(timeout=5)
            pytest.fail(
                f"fake Stryker never started. wrapper stdout={out!r} stderr={err!r}"
            )
        return proc, stryker_pid_file

    def test_sigterm_restores_sln_and_kills_stryker(self, hermetic):
        sentinel = hermetic.root / "block"
        sentinel.touch()
        try:
            proc, pid_file = self._spawn_wrapper_subprocess(hermetic, sentinel)
            stryker_pid = int(pid_file.read_text().strip())

            proc.terminate()  # SIGTERM
            proc.wait(timeout=10)
        finally:
            sentinel.unlink(missing_ok=True)

        # .sln restored.
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()

        # Stryker child reaped — kill -0 on the PID should fail.
        for _ in range(50):
            try:
                os.kill(stryker_pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                break
        with pytest.raises(ProcessLookupError):
            os.kill(stryker_pid, 0)

    def test_sigint_restores_sln_and_kills_stryker(self, hermetic):
        sentinel = hermetic.root / "block"
        sentinel.touch()
        try:
            proc, pid_file = self._spawn_wrapper_subprocess(hermetic, sentinel)
            stryker_pid = int(pid_file.read_text().strip())

            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
        finally:
            sentinel.unlink(missing_ok=True)

        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()

        for _ in range(50):
            try:
                os.kill(stryker_pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                break
        with pytest.raises(ProcessLookupError):
            os.kill(stryker_pid, 0)


# =============================================================================
# run_stryker line-callback — additive, tee'd, backward-compatible (#1136 S5.1)
# =============================================================================
class _FakeStreamPopen:
    """Popen stand-in for the streaming (callback) path. ``stdout`` is a
    single byte-line iterator so the drain loop resumes where the main loop
    broke off. ``poll()`` returns None until terminate()/exhaustion.
    """

    def __init__(self, lines, exit_code=0):
        self.stdout = iter([line.encode("utf-8") for line in lines])
        self._exit = exit_code
        self.terminated = False
        self.terminate_calls = 0

    def terminate(self):
        self.terminate_calls += 1
        self.terminated = True

    def poll(self):
        return self._exit if self.terminated else None

    def wait(self, timeout=None):
        return self._exit


class _HangingStreamPopen:
    """Popen stand-in whose 'grandchild' holds the stdout pipe: ``terminate()``
    is ignored (the child stays alive), only ``kill()`` makes it exit. Every
    ``wait(timeout)`` raises ``TimeoutExpired`` until killed; an unbounded
    ``wait()`` (``timeout is None``) is treated as the bug under test and fails
    fast instead of hanging CI.
    """

    def __init__(self, lines):
        self.stdout = iter([line.encode("utf-8") for line in lines])
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts: list = []
        self._killed = False

    def terminate(self):
        self.terminate_calls += 1  # ignored — a grandchild keeps the child up

    def kill(self):
        self.kill_calls += 1
        self._killed = True

    def poll(self):
        return -9 if self._killed else None

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self._killed:
            return -9
        if timeout is None:
            raise AssertionError("unbounded proc.wait() on abort — regression")
        raise wrapper.subprocess.TimeoutExpired(cmd="stryker", timeout=timeout)


class TestRunStrykerAbortBounded:
    """#1136 review: a grandchild test-host holding the stdout pipe must never
    hang the abort/raise reap. terminate() is escalated to kill() with bounded
    waits, and the child is reaped on both the callback-abort and the
    callback-raise path.
    """

    def _patch_popen(self, monkeypatch, proc):
        monkeypatch.setattr(
            wrapper.subprocess,
            "Popen",
            lambda cmd, stdout=None, stderr=None, cwd=None: proc,
        )

    def test_abort_wait_is_bounded_when_child_ignores_terminate(
        self, tmp_path, monkeypatch
    ):
        proc = _HangingStreamPopen(["ok\n", "5 mutants got status Timeout\n"])
        self._patch_popen(monkeypatch, proc)
        result: dict = {}

        def call():
            result["rc"] = wrapper.run_stryker(
                "fake-bin",
                [],
                tmp_path / "w.log",
                line_callback=lambda ln: "Timeout" in ln,
            )

        t = threading.Thread(target=call, daemon=True)
        t.start()
        t.join(timeout=15)
        assert not t.is_alive(), "run_stryker hung on abort — wait was not bounded"
        # terminate() was tried, then kill() escalated once it was ignored.
        assert proc.terminate_calls >= 1
        assert proc.kill_calls == 1
        # Every wait() the reap issued carried a timeout — none was unbounded.
        assert proc.wait_timeouts
        assert all(to is not None for to in proc.wait_timeouts)
        assert result["rc"] == -9

    def test_callback_raise_reaps_child_when_it_ignores_terminate(
        self, tmp_path, monkeypatch
    ):
        proc = _HangingStreamPopen(["boom\n"])
        self._patch_popen(monkeypatch, proc)

        def cb(_line):
            raise RuntimeError("abort via raise")

        with pytest.raises(RuntimeError, match="abort via raise"):
            wrapper.run_stryker("fake-bin", [], tmp_path / "w.log", line_callback=cb)

        # Reaped despite ignoring terminate(): kill escalation fired, bounded.
        assert proc.terminate_calls >= 1
        assert proc.kill_calls == 1
        assert proc.wait_timeouts
        assert all(to is not None for to in proc.wait_timeouts)


class TestRunStrykerLineCallback:
    """Slice 5 Step 5.1 scenarios. The callback receives each line and can
    abort; the logfile is tee'd (fully populated) when a callback is present;
    and callback-less callers keep the original logfile-redirect behavior.
    """

    def _patch_popen(self, monkeypatch, proc):
        captured = {}

        def fake_popen(cmd, stdout=None, stderr=None, cwd=None):
            captured["cmd"] = cmd
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            captured["cwd"] = cwd
            return proc

        monkeypatch.setattr(wrapper.subprocess, "Popen", fake_popen)
        return captured

    def test_callback_receives_each_output_line(self, tmp_path, monkeypatch):
        proc = _FakeStreamPopen(["one\n", "two\n", "three\n"])
        self._patch_popen(monkeypatch, proc)
        seen = []
        rc = wrapper.run_stryker(
            "fake-bin", [], tmp_path / "w.log", line_callback=lambda ln: seen.append(ln) or False
        )
        assert rc == 0
        assert seen == ["one\n", "two\n", "three\n"]
        assert proc.terminate_calls == 0

    def test_callback_can_abort_and_terminates_process(self, tmp_path, monkeypatch):
        proc = _FakeStreamPopen(["ok\n", "5 mutants got status Timeout\n", "tail\n"])
        self._patch_popen(monkeypatch, proc)
        seen = []

        def cb(line):
            seen.append(line)
            return "Timeout" in line

        wrapper.run_stryker("fake-bin", [], tmp_path / "w.log", line_callback=cb)
        # Callback stopped feeding at the abort line — never saw "tail".
        assert seen == ["ok\n", "5 mutants got status Timeout\n"]
        assert proc.terminate_calls == 1

    def test_logfile_is_fully_populated_when_callback_present(
        self, tmp_path, monkeypatch
    ):
        # Even though the callback aborts on line 2, the remaining buffered
        # output ("tail") is drained so the post-mortem log is complete (tee).
        proc = _FakeStreamPopen(["ok\n", "5 mutants got status Timeout\n", "tail\n"])
        self._patch_popen(monkeypatch, proc)
        logfile = tmp_path / "sub" / "w.log"
        wrapper.run_stryker(
            "fake-bin", [], logfile, line_callback=lambda ln: "Timeout" in ln
        )
        assert logfile.read_text() == "ok\n5 mutants got status Timeout\ntail\n"

    def test_callback_that_raises_terminates_process_and_propagates(
        self, tmp_path, monkeypatch
    ):
        proc = _FakeStreamPopen(["boom\n", "unreached\n"])
        self._patch_popen(monkeypatch, proc)

        def cb(_line):
            raise RuntimeError("abort via raise")

        with pytest.raises(RuntimeError, match="abort via raise"):
            wrapper.run_stryker("fake-bin", [], tmp_path / "w.log", line_callback=cb)
        assert proc.terminate_calls == 1

    def test_cwd_is_forwarded_to_popen(self, tmp_path, monkeypatch):
        proc = _FakeStreamPopen(["done\n"])
        captured = self._patch_popen(monkeypatch, proc)
        wrapper.run_stryker(
            "fake-bin", [], tmp_path / "w.log", line_callback=lambda ln: False, cwd=tmp_path
        )
        assert captured["cwd"] == str(tmp_path)

    def test_callbackless_run_redirects_to_logfile_unchanged(
        self, tmp_path, monkeypatch
    ):
        # No callback → the original path: stdout is redirected to the open
        # logfile handle (never PIPE), and the loop is never iterated.
        class _P:
            def wait(self, timeout=None):
                return 7

        captured = self._patch_popen(monkeypatch, _P())
        rc = wrapper.run_stryker("fake-bin", [], tmp_path / "w.log")
        assert rc == 7
        assert captured["stdout"] is not wrapper.subprocess.PIPE
        assert hasattr(captured["stdout"], "write")
        assert captured["stderr"] == wrapper.subprocess.STDOUT


import signal
