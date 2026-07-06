"""src/-layout detection -> mypy `--explicit-package-bases` flag.

A plain `src/` layout (modules with no `__init__.py`, no project-level mypy
package-base config) makes mypy fail outright the moment any checked file
imports a `src/` module by its dotted `src.` path — `Source file found
twice under different module names: "calc" and "src.calc"`.
`mypy-src-layout.py` detects the layout and prints
`--explicit-package-bases` so the caller can splice it into the mypy
invocation; see `../references/tool-configs.md`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Hermetic env for the real-mypy subprocess calls below: a host-level
# MYPYPATH (or similar mypy env var) would change module resolution and
# make the "broken" repro non-deterministic — strip everything except what
# mypy needs to run (PATH to find its own interpreter, HOME for its cache).
_HERMETIC_MYPY_ENV = {
    key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ
}

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    PLUGIN_ROOT
    / "skills"
    / "static-analysis-integration"
    / "adapters"
    / "mypy-src-layout.py"
)


def run_script(*args: str, cwd: Path = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=30,
    )


def test_plain_src_layout_without_init_is_detected(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    result = run_script(str(tmp_path))

    assert result.returncode == 0
    assert result.stdout.strip() == "--explicit-package-bases"


def test_src_layout_with_init_py_is_not_detected(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    result = run_script(str(tmp_path))

    assert result.stdout.strip() == ""


def test_no_src_directory_is_not_detected(tmp_path):
    result = run_script(str(tmp_path))

    assert result.stdout.strip() == ""


def test_src_with_no_python_files_is_not_detected(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "data.json").write_text("{}")

    result = run_script(str(tmp_path))

    assert result.stdout.strip() == ""


@pytest.mark.parametrize(
    "config_name,config_text",
    [
        ("mypy.ini", "[mypy]\n"),
        (".mypy.ini", "[mypy]\n"),
        ("setup.cfg", "[mypy]\nmypy_path = src\n"),
        ("tox.ini", "[mypy]\nmypy_path = src\n"),
        ("pyproject.toml", '[tool.mypy]\nmypy_path = "src"\n'),
    ],
)
def test_existing_package_base_config_short_circuits_detection(
    tmp_path, config_name, config_text
):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / config_name).write_text(config_text)

    result = run_script(str(tmp_path))

    assert result.stdout.strip() == ""


@pytest.mark.parametrize(
    "config_name,config_text",
    [
        ("setup.cfg", "[bdist_wheel]\nuniversal = 1\n"),
        ("tox.ini", "[tox]\nenvlist = py311\n"),
        ("pyproject.toml", "[tool.black]\nline-length = 100\n"),
    ],
)
def test_unrelated_config_section_does_not_short_circuit_detection(
    tmp_path, config_name, config_text
):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / config_name).write_text(config_text)

    result = run_script(str(tmp_path))

    assert result.stdout.strip() == "--explicit-package-bases"


def test_defaults_to_current_directory_when_no_argument_given(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    result = run_script(cwd=tmp_path)

    assert result.stdout.strip() == "--explicit-package-bases"


@pytest.mark.skipif(shutil.which("mypy") is None, reason="mypy not installed")
def test_src_layout_reproduces_and_the_detected_flag_fixes_source_file_found_twice(
    tmp_path,
):
    """End-to-end reproduction of the src/-layout mypy failure: a module
    with no __init__.py, referenced from another checked file by its
    dotted `src.` path, reproduces the false module-name collision this
    detector exists to resolve — and the detected flag resolves it."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
    (tmp_path / "main.py").write_text("from src.calc import add\n\nprint(add(1, 2))\n")

    broken = subprocess.run(
        ["mypy", "--output", "json", "."],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=_HERMETIC_MYPY_ENV,
        timeout=60,
    )
    assert "Source file found twice under different module names" in (
        broken.stdout + broken.stderr
    )

    detect = run_script(str(tmp_path))
    extra_args = detect.stdout.split()
    assert extra_args == ["--explicit-package-bases"]

    fixed = subprocess.run(
        ["mypy", *extra_args, "--output", "json", "."],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=_HERMETIC_MYPY_ENV,
        timeout=60,
    )
    assert "Source file found twice under different module names" not in (
        fixed.stdout + fixed.stderr
    )
    assert fixed.returncode == 0
