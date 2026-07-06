"""Unit tests for the #949 auto-provisioning of Defects4J/BugsJS homes.

All git-clone / `init.sh` behavior is injected (`run_fn`) — no real
subprocess, network, or git call, matching every other module's unit-test
contract in this harness.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from adapters import bootstrap  # noqa: E402


class _FakeRun:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.calls: List[dict] = []

    def __call__(self, timeout, argv, **kwargs):
        self.calls.append({"timeout": timeout, "argv": list(argv), "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=list(argv), returncode=self.returncode, stdout=self.stdout, stderr=""
        )


@pytest.fixture()
def no_java11(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Force `_resolve_java11_home()`/`_resolve_perl5lib()` to resolve to
    `None`, regardless of what's actually installed on the machine running
    this test — hermetic, not host-environment-dependent (#951). Returns a
    `perl5_home` to pass through so `_resolve_perl5lib()` doesn't stumble
    on a real `~/perl5` some dev machine happens to have.
    """
    monkeypatch.setattr(
        bootstrap, "JAVA_HOME_TOOL", str(tmp_path / "no-java-home-tool")
    )
    monkeypatch.setattr(shutil, "which", lambda name: None)
    return tmp_path / "no-perl5-here"


# ---------------------------------------------------------------------------
# BugsJS
# ---------------------------------------------------------------------------


def test_ensure_bugsjs_home_returns_explicit_home_unchanged_without_cloning(
    tmp_path: Path,
) -> None:
    fake = _FakeRun()
    result = bootstrap.ensure_bugsjs_home("/some/existing/home", run_fn=fake)
    assert result == "/some/existing/home"
    assert fake.calls == []


def test_ensure_bugsjs_home_clones_into_cache_when_missing(tmp_path: Path) -> None:
    fake = _FakeRun(returncode=0)
    result = bootstrap.ensure_bugsjs_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result == str(tmp_path / "bugsjs-bug-dataset")
    assert fake.calls[0]["argv"] == [
        "git",
        "clone",
        bootstrap.BUGSJS_REPO_URL,
        str(tmp_path / "bugsjs-bug-dataset"),
    ]


def test_ensure_bugsjs_home_skips_clone_when_cache_already_populated(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "bugsjs-bug-dataset"
    dest.mkdir(parents=True)
    (dest / "main.py").write_text("# stub\n", encoding="utf-8")

    fake = _FakeRun()
    result = bootstrap.ensure_bugsjs_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result == str(dest)
    assert fake.calls == []  # already populated -> no clone attempted


def test_ensure_bugsjs_home_none_on_clone_failure(tmp_path: Path) -> None:
    fake = _FakeRun(returncode=1)
    result = bootstrap.ensure_bugsjs_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Defects4J
# ---------------------------------------------------------------------------


def test_ensure_defects4j_home_returns_explicit_home_unchanged_without_cloning(
    tmp_path: Path,
) -> None:
    fake = _FakeRun()
    result = bootstrap.ensure_defects4j_home("/some/existing/home", run_fn=fake)
    assert result == {"home": "/some/existing/home", "bin": "defects4j", "env": None}
    assert fake.calls == []


def test_ensure_defects4j_home_clones_and_inits_when_missing(
    tmp_path: Path, no_java11: Path
) -> None:
    dest = tmp_path / "defects4j"

    def run_fn(timeout, argv, **kwargs):
        # `git clone` -> materialize the framework/projects tree and the
        # framework/bin/defects4j script `init.sh` will "produce."
        if argv[0] == "git":
            (dest / "framework" / "projects").mkdir(parents=True)
            (dest / "framework" / "bin").mkdir(parents=True)
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        # `bash init.sh` -> "download" the defects4j binary.
        assert argv == ["bash", "init.sh"]
        assert kwargs.get("cwd") == str(dest)
        (dest / "framework" / "bin" / "defects4j").write_text("#!/bin/sh\n")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    result = bootstrap.ensure_defects4j_home(
        None, run_fn=run_fn, cache_dir=tmp_path, perl5_home=no_java11
    )
    assert result == {
        "home": str(dest),
        "bin": str(dest / "framework" / "bin" / "defects4j"),
        "env": None,
    }
    assert (dest / ".d4j-init-complete").is_file()


def test_ensure_defects4j_home_skips_init_when_marker_already_present(
    tmp_path: Path, no_java11: Path
) -> None:
    dest = tmp_path / "defects4j"
    (dest / "framework" / "projects").mkdir(parents=True)
    (dest / "framework" / "bin").mkdir(parents=True)
    (dest / "framework" / "bin" / "defects4j").write_text("#!/bin/sh\n")
    (dest / ".d4j-init-complete").write_text("ok\n", encoding="utf-8")

    fake = _FakeRun()
    result = bootstrap.ensure_defects4j_home(
        None, run_fn=fake, cache_dir=tmp_path, perl5_home=no_java11
    )
    assert result == {
        "home": str(dest),
        "bin": str(dest / "framework" / "bin" / "defects4j"),
        "env": None,
    }
    assert fake.calls == []  # neither clone nor init.sh re-run


def test_ensure_defects4j_home_none_on_clone_failure(tmp_path: Path) -> None:
    fake = _FakeRun(returncode=1)
    result = bootstrap.ensure_defects4j_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result is None


def test_ensure_defects4j_home_none_on_init_failure_and_no_marker_written(
    tmp_path: Path, no_java11: Path
) -> None:
    dest = tmp_path / "defects4j"

    def run_fn(timeout, argv, **kwargs):
        if argv[0] == "git":
            (dest / "framework" / "projects").mkdir(parents=True)
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="")

    result = bootstrap.ensure_defects4j_home(
        None, run_fn=run_fn, cache_dir=tmp_path, perl5_home=no_java11
    )
    assert result is None
    assert not (dest / ".d4j-init-complete").is_file()


