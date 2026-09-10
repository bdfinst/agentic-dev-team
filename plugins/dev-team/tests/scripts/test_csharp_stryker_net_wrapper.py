"""Unit tests for skills/mutation-testing/scripts/csharp_stryker_net_wrapper.py.

Covers a regression fix: the wrapper's ``--stryker-bin`` default (and the
shipped slice runner's matching default) previously assumed a **global**
Stryker.NET install — a bare ``dotnet-stryker`` executable reachable
directly on ``PATH``. The skill's own docs recommend a **local** tool-
manifest install instead (SKILL.md's "Prefer a local install"), but a local
tool's command name is never placed on ``PATH`` — it is only reachable
through ``dotnet``'s own verb-resolution convention (``dotnet stryker``
finds the local ``dotnet-stryker`` tool). Invoking the previous default
literally as a subprocess therefore failed outright for the documented,
preferred install path. ``build_stryker_argv`` fixes this by auto-detecting
from ``stryker_bin`` whether to insert the ``stryker`` verb.
"""

from __future__ import annotations

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

import csharp_stryker_net_wrapper as wrapper
from csharp_stryker_net_wrapper import build_stryker_argv


def test_dotnet_stryker_bin_inserts_the_stryker_verb():
    argv = build_stryker_argv("dotnet", ["--config-file", "stryker-config.json"])

    assert argv == ["dotnet", "stryker", "--config-file", "stryker-config.json"]


def test_explicit_global_install_binary_is_used_unchanged():
    argv = build_stryker_argv("dotnet-stryker", ["--config-file", "stryker-config.json"])

    assert argv == ["dotnet-stryker", "--config-file", "stryker-config.json"]


def test_an_arbitrary_custom_binary_name_is_also_used_unchanged():
    argv = build_stryker_argv("/opt/tools/my-stryker-shim", ["-O", "StrykerOutput"])

    assert argv == ["/opt/tools/my-stryker-shim", "-O", "StrykerOutput"]


def test_empty_stryker_args_still_produces_a_valid_argv():
    assert build_stryker_argv("dotnet", []) == ["dotnet", "stryker"]


# ---------------------------------------------------------------------------
# Regression tests (#2145): the local-tool detection used to be exact-string
# equality on "dotnet", so a functionally-equivalent but differently-spelled
# --stryker-bin (an absolute path, a Windows-style ".exe" name) silently fell
# through to the bare-executable branch with no "stryker" verb inserted --
# reproducing the exact failure this module exists to fix.
# ---------------------------------------------------------------------------


def test_windows_style_dotnet_exe_still_inserts_the_stryker_verb():
    argv = build_stryker_argv("dotnet.exe", ["--config-file", "stryker-config.json"])

    assert argv == ["dotnet.exe", "stryker", "--config-file", "stryker-config.json"]


def test_absolute_path_to_dotnet_still_inserts_the_stryker_verb():
    argv = build_stryker_argv("/usr/bin/dotnet", ["-O", "StrykerOutput"])

    assert argv == ["/usr/bin/dotnet", "stryker", "-O", "StrykerOutput"]


def test_mixed_case_dotnet_still_inserts_the_stryker_verb():
    argv = build_stryker_argv("DOTNET", [])

    assert argv == ["DOTNET", "stryker"]


def test_a_binary_that_merely_contains_dotnet_is_not_matched():
    # "my-dotnet-wrapper" is not the dotnet SDK -- must not gain a spurious
    # "stryker" verb it was never built to accept.
    argv = build_stryker_argv("my-dotnet-wrapper", ["-O", "StrykerOutput"])

    assert argv == ["my-dotnet-wrapper", "-O", "StrykerOutput"]


def test_windows_style_absolute_dotnet_exe_path_still_inserts_the_stryker_verb():
    # Backslash-separated -- plain Path() alone treats the whole string as
    # one opaque filename component under a POSIX-flavored Python, missing
    # the "dotnet" stem entirely; the PureWindowsPath fallback catches it
    # regardless of which flavor Path() resolves to on the host running this.
    argv = build_stryker_argv(r"C:\Program Files\dotnet\dotnet.exe", [])

    assert argv == [r"C:\Program Files\dotnet\dotnet.exe", "stryker"]


# ---------------------------------------------------------------------------
# Regression test (test-review finding on #2146): build_stryker_argv above is
# only proven correct in isolation -- nothing proves its result actually
# reaches the real subprocess.Popen call sites in run_stryker() and its
# streaming variant. A revert of the real fix (e.g. dropping the
# build_stryker_argv() call and passing [stryker_bin, *stryker_args] again)
# would have passed every test above.
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimal Popen stand-in for the non-streaming (callback-less) path."""

    def __init__(self, returncode: int = 0):
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode


class _FakeStreamProc:
    """Minimal Popen stand-in for the streaming (line-callback) path: an
    already-exhausted byte-line ``stdout`` iterator, so the read loop exits
    immediately and the reap path never needs to escalate."""

    def __init__(self):
        self.stdout = iter(())
        self._terminated = False

    def terminate(self):
        self._terminated = True

    def poll(self):
        return 0 if self._terminated else None

    def wait(self, timeout=None):
        return 0


def _patch_popen(monkeypatch, proc):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return proc

    monkeypatch.setattr(wrapper.subprocess, "Popen", fake_popen)
    return captured


def test_run_stryker_resolves_the_local_tool_verb_at_the_real_popen_call_site(
    tmp_path, monkeypatch
):
    captured = _patch_popen(monkeypatch, _FakeProc())
    wrapper.run_stryker("dotnet", ["--config-file", "stryker-config.json"], tmp_path / "w.log")
    assert captured["cmd"] == ["dotnet", "stryker", "--config-file", "stryker-config.json"]


def test_run_stryker_non_dotnet_bin_reaches_popen_unchanged(tmp_path, monkeypatch):
    captured = _patch_popen(monkeypatch, _FakeProc())
    wrapper.run_stryker("dotnet-stryker", ["-O", "StrykerOutput"], tmp_path / "w.log")
    assert captured["cmd"] == ["dotnet-stryker", "-O", "StrykerOutput"]


def test_run_stryker_streaming_path_resolves_the_local_tool_verb_at_popen(
    tmp_path, monkeypatch
):
    """Same regression as above, at the SEPARATE subprocess.Popen call site
    inside _run_stryker_streaming (used whenever a line_callback is passed)."""
    captured = _patch_popen(monkeypatch, _FakeStreamProc())
    wrapper.run_stryker(
        "dotnet",
        ["--config-file", "stryker-config.json"],
        tmp_path / "w.log",
        line_callback=lambda _line: False,
    )
    assert captured["cmd"] == ["dotnet", "stryker", "--config-file", "stryker-config.json"]
