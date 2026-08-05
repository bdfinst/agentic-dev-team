"""Unit tests for hooks/lib/git_safe_diff.py (#1477).

The shared `git diff --cached` safety-flag helper extracted out of
`pre_commit_review.py`'s `_staged_names()` and `review_gate_hash.py`'s
`review_gate_hash()`. These tests pin the exact argv each caller relies on
(order matters: `-c diff.relative=false` must precede the `diff`
subcommand, `--ignore-submodules=none` must come last) via a monkeypatched
`subprocess.run`, plus one real-git behavioral check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import git_safe_diff as gsd  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def test_staged_names_shaped_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces `_staged_names()`'s exact original argv."""
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gsd.run_safe_git_diff(["--name-only"], cwd="/tmp/repo", text=True)
    assert captured["argv"] == [
        "git",
        "-c", "diff.relative=false",
        "diff", "--cached",
        "--name-only",
        "--ignore-submodules=none",
    ]
    assert captured["kwargs"]["cwd"] == "/tmp/repo"
    assert captured["kwargs"]["text"] is True


def test_review_gate_hash_shaped_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces `review_gate_hash()`'s exact original argv."""
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gsd.run_safe_git_diff(
        ["--no-color", "--no-ext-diff", "--no-textconv"], cwd=None, text=False
    )
    assert captured["argv"] == [
        "git",
        "-c", "diff.relative=false",
        "diff", "--cached",
        "--no-color", "--no-ext-diff", "--no-textconv",
        "--ignore-submodules=none",
    ]


def test_cwd_none_passes_none_not_string(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gsd.run_safe_git_diff(["--name-only"], cwd=None, text=True)
    assert captured["kwargs"]["cwd"] is None


def test_target_head_shaped_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1476: `target="HEAD"` (the shape `review_gate_hash.py`'s now-deleted
    `working_tree_gate_hash()` passed before #1904 retired it as orphaned)."""
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gsd.run_safe_git_diff(
        ["--no-color", "--no-ext-diff", "--no-textconv"],
        cwd=None,
        text=False,
        target="HEAD",
    )
    assert captured["argv"] == [
        "git",
        "-c", "diff.relative=false",
        "diff", "HEAD",
        "--no-color", "--no-ext-diff", "--no-textconv",
        "--ignore-submodules=none",
    ]


def test_target_none_omits_target_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1476: `_working_tree_modified_names()` passes `target=None` for a
    bare `git diff` (index vs. working tree) — the target argument must be
    omitted entirely, not passed as the literal string "None"."""
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gsd.run_safe_git_diff(["--name-only"], cwd="/tmp/repo", text=True, target=None)
    assert captured["argv"] == [
        "git",
        "-c", "diff.relative=false",
        "diff",
        "--name-only",
        "--ignore-submodules=none",
    ]


def test_real_git_diff_cached_name_only(tmp_path: Path) -> None:
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)

    completed = gsd.run_safe_git_diff(["--name-only"], cwd=tmp_path, text=True)
    assert completed.returncode == 0
    assert completed.stdout.strip() == "a.ts"
