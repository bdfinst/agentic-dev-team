"""Pytest tests for scripts/recon_inventory.py (#615 / #572 Phase 3).

Mirrors the recon-inventory cases from
``tests/scripts/codebase_recon_tests.bats``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "recon_inventory.py"


def _git(*args, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _mk_git_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.txt").write_text("a\n")
    (root / "src" / "b.txt").write_text("b\n")
    _git("init", "-q", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)


def test_missing_root_arg_usage_error() -> None:
    r = _run()
    assert r.returncode == 2
    assert "Usage" in r.stderr


def test_nonexistent_root_returns_3(tmp_path: Path) -> None:
    r = _run(str(tmp_path / "nope"))
    assert r.returncode == 3


def test_git_repo_lists_ls_files(tmp_path: Path) -> None:
    _mk_git_project(tmp_path)
    r = _run(str(tmp_path))
    assert r.returncode == 0
    files = r.stdout.strip().split("\n")
    assert sorted(files) == ["src/a.txt", "src/b.txt"]


def test_force_filesystem_walk_switches_source(tmp_path: Path) -> None:
    _mk_git_project(tmp_path)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("n\n")
    # Under git mode this file IS listed (not gitignored), so we compare
    # against the fs-walk mode which prunes it.
    r_git = _run(str(tmp_path))
    r_fs = _run(str(tmp_path), "--force-filesystem-walk")
    assert "node_modules/x.js" not in r_fs.stdout
    # git mode WOULD include it if it were tracked, but here it isn't:
    assert "node_modules/x.js" not in r_git.stdout


def test_fs_walk_no_git(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.txt").write_text("1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("n\n")
    r = _run(str(tmp_path))
    assert r.returncode == 0
    files = r.stdout.strip().split("\n")
    assert "src/one.txt" in files
    assert "node_modules/x.js" not in files


def test_fs_walk_prunes_dsstore(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.txt").write_text("1\n")
    (tmp_path / "src" / ".DS_Store").write_text("mac\n")
    r = _run(str(tmp_path))
    assert ".DS_Store" not in r.stdout


def test_emit_main_json(tmp_path: Path) -> None:
    _mk_git_project(tmp_path)
    out_path = tmp_path / "main.json"
    r = _run(
        str(tmp_path),
        "--slug",
        "myproj",
        "--emit-main-inventory-json",
        str(out_path),
    )
    assert r.returncode == 0
    payload = json.loads(out_path.read_text())
    assert payload["source"] == "git-ls-files"
    assert payload["count"] == 2
    assert payload["sibling_ref"] == "recon-myproj.inventory.txt"


def test_slug_derived_from_basename(tmp_path: Path) -> None:
    project = tmp_path / "My_Weird-Project"
    project.mkdir()
    _mk_git_project(project)
    out_path = tmp_path / "main.json"
    _run(str(project), "--emit-main-inventory-json", str(out_path))
    payload = json.loads(out_path.read_text())
    # Lowercased, invalid chars replaced with `-`, collapsed.
    assert payload["sibling_ref"] == "recon-my_weird-project.inventory.txt"


def test_sorted_output_is_lc_all_c(tmp_path: Path) -> None:
    (tmp_path / "Zed.txt").write_text("z\n")
    (tmp_path / "alpha.txt").write_text("a\n")
    (tmp_path / "1.txt").write_text("one\n")
    r = _run(str(tmp_path))
    assert r.returncode == 0
    lines = r.stdout.strip().split("\n")
    # LC_ALL=C: uppercase before lowercase.
    assert lines == ["1.txt", "Zed.txt", "alpha.txt"]


def test_unknown_flag_usage_error(tmp_path: Path) -> None:
    r = _run(str(tmp_path), "--wat")
    assert r.returncode == 2


def test_broken_symlink_logged_to_stderr(tmp_path: Path) -> None:
    """In git mode, a committed dangling symlink is logged and dropped."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.txt").write_text("ok\n")
    os.symlink("nonexistent.txt", tmp_path / "src" / "dangling.txt")
    _git("init", "-q", cwd=tmp_path)
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "seed", cwd=tmp_path)
    r = _run(str(tmp_path))
    assert r.returncode == 0
    assert "BROKEN_SYMLINK" in r.stderr
    assert "dangling.txt" in r.stderr
    # Dangling symlink is dropped from inventory.
    assert "dangling.txt" not in r.stdout


def test_fs_walk_skips_symlinks_silently(tmp_path: Path) -> None:
    """fs-walk mode uses `find -type f` semantics — symlinks are just skipped
    without a BROKEN_SYMLINK log entry (they aren't regular files)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.txt").write_text("ok\n")
    os.symlink("nonexistent.txt", tmp_path / "src" / "dangling.txt")
    r = _run(str(tmp_path))
    assert r.returncode == 0
    assert "BROKEN_SYMLINK" not in r.stderr
    assert "dangling.txt" not in r.stdout
