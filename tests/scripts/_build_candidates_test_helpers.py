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

import os
import shlex
import subprocess
import sys
import tempfile
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
    `timeout` seconds."""
    argv = [sys.executable, *python_flags, str(script), *args]
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=hermetic_env() if env is None else env,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"timed out after {timeout}s: {argv}")


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
