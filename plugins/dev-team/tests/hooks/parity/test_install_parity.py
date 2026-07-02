"""Parity check for install.sh trampoline → install.py (#616 / #572 Phase 3).

Unlike the other slices where a `.py` replaces a `.sh` outright, `install.sh`
stays as a thin trampoline per ADR 0014's "shell-detection prelude" rule.
The parity contract for this file is therefore:

    running `install.sh` produces byte-identical stdout/stderr/exit code
    to running `install.py` directly (given the same PATH / env).

That verifies the trampoline forwards correctly rather than shadowing the
Python entry point with old bash logic.

Fixtures parametrize over PATH shims that toggle which prerequisites are
"present", so both sides land on the same [ok] / [FAIL] / [warn] lines.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_INSTALL_PY = _REPO_ROOT / "plugins" / "dev-team" / "install.py"
_INSTALL_SH = _REPO_ROOT / "plugins" / "dev-team" / "install.sh"


def _make_shim(shim: Path, cmds: List[str]) -> None:
    shim.mkdir(exist_ok=True)
    for cmd in cmds:
        p = shim / cmd
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)


def _stitch_path(shim: Path, extra_bins: List[str]) -> str:
    """Return a PATH that has the shim first, plus the directories that
    contain the given extra binaries (bash, python3). Nothing else."""
    parts = [str(shim)]
    for name in extra_bins:
        w = shutil.which(name)
        if w:
            parts.append(os.path.dirname(w))
    return ":".join(parts)


CASES: List[Tuple[str, List[str], List[str]]] = [
    # name, required-present, optional-present
    ("all_present", ["claude", "jq", "gh"], ["semgrep", "hadolint", "trivy", "grype"]),
    ("only_required", ["claude", "jq", "gh"], []),
    ("missing_claude", ["jq", "gh"], []),
    ("missing_jq", ["claude", "gh"], []),
    ("mixed_optional", ["claude", "jq", "gh"], ["semgrep"]),
]


@pytest.mark.skipif(
    not _INSTALL_PY.is_file() or not _INSTALL_SH.is_file(),
    reason="both .sh trampoline and .py implementation required",
)
@pytest.mark.parametrize(
    "name, required, optional",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_parity(
    tmp_path: Path, name: str, required: List[str], optional: List[str]
) -> None:
    shim = tmp_path / "shim"
    _make_shim(shim, required + optional)

    # Sh needs bash + python3 to delegate; py needs just python3.
    sh_path = _stitch_path(shim, ["bash", "python3"])
    py_path = _stitch_path(shim, ["python3"])

    sh_env = {"PATH": sh_path, "HOME": "/tmp", "LANG": "C.UTF-8"}
    py_env = {"PATH": py_path, "HOME": "/tmp", "LANG": "C.UTF-8"}

    bash_bin = shutil.which("bash") or "bash"
    sh_result = subprocess.run(
        [bash_bin, str(_INSTALL_SH)],
        capture_output=True,
        text=True,
        check=False,
        env=sh_env,
    )
    py_result = subprocess.run(
        [sys.executable, str(_INSTALL_PY)],
        capture_output=True,
        text=True,
        check=False,
        env=py_env,
    )

    assert sh_result.returncode == py_result.returncode, (
        f"[{name}] exit code diverged: sh={sh_result.returncode} "
        f"py={py_result.returncode}\n"
        f"sh stdout: {sh_result.stdout!r}\n"
        f"py stdout: {py_result.stdout!r}"
    )
    assert sh_result.stdout == py_result.stdout, (
        f"[{name}] stdout diverged\nsh: {sh_result.stdout!r}\npy: {py_result.stdout!r}"
    )
    assert sh_result.stderr == py_result.stderr, f"[{name}] stderr diverged"


@pytest.mark.skipif(
    not _INSTALL_SH.is_file(),
    reason="install.sh trampoline required",
)
def test_trampoline_windows_missing_python(tmp_path: Path) -> None:
    """Windows-path scenario: on a machine where Git Bash is present but
    python3 is not on PATH, the trampoline exits 1 with an actionable
    pointer. This is the platform this migration exists to protect."""
    shim = tmp_path / "shim"
    shim.mkdir()
    bash_bin = shutil.which("bash") or "bash"
    # Ensure bash is available in the shim (subprocess needs to find it).
    os.symlink(bash_bin, shim / "bash")
    r = subprocess.run(
        [bash_bin, str(_INSTALL_SH)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": str(shim), "HOME": "/tmp"},
    )
    assert r.returncode == 1
    assert "python3" in r.stdout
    assert "required" in r.stdout
