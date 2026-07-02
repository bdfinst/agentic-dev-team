"""Pytest tests for csharp_stryker_net_wrapper.py — the Python port of
csharp-stryker-net-wrapper.sh (#559, #564, #572).

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

import json
import os
import stat
import subprocess
import sys
import tempfile
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

import csharp_stryker_net_wrapper as wrapper  # noqa: E402


# =============================================================================
# Fixture helpers
# =============================================================================
@pytest.fixture
def hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Per-test hermetic workspace: temp dir + fake dotnet shim on PATH.

    Returns an object with:
      root      — Path to the temp dir (used as cwd)
      sln       — Path to $root/Foo.sln
      sln_hidden — Path to $root/Foo.sln.stryker-hidden
      record_dir — Path to $root/record/, where fake-dotnet writes invocations
      shim_project — Path to $root/tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj
      logfile   — Path to $root/wrapper.log
      invocations() → list of dicts, one per fake-dotnet call
    """
    root = tmp_path
    record_dir = root / "record"
    record_dir.mkdir()

    bin_dir = root / "bin"
    bin_dir.mkdir()

    # Fake dotnet shim — records every invocation into $RECORD_DIR/invocation-NN.
    fake_dotnet = bin_dir / "dotnet"
    if os.name == "nt":
        # On native Windows, PATH resolution uses `dotnet.bat`/`.exe`.
        # We're not targeting native Windows in this test harness — the wrapper
        # is verified on Windows via subprocess-shim tests in a separate pass.
        pytest.skip("Fake-dotnet shim requires POSIX-shell interpreter")

    fake_dotnet.write_text(
        # A Python shim (not bash) so we don't reintroduce the bash fork/wait
        # issues on Git Bash. Cross-platform via the same Python interpreter.
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "record_dir = os.environ['RECORD_DIR']\n"
        "existing = sorted(os.listdir(record_dir))\n"
        "n = len(existing) + 1\n"
        f"rec = os.path.join(record_dir, f'invocation-{{n:02d}}.json')\n"
        "data = {\n"
        "  'ts_ns': time.time_ns(),\n"
        "  'DOTNET_ROOT': os.environ.get('DOTNET_ROOT', ''),\n"
        "  'PWD': os.getcwd(),\n"
        "  'argv': sys.argv[1:],\n"
        "}\n"
        "with open(rec, 'w') as f:\n"
        "  json.dump(data, f)\n"
        "\n"
        "# Dispatch: build always exits 0. stryker respects env sentinels.\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'build':\n"
        "  sys.exit(0)\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'stryker':\n"
        "  code = os.environ.get('FAKE_STRYKER_EXIT_CODE')\n"
        "  if code:\n"
        "    sys.exit(int(code))\n"
        "  block = os.environ.get('FAKE_STRYKER_BLOCK_SENTINEL')\n"
        "  if block:\n"
        "    with open(os.path.join(record_dir, 'stryker.pid'), 'w') as f:\n"
        "      f.write(str(os.getpid()))\n"
        "    while os.path.exists(block):\n"
        "      time.sleep(0.1)\n"
        "  sys.exit(0)\n"
        "sys.exit(0)\n"
    )
    fake_dotnet.chmod(
        fake_dotnet.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    )

    # Also install a stryker shim under the same directory. Runner will call
    # $STRYKER_BIN, which we set to point at this.
    fake_stryker = bin_dir / "dotnet-stryker-fake"
    fake_stryker.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "os.execvp('dotnet', ['dotnet', 'stryker'] + sys.argv[1:])\n"
    )
    fake_stryker.chmod(
        fake_stryker.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    )

    # Prepend bin_dir to PATH so subprocess.Popen finds the fake dotnet.
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("RECORD_DIR", str(record_dir))
    # Pre-set DOTNET_ROOT so probe short-circuits and doesn't require a real SDK.
    monkeypatch.setenv("DOTNET_ROOT", str(root / "fake-dotnet-root"))

    # Change working directory to the hermetic root.
    monkeypatch.chdir(root)

    # Standard project layout.
    sln = root / "Foo.sln"
    sln.write_text("solution stub")
    shim_dir = root / "tests" / "Foo.Tests.Mutation"
    shim_dir.mkdir(parents=True)
    shim_project = shim_dir / "Foo.Tests.Mutation.csproj"
    shim_project.write_text('<Project Sdk="Microsoft.NET.Sdk" />')

    class HermeticCtx:
        pass

    ctx = HermeticCtx()
    ctx.root = root
    ctx.sln = sln
    ctx.sln_hidden = Path(str(sln) + ".stryker-hidden")
    ctx.record_dir = record_dir
    ctx.shim_project = shim_project
    ctx.logfile = root / "wrapper.log"
    ctx.stryker_bin = str(fake_stryker)

    def _invocations() -> list[dict]:
        recs = []
        for p in sorted(record_dir.glob("invocation-*.json")):
            with p.open() as f:
                recs.append(json.load(f))
        return recs

    ctx.invocations = _invocations
    return ctx


