"""Tests for the shared `run_script` helper in _build_candidates_test_helpers.py."""

from __future__ import annotations

import os

import pytest
from _build_candidates_test_helpers import run_script

ISOLATED_FLAG_SCRIPT = "import sys; print(sys.flags.isolated)"


def _script(tmp_path, body: str):
    path = tmp_path / "probe.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_run_script_puts_python_flags_before_the_script(tmp_path) -> None:
    script = _script(tmp_path, ISOLATED_FLAG_SCRIPT)
    r = run_script(script, python_flags=("-I",))
    assert r.stdout.strip() == "1"


def test_run_script_passes_the_arguments_to_the_script(tmp_path) -> None:
    script = _script(tmp_path, "import sys; print(*sys.argv[1:])")
    assert run_script(script, "a", "b").stdout.split() == ["a", "b"]


def test_run_script_runs_in_the_hermetic_git_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    script = _script(tmp_path, "import os; print(os.environ.get('GIT_DIR', 'unset'))")
    assert run_script(script).stdout.strip() == "unset"


def test_run_script_uses_the_given_environment_instead(tmp_path) -> None:
    script = _script(tmp_path, "import os; print(os.environ.get('PROBE', 'unset'))")
    env = {**os.environ, "PROBE": "given"}
    assert run_script(script, env=env).stdout.strip() == "given"


def test_run_script_fails_the_test_naming_the_argv_on_timeout(tmp_path) -> None:
    script = _script(tmp_path, "import time; time.sleep(60)")
    with pytest.raises(pytest.fail.Exception, match=r"timed out after 1s.*probe\.py"):
        run_script(script, timeout=1)
