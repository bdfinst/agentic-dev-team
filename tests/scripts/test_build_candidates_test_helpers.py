"""Tests for the shared `run_script` helper in _build_candidates_test_helpers.py."""

from __future__ import annotations

import os

import pytest
from _build_candidates_test_helpers import run_script, wait_until_gone

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


SPAWN_SLEEPING_CHILD = """\
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
time.sleep(300)
"""


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_run_script_kills_a_child_the_script_left_running_when_it_times_out(
    tmp_path,
) -> None:
    script = _script(tmp_path, SPAWN_SLEEPING_CHILD)
    pid_file = tmp_path / "child.pid"
    with pytest.raises(pytest.fail.Exception, match="timed out after 3s"):
        run_script(script, str(pid_file), timeout=3)
    child = int(pid_file.read_text(encoding="utf-8"))
    assert wait_until_gone(child), f"child {child} outlived the timed-out script"


def test_run_script_returns_the_exit_code_and_both_streams(tmp_path) -> None:
    script = _script(
        tmp_path,
        "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
    )
    r = run_script(script)
    assert (r.returncode, r.stdout.strip(), r.stderr.strip()) == (3, "out", "err")
