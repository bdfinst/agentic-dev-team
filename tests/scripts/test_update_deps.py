"""Tests for scripts/update_deps.py — recursive package.json discovery and
per-directory `npx npm-check-updates` + `npm install` runner.

find_package_json_dirs' exclusion logic is the risky part: node_modules/
fixtures are excluded at any depth, but evals/tests are anchored to the
top-level segment only (a real Node project nested under some other tree
that happens to be named "tests" must still be updated). The tests below
exercise both the anchored and depth-agnostic sides, plus the exact-segment
(not substring) matching that makes "testservice" distinct from "tests".

_run must never raise — a missing npx/npm binary or a hang both have to
surface as a plain False so main()'s failed-directory list and exit code
stay accurate, rather than an uncaught exception aborting every directory
after the one that failed.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_deps


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    monkeypatch.setattr(update_deps, "REPO_ROOT", tmp_path)
    return tmp_path


def _touch_package_json(directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text("{}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# find_package_json_dirs
# ---------------------------------------------------------------------------


def test_root_level_package_json_is_included(repo_root):
    _touch_package_json(repo_root)
    assert update_deps.find_package_json_dirs() == [repo_root]


def test_no_package_json_anywhere_returns_empty_list(repo_root):
    assert update_deps.find_package_json_dirs() == []


def test_node_modules_excluded_at_any_depth(repo_root):
    _touch_package_json(repo_root)
    _touch_package_json(repo_root / "node_modules" / "some-dep")
    _touch_package_json(repo_root / "packages" / "app" / "node_modules" / "nested-dep")
    assert update_deps.find_package_json_dirs() == [repo_root]


def test_fixtures_excluded_at_any_depth(repo_root):
    _touch_package_json(repo_root)
    _touch_package_json(repo_root / "plugins" / "x" / "fixtures" / "sample")
    assert update_deps.find_package_json_dirs() == [repo_root]


def test_top_level_evals_and_tests_excluded(repo_root):
    _touch_package_json(repo_root)
    _touch_package_json(repo_root / "evals" / "some-benchmark")
    _touch_package_json(repo_root / "tests" / "some-fixture")
    assert update_deps.find_package_json_dirs() == [repo_root]


def test_tests_dir_not_anchored_at_top_level_is_not_excluded(repo_root):
    """A real Node project nested under some other tree, merely named
    "tests", is not an eval/test fixture and must still be updated — only
    a TOP-LEVEL evals/tests segment is excluded."""
    nested = repo_root / "packages" / "app" / "tests"
    _touch_package_json(nested)
    assert update_deps.find_package_json_dirs() == [nested]


def test_exact_segment_match_not_substring(repo_root):
    """"testservice" and "my-fixtures-lib" must not be excluded merely for
    containing "tests"/"fixtures" as a substring — exclusion is by exact
    path-segment name."""
    testservice = repo_root / "testservice"
    fixtures_lib = repo_root / "my-fixtures-lib"
    _touch_package_json(testservice)
    _touch_package_json(fixtures_lib)
    assert update_deps.find_package_json_dirs() == sorted([testservice, fixtures_lib])


def test_results_are_sorted(repo_root):
    b_dir = repo_root / "packages" / "b"
    a_dir = repo_root / "packages" / "a"
    _touch_package_json(b_dir)
    _touch_package_json(a_dir)
    assert update_deps.find_package_json_dirs() == [a_dir, b_dir]


# ---------------------------------------------------------------------------
# _run — never raises
# ---------------------------------------------------------------------------


def test_run_returns_true_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=0)
    )
    assert update_deps._run(["true"], tmp_path) is True


def test_run_returns_false_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=1)
    )
    assert update_deps._run(["false"], tmp_path) is False


def test_run_returns_false_on_missing_binary(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("no such file or directory: npx")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert update_deps._run(["npx", "whatever"], tmp_path) is False


def test_run_returns_false_on_timeout(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["npm", "install"], timeout=600)

    monkeypatch.setattr(subprocess, "run", _raise)
    assert update_deps._run(["npm", "install"], tmp_path) is False


# ---------------------------------------------------------------------------
# update_one
# ---------------------------------------------------------------------------


def test_update_one_dry_run_never_invokes_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(update_deps, "REPO_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    assert update_deps.update_one(tmp_path, dry_run=True) is True
    assert calls == []


def test_update_one_skips_install_when_ncu_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(update_deps, "REPO_ROOT", tmp_path)
    commands_run = []

    def _fake_run(cmd, **kwargs):
        commands_run.append(cmd)
        is_ncu = "npm-check-updates" in cmd[2] if len(cmd) > 2 else False
        return subprocess.CompletedProcess(cmd, returncode=1 if is_ncu else 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert update_deps.update_one(tmp_path, dry_run=False) is False
    assert len(commands_run) == 1  # npm install never ran


def test_update_one_true_when_both_succeed(tmp_path, monkeypatch):
    monkeypatch.setattr(update_deps, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=0)
    )
    assert update_deps.update_one(tmp_path, dry_run=False) is True


def test_update_one_false_when_install_fails_after_ncu_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(update_deps, "REPO_ROOT", tmp_path)

    def _fake_run(cmd, **kwargs):
        is_install = cmd[:2] == ["npm", "install"]
        return subprocess.CompletedProcess(cmd, returncode=1 if is_install else 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert update_deps.update_one(tmp_path, dry_run=False) is False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_reports_no_targets(repo_root, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["update_deps.py"])
    assert update_deps.main() == 0
    assert "No package.json files found" in capsys.readouterr().out


def test_main_dry_run_never_invokes_subprocess(repo_root, monkeypatch):
    _touch_package_json(repo_root)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(sys, "argv", ["update_deps.py", "--dry-run"])
    assert update_deps.main() == 0
    assert calls == []


def test_main_aggregates_failures_and_exits_nonzero(repo_root, monkeypatch, capsys):
    _touch_package_json(repo_root / "a")
    _touch_package_json(repo_root / "b")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=1)
    )
    monkeypatch.setattr(sys, "argv", ["update_deps.py"])
    exit_code = update_deps.main()
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Failed to update:" in err
    assert "a" in err and "b" in err


def test_main_exit_zero_when_all_succeed(repo_root, monkeypatch):
    _touch_package_json(repo_root)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode=0)
    )
    monkeypatch.setattr(sys, "argv", ["update_deps.py"])
    assert update_deps.main() == 0
