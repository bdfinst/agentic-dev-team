"""Tests for scripts/install-java-static-analysis.py — the pinned, repo-local
PMD installer backing the Java static-analysis lane.

The installer is Python 3.8+ stdlib-only (ADR 0014) and installs a pinned
PMD distribution into a repo-local, gitignored ``.pmd/`` directory (or
``PMD_INSTALL_DIR`` when set). Detection is repo-local first, then PATH.

No test here touches the network: every in-process run stubs
``urllib.request.urlretrieve`` to fail loudly, so a short-circuit path that
accidentally reaches the download is a test failure, not a download.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "install-java-static-analysis.py"

# Modules the installer may import — all stdlib, per ADR 0014.
ALLOWED_IMPORTS = {
    "os",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "urllib",
    "urllib.request",
    "zipfile",
    "pathlib",
}

LAUNCHER_NAME = "pmd.bat" if os.name == "nt" else "pmd"


def _load_installer():
    spec = importlib.util.spec_from_file_location(
        "install_java_static_analysis", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def installer(monkeypatch):
    module = _load_installer()
    monkeypatch.setattr(
        module.urllib.request,
        "urlretrieve",
        lambda *a, **k: pytest.fail("installer attempted a network download"),
    )
    return module


def _fake_which(mapping):
    return lambda name: mapping.get(name)


def _make_launcher(install_dir: Path, version: str) -> Path:
    bin_dir = install_dir / f"pmd-bin-{version}" / "bin"
    bin_dir.mkdir(parents=True)
    launcher = bin_dir / LAUNCHER_NAME
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o755)
    return launcher


def test_installer_exists_and_is_stdlib_only():
    assert SCRIPT.is_file(), "scripts/install-java-static-analysis.py missing"
    tree = ast.parse(SCRIPT.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= ALLOWED_IMPORTS, (
        f"non-stdlib (or unexpected) imports: {sorted(imported - ALLOWED_IMPORTS)}"
    )


def test_missing_java_exits_1_with_actionable_message(installer, monkeypatch, capsys):
    monkeypatch.setattr(installer.shutil, "which", _fake_which({}))
    assert installer.main() == 1
    assert "java" in capsys.readouterr().err.lower()


def test_missing_java_exits_1_end_to_end(tmp_path):
    """Black-box run with an empty PATH — no java resolvable anywhere."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={"PATH": str(empty)},
        check=False,
    )
    assert result.returncode == 1
    assert "required" in result.stderr.lower()


def test_existing_repo_local_install_short_circuits(installer, monkeypatch, tmp_path, capsys):
    """Re-running from a repo that already has .pmd/ exits 0 without any
    download — the repo-local probe wins before the PATH fallback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PMD_INSTALL_DIR", raising=False)
    monkeypatch.setattr(
        installer.shutil, "which", _fake_which({"java": "/usr/bin/java"})
    )
    launcher = _make_launcher(tmp_path / ".pmd", installer.PMD_VERSION)
    assert installer.main() == 0
    out = capsys.readouterr().out
    assert "already installed" in out
    assert str(launcher) in out


def test_repo_local_probe_wins_over_path_pmd(installer, monkeypatch, tmp_path, capsys):
    """With both a repo-local install and a PATH pmd present, the repo-local
    one is reported — detection is repo-local first, then PATH."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PMD_INSTALL_DIR", raising=False)
    monkeypatch.setattr(
        installer.shutil,
        "which",
        _fake_which({"java": "/usr/bin/java", "pmd": "/usr/local/bin/pmd"}),
    )
    _make_launcher(tmp_path / ".pmd", installer.PMD_VERSION)
    assert installer.main() == 0
    assert "on PATH" not in capsys.readouterr().out


def test_path_pmd_short_circuits_when_no_repo_local_install(
    installer, monkeypatch, tmp_path, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PMD_INSTALL_DIR", raising=False)
    monkeypatch.setattr(
        installer.shutil,
        "which",
        _fake_which({"java": "/usr/bin/java", "pmd": "/usr/local/bin/pmd"}),
    )

    class _Version:
        stdout = "PMD 0.0.0\n"

    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **k: _Version())
    assert installer.main() == 0
    assert "already installed on PATH" in capsys.readouterr().out


def test_pmd_install_dir_env_override_is_honored(installer, monkeypatch, tmp_path, capsys):
    custom = tmp_path / "custom-pmd-home"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PMD_INSTALL_DIR", str(custom))
    monkeypatch.setattr(
        installer.shutil, "which", _fake_which({"java": "/usr/bin/java"})
    )
    launcher = _make_launcher(custom, installer.PMD_VERSION)
    assert installer.main() == 0
    assert str(launcher) in capsys.readouterr().out


def test_version_pin_lives_only_in_the_installer():
    """The PMD pin appears in exactly one non-generated file: the installer's
    PMD_VERSION constant. plugins/dev-team/CHANGELOG.md is excluded — it is
    release-please-generated and happens to contain the same literal as a
    past plugin release version."""
    module = _load_installer()
    pattern = module.PMD_VERSION.replace(".", r"\.")
    result = subprocess.run(
        ["git", "grep", "-n", "--untracked", "-e", pattern],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    files = {
        line.split(":", 1)[0]
        for line in result.stdout.splitlines()
        if line.strip()
    }
    files.discard("plugins/dev-team/CHANGELOG.md")
    assert files == {"scripts/install-java-static-analysis.py"}, (
        f"PMD version literal leaked outside the installer: {sorted(files)}"
    )


def test_repo_gitignores_the_pmd_install_dir():
    lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".pmd/" in lines


def test_installer_reminds_about_gitignore_without_mutating_it():
    """The installer prints a reminder when the target repo lacks a .pmd/
    gitignore entry; it never edits .gitignore itself."""
    source = SCRIPT.read_text()
    assert "Reminder" in source
    assert ".gitignore" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("write_text", "open"):
            # No .gitignore writes: the only file writes are inside the
            # tempdir download path (zip extraction handles the rest).
            assert "gitignore" not in ast.dump(node).lower()
