"""Tests for `resolve_defects4j_env()` (#951).

No real subprocess/macOS dependency — `run_fn` is faked and platform
checks are monkeypatched, so these run identically on any CI host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from adapters import bootstrap


def _fake_run_fn(returncode: int, stdout: str):
    def _run(_seconds, _argv, **_kwargs):
        return subprocess.CompletedProcess(
            args=_argv, returncode=returncode, stdout=stdout, stderr=""
        )

    return _run


@pytest.fixture
def no_perl5_home(monkeypatch, tmp_path):
    """Isolate `Path.home()` from the real machine's `~/perl5` (if any) so
    Java-only assertions don't depend on whether local::lib is installed."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(bootstrap.Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


def test_resolve_defects4j_env_noop_off_macos(monkeypatch, no_perl5_home):
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    base_env = {"PATH": "/usr/bin"}
    env = bootstrap.resolve_defects4j_env(
        base_env=base_env, run_fn=_fake_run_fn(0, "/opt/java11\n")
    )
    assert env == base_env
    assert env is not base_env  # never mutates the caller's dict


def test_resolve_defects4j_env_sets_java_home_on_macos(monkeypatch, no_perl5_home):
    monkeypatch.setattr(bootstrap.sys, "platform", "darwin")
    base_env = {"PATH": "/usr/bin"}
    env = bootstrap.resolve_defects4j_env(
        base_env=base_env, run_fn=_fake_run_fn(0, "/opt/java11\n")
    )
    assert env["JAVA_HOME"] == "/opt/java11"
    assert env["PATH"].startswith(str(Path("/opt/java11") / "bin"))
    assert env["PATH"].endswith("/usr/bin")


def test_resolve_defects4j_env_no_java11_found(monkeypatch, no_perl5_home):
    monkeypatch.setattr(bootstrap.sys, "platform", "darwin")
    base_env = {"PATH": "/usr/bin"}
    env = bootstrap.resolve_defects4j_env(base_env=base_env, run_fn=_fake_run_fn(1, ""))
    assert "JAVA_HOME" not in env
    assert env["PATH"] == "/usr/bin"


def test_resolve_defects4j_env_sets_perl5lib_when_present(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / "perl5" / "lib" / "perl5").mkdir(parents=True)
    monkeypatch.setattr(bootstrap.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")

    env = bootstrap.resolve_defects4j_env(base_env={}, run_fn=_fake_run_fn(1, ""))

    expected = str(fake_home / "perl5" / "lib" / "perl5")
    assert env["PERL5LIB"] == expected


def test_resolve_defects4j_env_preserves_existing_perl5lib(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / "perl5" / "lib" / "perl5").mkdir(parents=True)
    monkeypatch.setattr(bootstrap.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")

    env = bootstrap.resolve_defects4j_env(
        base_env={"PERL5LIB": "/existing/lib"}, run_fn=_fake_run_fn(1, "")
    )

    expected_prefix = str(fake_home / "perl5" / "lib" / "perl5")
    assert env["PERL5LIB"] == f"{expected_prefix}:/existing/lib"


def test_resolve_defects4j_env_no_perl5lib_when_absent(monkeypatch, no_perl5_home):
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")

    env = bootstrap.resolve_defects4j_env(base_env={}, run_fn=_fake_run_fn(1, ""))

    assert "PERL5LIB" not in env
