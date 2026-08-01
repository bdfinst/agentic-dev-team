"""Shared constants for tests/scripts/test_mutation_*.py.

Named with a leading underscore (not ``conftest``) to avoid ambiguity with
pytest's own conftest.py fixture-collection mechanism — this is a plain
importable module, not a pytest plugin. Follows this repo's existing
convention for cross-directory test helpers (``tests/agents/_plugin_dirs.py``,
``tests/stack_aware/_stack_aware_helpers.py``, ``_repo_root.py`` at the repo root).

``SCRIPTS_DIR`` resolves the mutation-testing skill's scripts directory so
each test module can put it on ``sys.path`` before importing the module
under test. ``FORBIDDEN_LITERALS`` is the shared list of repo-specific
literals (ACI project/tooling names) those modules must never leak into
their source — mirrors the list originally defined in
``test_mutation_kill_loop.py`` (issue #1554).

``hermetic_git_env``/``git_hermetic`` scrub the git-hook-exported env vars
(issue #546) for the handful of tests here that shell out to a REAL git repo
(no mocks) — see ``test_check_python_only.py``'s ``_hermetic_env``/``_git``
for the original pattern this mirrors. Without this, a test's own ``git
init``/``git commit`` can inherit GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/
GIT_PREFIX/GIT_REFLOG_ACTION from the parent process (e.g. this repo's own
pre-push git hook) and silently target/corrupt the real parent repo's refs
instead of the test's own tmp_path (#1598/#1584 review, item 4).

Scrubbing the test's OWN setup calls (``git_hermetic``) is necessary but not
sufficient: the production function under test shells out to git too, and
if that call doesn't also receive a scrubbed env, only half the test is
hermetic (#1598/#1584 review, round 3 — caught by test-smell-review/
ai-provenance-review after round 2's fix wired the scrub into setup calls
only). Pass ``hermetic_git_env(home=tmp_path)`` as the SUT's own ``env=``
argument too, not just to ``git_hermetic``'s scaffolding calls.
``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM`` point at ``/dev/null`` so no
global/system gitconfig leaks in, and an optional ``home=`` overrides
``HOME`` for the same reason.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]

_GIT_SCRUB_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def hermetic_git_env(home: Path | str | None = None) -> dict:
    """A minimal, scrubbed environment for real ``git`` subprocess calls.

    Pass this same dict as the production code's own ``env=`` argument (not
    just to the test's setup calls) — the code under test shells out to git
    too, and only scrubbing the test's own scaffolding leaves the assertion
    itself running against the ambient environment (#1598/#1584 review,
    round 3: test-smell-review/ai-provenance-review). ``home`` overrides
    ``HOME`` so a stray ``~/.gitconfig`` can't leak in either, matching
    ``tests/repo/conftest.py``'s ``hermetic_env`` fixture.
    """
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB_ENV_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    if home is not None:
        env["HOME"] = str(home)
    return env


def git_hermetic(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a real ``git`` subprocess with a hermetic, scrubbed environment."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=hermetic_git_env(home=cwd),
        check=True,
    )
