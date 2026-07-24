"""Behavioral tests for hooks/py.sh (#1078).

py.sh is a POSIX bootstrap shim (it runs before Python is guaranteed on PATH,
so it cannot itself be Python). Driven here via subprocess with a controlled
PATH of fake interpreters so we can assert: it resolves python3, falls back to
py -3 / python, rejects the Windows Store stub and Python 2, honors
$DEV_TEAM_PYTHON, and exits 2 with a message when nothing works.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

PY_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "py.sh"

# A real interpreter the fakes delegate to when running an actual script.
_REAL_PY = sys.executable

# Absolute path to sh — the sandbox sets PATH to only the fake bindir, so the
# subprocess launcher can't rely on PATH to locate the shell itself.
_SH = shutil.which("sh") or "/bin/sh"


def _write(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _fake_valid(path: Path, name: str, *, launcher_flag: str | None = None) -> None:
    """A fake python-3 interpreter.

    For the version probe (`-c ...`) it reports success (exit 0). For anything
    else it records its own name to $MARKER then delegates to the real Python so
    the target script actually runs. ``launcher_flag`` emulates the Windows `py`
    launcher, whose real first argument is a version selector like ``-3``.
    """
    shift = 'shift\n' if launcher_flag else ""
    _write(
        path,
        f"""#!/bin/sh
{shift}if [ "$1" = "-c" ]; then exit 0; fi
printf '{name}\\n' >> "$MARKER"
exec "{_REAL_PY}" "$@"
""",
    )


def _fake_py2(path: Path) -> None:
    """A Python-2-like interpreter: the probe reports major < 3 (exit 1)."""
    _write(
        path,
        f"""#!/bin/sh
if [ "$1" = "-c" ]; then exit 1; fi
exec "{_REAL_PY}" "$@"
""",
    )


def _fake_stub(path: Path) -> None:
    """The WindowsApps app-execution-alias stub: refuses to run, exit non-zero."""
    _write(
        path,
        """#!/bin/sh
echo "Python was not found; run without arguments to install from the Microsoft Store" >&2
exit 9009
""",
    )


@pytest.fixture()
def sandbox(tmp_path):
    """A private bin dir on an isolated PATH, an isolated cache, and a target
    script that prints a sentinel. Returns (env, run)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "marker"
    target = tmp_path / "target.py"
    target.write_text("print('SENTINEL')\n")

    env = dict(os.environ)
    env["PATH"] = str(bindir)  # only our fakes are resolvable
    env["MARKER"] = str(marker)
    env["DEV_TEAM_PY_CACHE"] = str(tmp_path / "cache")
    env.pop("DEV_TEAM_PYTHON", None)

    def run():
        return subprocess.run(
            [_SH, str(PY_SH), str(target)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    return bindir, marker, env, run


def test_prefers_python3(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_valid(bindir / "python3", "python3")
    _fake_valid(bindir / "python", "python")  # present but should not win
    r = run()
    assert r.returncode == 0
    assert "SENTINEL" in r.stdout
    assert marker.read_text().strip() == "python3"


def test_falls_back_to_python_when_no_python3(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_valid(bindir / "python", "python")
    r = run()
    assert r.returncode == 0
    assert "SENTINEL" in r.stdout
    assert marker.read_text().strip() == "python"


def test_falls_back_to_py_launcher(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_valid(bindir / "py", "py", launcher_flag="-3")
    r = run()
    assert r.returncode == 0
    assert "SENTINEL" in r.stdout
    assert marker.read_text().strip() == "py"


def test_rejects_windows_store_stub(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_stub(bindir / "python3")  # the stub masquerades as python3
    _fake_valid(bindir / "python", "python")
    r = run()
    assert r.returncode == 0
    assert "SENTINEL" in r.stdout
    assert marker.read_text().strip() == "python"  # stub skipped, python won


def test_rejects_python2(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_py2(bindir / "python3")  # a py2 masquerading as python3
    _fake_valid(bindir / "python", "python")
    r = run()
    assert r.returncode == 0
    assert marker.read_text().strip() == "python"


def test_exit_2_when_nothing_valid(sandbox):
    bindir, _marker, _env, run = sandbox
    _fake_stub(bindir / "python3")  # only a stub, nothing else
    r = run()
    assert r.returncode == 2
    assert "no Python 3 interpreter found" in r.stderr


def test_dev_team_python_override_wins(sandbox):
    bindir, marker, env, run = sandbox
    _fake_valid(bindir / "python3", "python3")
    _fake_valid(bindir / "custompy", "custompy")
    env["DEV_TEAM_PYTHON"] = "custompy"
    r = run()
    assert r.returncode == 0
    assert marker.read_text().strip() == "custompy"


def test_cache_short_circuits_second_call(sandbox):
    bindir, marker, _env, run = sandbox
    _fake_valid(bindir / "python", "python")
    assert run().returncode == 0
    # Cache now records `python`. A second call must reuse it without re-probing
    # (the marker gains a second line from the cached exec).
    assert run().returncode == 0
    assert marker.read_text().split() == ["python", "python"]


def test_resolves_with_real_interpreter_no_path_override():
    """Smoke test against the actual environment (real python3 present)."""
    if shutil.which("python3") is None and shutil.which("python") is None:
        pytest.skip("no Python on PATH to smoke-test against")
    r = subprocess.run(
        [_SH, str(PY_SH), "-c", "print('OK')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "OK" in r.stdout
