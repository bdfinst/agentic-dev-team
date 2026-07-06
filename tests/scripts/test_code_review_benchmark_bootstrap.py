"""Unit tests for the #949 auto-provisioning of Defects4J/BugsJS homes.

All git-clone / `init.sh` behavior is injected (`run_fn`) — no real
subprocess, network, or git call, matching every other module's unit-test
contract in this harness.
"""

from __future__ import annotations

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
    assert result == {"home": "/some/existing/home", "bin": "defects4j"}
    assert fake.calls == []


def test_ensure_defects4j_home_clones_and_inits_when_missing(tmp_path: Path) -> None:
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

    result = bootstrap.ensure_defects4j_home(None, run_fn=run_fn, cache_dir=tmp_path)
    assert result == {
        "home": str(dest),
        "bin": str(dest / "framework" / "bin" / "defects4j"),
    }
    assert (dest / ".d4j-init-complete").is_file()


def test_ensure_defects4j_home_skips_init_when_marker_already_present(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "defects4j"
    (dest / "framework" / "projects").mkdir(parents=True)
    (dest / "framework" / "bin").mkdir(parents=True)
    (dest / "framework" / "bin" / "defects4j").write_text("#!/bin/sh\n")
    (dest / ".d4j-init-complete").write_text("ok\n", encoding="utf-8")

    fake = _FakeRun()
    result = bootstrap.ensure_defects4j_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result == {
        "home": str(dest),
        "bin": str(dest / "framework" / "bin" / "defects4j"),
    }
    assert fake.calls == []  # neither clone nor init.sh re-run


def test_ensure_defects4j_home_none_on_clone_failure(tmp_path: Path) -> None:
    fake = _FakeRun(returncode=1)
    result = bootstrap.ensure_defects4j_home(None, run_fn=fake, cache_dir=tmp_path)
    assert result is None


def test_ensure_defects4j_home_none_on_init_failure_and_no_marker_written(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "defects4j"

    def run_fn(timeout, argv, **kwargs):
        if argv[0] == "git":
            (dest / "framework" / "projects").mkdir(parents=True)
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="")

    result = bootstrap.ensure_defects4j_home(None, run_fn=run_fn, cache_dir=tmp_path)
    assert result is None
    assert not (dest / ".d4j-init-complete").is_file()


def test_ensure_defects4j_home_skips_clone_when_projects_dir_already_exists(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "defects4j"
    (dest / "framework" / "projects").mkdir(parents=True)
    (dest / "framework" / "bin").mkdir(parents=True)

    def run_fn(timeout, argv, **kwargs):
        assert argv == ["bash", "init.sh"]  # clone must be skipped entirely
        (dest / "framework" / "bin" / "defects4j").write_text("#!/bin/sh\n")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    result = bootstrap.ensure_defects4j_home(None, run_fn=run_fn, cache_dir=tmp_path)
    assert result["home"] == str(dest)