def run_wrapper(hermetic, *extra_args, monkeypatch: pytest.MonkeyPatch = None):
    """Invoke wrapper.main() with the given hermetic fixture's paths."""
    args = [
        "--sln",
        str(hermetic.sln),
        "--shim-project",
        str(hermetic.shim_project),
        "--stryker-bin",
        hermetic.stryker_bin,
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
        # dirname of that.
        bin_dir = tmp_path / "custom-install" / "bin"
        bin_dir.mkdir(parents=True)
        exe = bin_dir / "dotnet"
        exe.write_text("stub")
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
        wrapper.restore_sln(sln, hidden)
        assert sln.exists()
        assert sln.read_text() == "stub"

    def test_restore_does_not_clobber_a_fresh_sln(self, tmp_path):
        sln = tmp_path / "Foo.sln"
        sln.write_text("fresh")
        hidden = Path(str(sln) + ".stryker-hidden")
        hidden.write_text("stale")
        wrapper.restore_sln(sln, hidden)
        # Fresh .sln untouched.
        assert sln.read_text() == "fresh"


# =============================================================================
# End-to-end main() — the full wrapper contract
# =============================================================================
class TestMainContract:
    def test_normal_exit_restores_sln(self, hermetic):
        rc = run_wrapper(hermetic)
        assert rc == 0
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()
        assert hermetic.sln.read_text() == "solution stub"

    def test_builds_sln_and_shim_project_before_hiding(self, hermetic):
        rc = run_wrapper(hermetic)
        assert rc == 0
        invs = hermetic.invocations()
        # First two invocations are `dotnet build <sln>` and `dotnet build <shim>`.
        assert len(invs) >= 3
        assert invs[0]["argv"][0] == "build"
        assert str(hermetic.sln) in invs[0]["argv"]
        assert invs[1]["argv"][0] == "build"
        assert "Foo.Tests.Mutation" in " ".join(invs[1]["argv"])
        # Third invocation is `dotnet stryker`.
        assert invs[2]["argv"][0] == "stryker"

    def test_stryker_nonzero_exit_propagates_and_restores(self, hermetic, monkeypatch):
        monkeypatch.setenv("FAKE_STRYKER_EXIT_CODE", "42")
        rc = run_wrapper(hermetic)
        assert rc == 42
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()

    def test_refuses_when_stale_hidden_sln_coexists_with_fresh_sln(
        self, hermetic, capsys
    ):
        # Set up the stale-hidden collision.
        hermetic.sln_hidden.write_text("stale-hidden-content")
        rc = run_wrapper(hermetic)
        assert rc == wrapper.EXIT_STALE_HIDDEN_SLN
        captured = capsys.readouterr()
        # Error names the stale path.
        assert str(hermetic.sln_hidden) in captured.err
        # Fresh .sln untouched.
        assert hermetic.sln.read_text() == "solution stub"

    def test_forwards_arguments_to_stryker_unchanged(self, hermetic):
        rc = run_wrapper(
            hermetic,
            "--mutate",
            "**/Foo.cs",
            "-O",
            "StrykerOutput/probe",
        )
        assert rc == 0
        invs = hermetic.invocations()
        # Find the stryker invocation.
        stryker_invs = [i for i in invs if i["argv"] and i["argv"][0] == "stryker"]
        assert len(stryker_invs) == 1
        argv = stryker_invs[0]["argv"]
        # Args land after the leading `stryker` token.
        assert "--mutate" in argv
        assert "**/Foo.cs" in argv
        assert "-O" in argv
        assert "StrykerOutput/probe" in argv

    def test_preset_dotnet_root_is_preserved_in_subprocess_env(
        self, hermetic, monkeypatch
    ):
        monkeypatch.setenv("DOTNET_ROOT", "/custom/dotnet/root")
        rc = run_wrapper(hermetic)
        assert rc == 0
        invs = hermetic.invocations()
        # Every invocation saw the custom DOTNET_ROOT.
        for inv in invs:
            assert inv["DOTNET_ROOT"] == "/custom/dotnet/root"

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
# Signal handling — the whole reason for the Python rewrite (#571/#572)
# =============================================================================
class TestSignalHandling:
    """SIGINT / SIGTERM tests. These run in a subprocess so the parent
    pytest process isn't itself signaled. The wrapper's contract: on any
    signal, kill the Stryker child, restore .sln, exit non-zero.
    """

    def _spawn_wrapper_subprocess(self, hermetic, sentinel_path: Path):
        """Spawn the wrapper in a subprocess with an infinite-blocking fake
        Stryker (via FAKE_STRYKER_BLOCK_SENTINEL). Returns the Popen handle.
        """
        env = os.environ.copy()
        env["FAKE_STRYKER_BLOCK_SENTINEL"] = str(sentinel_path)
        env["RECORD_DIR"] = str(hermetic.record_dir)
        proc = subprocess.Popen(
            [
                sys.executable,
                str(WRAPPER_DIR / "csharp_stryker_net_wrapper.py"),
                "--sln",
                str(hermetic.sln),
                "--shim-project",
                str(hermetic.shim_project),
                "--stryker-bin",
                hermetic.stryker_bin,
                "--logfile",
                str(hermetic.logfile),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(hermetic.root),
        )
        # Wait for the fake Stryker to be running (its PID file appears).
        stryker_pid_file = hermetic.record_dir / "stryker.pid"
        for _ in range(100):
            if stryker_pid_file.exists():
                break
            time.sleep(0.05)
        assert stryker_pid_file.exists(), "fake Stryker never started"
        return proc, stryker_pid_file

    def test_sigterm_restores_sln_and_kills_stryker(self, hermetic):
        sentinel = hermetic.root / "block"
        sentinel.touch()
        proc, pid_file = self._spawn_wrapper_subprocess(hermetic, sentinel)
        stryker_pid = int(pid_file.read_text().strip())

        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=10)
        finally:
            sentinel.unlink(missing_ok=True)

        # .sln restored.
        assert hermetic.sln.exists()
        assert not hermetic.sln_hidden.exists()
        assert hermetic.sln.read_text() == "solution stub"

        # Stryker child reaped — kill -0 on the PID should fail.
        for _ in range(50):
            try:
                os.kill(stryker_pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                break
        with pytest.raises(ProcessLookupError):
            os.kill(stryker_pid, 0)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGINT semantics differ on Windows; SIGTERM test covers the invariant",
    )
    def test_sigint_restores_sln_and_kills_stryker(self, hermetic):
        sentinel = hermetic.root / "block"
        sentinel.touch()
        proc, pid_file = self._spawn_wrapper_subprocess(hermetic, sentinel)
        stryker_pid = int(pid_file.read_text().strip())

        proc.send_signal(signal.SIGINT)
        try:
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


import signal  # noqa: E402 — used only by the signal tests above