def test_ensure_defects4j_home_skips_clone_when_projects_dir_already_exists(
    tmp_path: Path, no_java11: Path
) -> None:
    dest = tmp_path / "defects4j"
    (dest / "framework" / "projects").mkdir(parents=True)
    (dest / "framework" / "bin").mkdir(parents=True)

    def run_fn(timeout, argv, **kwargs):
        assert argv == ["bash", "init.sh"]  # clone must be skipped entirely
        (dest / "framework" / "bin" / "defects4j").write_text("#!/bin/sh\n")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    result = bootstrap.ensure_defects4j_home(
        None, run_fn=run_fn, cache_dir=tmp_path, perl5_home=no_java11
    )
    assert result["home"] == str(dest)


# ---------------------------------------------------------------------------
# Java 11 / Perl CPAN env resolution (#951)
# ---------------------------------------------------------------------------


def test_resolve_java11_home_via_java_home_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_tool = tmp_path / "java_home"
    fake_tool.write_text("#!/bin/sh\n")
    monkeypatch.setattr(bootstrap, "JAVA_HOME_TOOL", str(fake_tool))
    fake = _FakeRun(returncode=0, stdout="/path/to/jdk-11\n")
    assert bootstrap._resolve_java11_home(run_fn=fake) == "/path/to/jdk-11"
    assert fake.calls[0]["argv"] == [str(fake_tool), "-v", "11"]


def test_resolve_java11_home_falls_back_to_brew_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bootstrap, "JAVA_HOME_TOOL", str(tmp_path / "no-such-tool"))
    monkeypatch.setattr(shutil, "which", lambda name: "/opt/homebrew/bin/brew")
    mac_home = tmp_path / "openjdk@11" / "libexec" / "openjdk.jdk" / "Contents" / "Home"
    mac_home.mkdir(parents=True)

    fake = _FakeRun(returncode=0, stdout=f"{tmp_path / 'openjdk@11'}\n")
    result = bootstrap._resolve_java11_home(run_fn=fake)
    assert result == str(mac_home)
    assert fake.calls[0]["argv"] == ["brew", "--prefix", "openjdk@11"]


def test_resolve_java11_home_none_when_nothing_resolves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bootstrap, "JAVA_HOME_TOOL", str(tmp_path / "no-such-tool"))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert bootstrap._resolve_java11_home(run_fn=_FakeRun()) is None


def test_resolve_perl5lib_finds_local_lib_convention(tmp_path: Path) -> None:
    perl5 = tmp_path / "perl5" / "lib" / "perl5"
    perl5.mkdir(parents=True)
    assert bootstrap._resolve_perl5lib(home=tmp_path) == str(perl5)


def test_resolve_perl5lib_none_when_absent(tmp_path: Path) -> None:
    assert bootstrap._resolve_perl5lib(home=tmp_path) is None


def test_build_defects4j_env_none_when_nothing_resolves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bootstrap, "JAVA_HOME_TOOL", str(tmp_path / "no-such-tool"))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = bootstrap.build_defects4j_env(run_fn=_FakeRun(), perl5_home=tmp_path)
    assert result is None


def test_build_defects4j_env_merges_java_home_and_perl5lib(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bootstrap, "JAVA_HOME_TOOL", str(tmp_path / "no-such-tool"))
    monkeypatch.setattr(shutil, "which", lambda name: "/opt/homebrew/bin/brew")
    mac_home = tmp_path / "openjdk@11" / "libexec" / "openjdk.jdk" / "Contents" / "Home"
    mac_home.mkdir(parents=True)
    perl5 = tmp_path / "perl5" / "lib" / "perl5"
    perl5.mkdir(parents=True)

    fake = _FakeRun(returncode=0, stdout=f"{tmp_path / 'openjdk@11'}\n")
    env = bootstrap.build_defects4j_env(run_fn=fake, perl5_home=tmp_path)
    assert env["JAVA_HOME"] == str(mac_home)
    assert env["PATH"].startswith(f"{mac_home}/bin:")
    assert env["PERL5LIB"] == str(perl5)
    # A full env copy, not a partial replacement — the subprocess still
    # inherits everything else (e.g. its own PATH tail).
    import os

    assert env["PATH"].endswith(os.environ.get("PATH", ""))
