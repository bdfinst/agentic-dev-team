"""Shared helpers for tests/scripts/test_build_candidates*.py.

Named with a leading underscore (not ``conftest``) like the other cross-file
helpers in this directory: a plain importable module, not a pytest plugin.

Every subprocess here runs under a hermetic git environment: inherited
``GIT_*`` variables (a git hook exports ``GIT_DIR`` and friends) are dropped,
global and system config are ignored, discovery cannot climb out of the
system temp directory, and the author and committer identity comes from the
environment, so no test writes per-repository config.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
SCRIPT_PY = SCRIPTS_DIR / "build_candidates.py"

#: Scenario count `make_candidate` gives every candidate unless a test says
#: otherwise.
SCENARIOS_TOTAL = 5

CLI_TIMEOUT_SECONDS = 60
_KILL_DRAIN_SECONDS = 5

_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def hermetic_env() -> dict[str, str]:
    """The environment for every subprocess a test starts."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_IDENTITY)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CEILING_DIRECTORIES"] = str(Path(tempfile.gettempdir()).resolve())
    return env


def apply_hermetic_env(monkeypatch) -> None:
    """Give the test process itself the hermetic git environment, for tests
    that call the production git wrappers in-process (they inherit
    os.environ rather than going through `run_cli`/`git_output`)."""
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key, raising=False)
    for key, value in hermetic_env().items():
        if key.startswith("GIT_"):
            monkeypatch.setenv(key, value)


def run_script(
    script: Path,
    *args: str,
    python_flags: Sequence[str] = (),
    timeout: int = CLI_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
):
    """Run `script` with `args` under this interpreter (`python_flags` go
    before the script path), in the hermetic environment unless `env` is
    given; fail the test, naming the argv, when it does not finish within
    `timeout` seconds. The script runs as a session leader; on a timeout its
    whole process group is killed first, so no descendant outlives the test."""
    argv = [sys.executable, *python_flags, str(script), *args]
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=hermetic_env() if env is None else env,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            pytest.fail(f"timed out after {timeout}s: {argv}")
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _kill_process_tree(process: subprocess.Popen) -> None:
    """SIGKILL the process group of `process` (POSIX), else the process, then
    drain its pipes for a bounded time."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows has no process groups
            process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.communicate(timeout=_KILL_DRAIN_SECONDS)


def process_is_gone(pid: int) -> bool:
    """True when `pid` no longer runs. A zombie still answers signal 0 until
    its parent reaps it, so where /proc exists its state is read too."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat_file:
            return stat_file.read().rpartition(") ")[2][:1] == "Z"
    except FileNotFoundError:
        # Gone between the two calls, unless this platform has no /proc.
        return os.path.isdir("/proc")
    except OSError:
        return False


def wait_until_gone(pid: int, seconds: float = 2.0) -> bool:
    """Poll for up to `seconds` until `pid` is gone; return whether it is."""
    deadline = time.monotonic() + seconds
    while not process_is_gone(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return process_is_gone(pid)


def run_cli(*args: str, timeout: int = CLI_TIMEOUT_SECONDS):
    """Run build_candidates.py with `args` (see `run_script`)."""
    return run_script(SCRIPT_PY, *args, timeout=timeout)


def git_output(repo, *args: str, stdin: str | None = None) -> str:
    """Stripped stdout of `git -C <repo> <args>`, feeding `stdin` when given;
    raises CalledProcessError on a non-zero exit."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
        env=hermetic_env(),
        timeout=CLI_TIMEOUT_SECONDS,
    ).stdout.strip()


def init_repo(path: Path, branch: str = "main") -> None:
    """Create an empty repository at `path` on `branch`, without templates."""
    path.mkdir()
    git_output(path, "init", "-q", "--template=", "-b", branch)


def commit_all(repo, message: str) -> None:
    git_output(repo, "add", "-A")
    git_output(repo, "commit", "-q", "-m", message)


def make_candidate(candidate_id: int, met: int = SCENARIOS_TOTAL, **overrides) -> dict:
    """A green, finding-free candidate dict with `met` of SCENARIOS_TOTAL
    scenarios met; `overrides` replace any field."""
    candidate = {
        "id": candidate_id,
        "branch": f"worktree-c{candidate_id}",
        "suite_green": True,
        "scenarios_total": SCENARIOS_TOTAL,
        "scenarios_unmet": SCENARIOS_TOTAL - met,
        "errors": 0,
        "warnings": 0,
        "diff_lines": 10,
        "cost_usd": 0.5,
        "screening": "ok",
    }
    candidate.update(overrides)
    return candidate


def python_command(code: str) -> str:
    """A shell-safe `--test-cmd` that runs `code` under this interpreter."""
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"
