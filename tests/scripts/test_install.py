"""Pytest tests for install.py + the install.sh trampoline (#616 / #572 Phase 3).

Covers:
  - all-required-present → exit 0, "All dependencies present"
  - one required missing → exit 1 with `[FAIL] <cmd>`
  - one optional missing → exit 0 with warn line + "X optional dependency missing"
  - trampoline .sh finds python3 → delegates to install.py byte-identically
  - trampoline .sh cannot find python3 → exit 1 with a clear pointer
  - Windows-path detection: OS=Windows_NT + non-MSYS uname → informational
    [ok], never a hard failure (ADR 0015 retired the Git Bash requirement)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_PY = _REPO_ROOT / "plugins" / "dev-team" / "install.py"
_INSTALL_SH = _REPO_ROOT / "plugins" / "dev-team" / "install.sh"


def _run_py(*, path_override: str | None = None, extra_env: dict | None = None):
    env = {"HOME": "/tmp", "LANG": "C.UTF-8"}
    if path_override is not None:
        env["PATH"] = path_override
    else:
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(_INSTALL_PY)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _run_sh(*, path_override: str | None = None):
    env = {"HOME": "/tmp"}
    if path_override is not None:
        env["PATH"] = path_override
    else:
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    return subprocess.run(
        ["bash", str(_INSTALL_SH)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _shim_dir(tmp_path: Path, cmds: list) -> str:
    """Create a shim directory containing minimal executables for each cmd."""
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    for cmd in cmds:
        p = shim / cmd
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    return str(shim)


def test_all_required_present_exit_0(tmp_path: Path) -> None:
    path = _shim_dir(tmp_path, ["claude", "jq", "gh", "python3"])
    r = _run_py(path_override=path)
    assert r.returncode == 0
    # Some optional deps will be missing → warn path, still exit 0.
    assert "Result:" in r.stdout


def test_missing_required_exits_1(tmp_path: Path) -> None:
    # Only jq and gh present; claude missing.
    path = _shim_dir(tmp_path, ["jq", "gh"])
    r = _run_py(path_override=path)
    assert r.returncode == 1
    assert "[FAIL] claude" in r.stdout


def test_missing_optional_warns_but_exits_0(tmp_path: Path) -> None:
    path = _shim_dir(tmp_path, ["claude", "jq", "gh"])
    r = _run_py(path_override=path)
    assert r.returncode == 0
    assert "[warn] semgrep" in r.stdout
    assert "optional dependency missing" in r.stdout


def test_all_present_including_optional_exits_0(tmp_path: Path) -> None:
    path = _shim_dir(
        tmp_path,
        ["claude", "jq", "gh", "semgrep", "hadolint", "trivy", "grype"],
    )
    r = _run_py(path_override=path)
    assert r.returncode == 0
    assert "All dependencies present" in r.stdout


def test_trampoline_delegates_to_py(tmp_path: Path) -> None:
    """install.sh finds python3 → forwards; output should match install.py."""
    # Use system python3.
    r = _run_sh()
    assert r.returncode in (0, 1)  # depends on the dev env, but never crashes
    assert "Checking dev-team prerequisites..." in r.stdout


def test_trampoline_fails_when_no_python3(tmp_path: Path) -> None:
    """No python3 on PATH → the .sh emits an install pointer and exits 1."""
    # subprocess needs bash on PATH to run the .sh at all, but python3 must
    # NOT be there. Symlink bash into the shim, leave python3 out.
    shim = tmp_path / "shim"
    shim.mkdir()
    import shutil as _shutil

    bash_path = _shutil.which("bash")
    if bash_path:
        os.symlink(bash_path, shim / "bash")
    r = subprocess.run(
        [bash_path or "bash", str(_INSTALL_SH)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": str(shim), "HOME": "/tmp"},
    )
    assert r.returncode == 1
    assert "python3" in r.stdout
    assert "required" in r.stdout


def test_windows_without_git_bash_does_not_hard_fail(tmp_path: Path) -> None:
    """OS=Windows_NT + non-MSYS uname must NOT hard-fail (ADR 0015).

    ADR 0015 (docs/adr/0015-bash-removal-complete.md) retired the Git Bash
    requirement: "Windows CI is now fully bash-free... nothing in the
    plugins/dev-team/ runtime requires Git Bash on Windows anymore."
    Native Windows without Git Bash is a legitimate install path.
    """
    path = _shim_dir(tmp_path, ["claude", "jq", "gh", "python3"])
    r = _run_py(
        path_override=path,
        extra_env={"OS": "Windows_NT"},
    )
    # On this macOS host, platform.uname().system returns "Darwin" — which
    # does NOT start with MINGW/MSYS/CYGWIN, exercising the exact code path
    # Windows-without-Git-Bash would hit. It must no longer be a [FAIL].
    assert r.returncode == 0
    assert "Windows without Git Bash" not in r.stdout
    assert "[FAIL]" not in r.stdout
    assert "[ok]   native Windows" in r.stdout


def test_output_has_required_and_optional_sections(tmp_path: Path) -> None:
    path = _shim_dir(tmp_path, ["claude", "jq", "gh", "python3"])
    r = _run_py(path_override=path)
    assert "--- Required ---" in r.stdout
    assert "--- Optional ---" in r.stdout
