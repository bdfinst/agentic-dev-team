"""Tests for scripts/check-python-only.py — the repo-wide, allowlisted,
blocking-by-default gate on newly-added ``.sh``/``.bats`` files (ADR 0014,
issue #702).

Hermetic per #546: git exports GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/
GIT_PREFIX/GIT_REFLOG_ACTION into a pre-push hook's environment, and nothing
in the hook chain scrubs them. A fixture that runs `git init` / `git commit`
inherits those and can silently rewrite refs on the parent repo. Every
subprocess here scrubs the git env and operates inside a per-test tmp_path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "check-python-only.py"

GIT_SCRUB_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def _hermetic_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in GIT_SCRUB_ENV_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
        check=False,
    )


def _run_script(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one seed commit on its only branch."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "README.md").write_text("seed\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "chore: seed repo")
    return tmp_path


def _add_and_commit(repo: Path, relpath: str, contents: str = "#!/bin/sh\n") -> str:
    """Add a new file (staged, then committed) and return the seed commit
    SHA to diff against (i.e. the ref *before* this commit)."""
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"feat: add {relpath}")
    return base_sha


# --- blocked: new file outside the allowlist --------------------------------


def test_new_sh_under_repo_root_scripts_is_blocked(repo: Path) -> None:
    base = _add_and_commit(repo, "scripts/new-thing.sh")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 1, result.stderr
    assert "scripts/new-thing.sh" in result.stderr
    assert "BLOCKING" in result.stderr


def test_new_sh_under_plugins_dev_team_is_blocked(repo: Path) -> None:
    base = _add_and_commit(repo, "plugins/dev-team/hooks/new-hook.sh")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 1, result.stderr
    assert "plugins/dev-team/hooks/new-hook.sh" in result.stderr


def test_new_bats_under_plugins_dev_team_is_blocked(repo: Path) -> None:
    base = _add_and_commit(repo, "plugins/dev-team/tests/new_thing.bats")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 1, result.stderr
    assert "plugins/dev-team/tests/new_thing.bats" in result.stderr


# --- passes: new file inside an allowlisted path -----------------------------


def test_new_sh_under_security_assessment_plugin_passes(repo: Path) -> None:
    base = _add_and_commit(repo, "plugins/security-assessment/scripts/new-thing.sh")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 0, result.stderr


def test_new_bats_under_allowlisted_dir_passes(repo: Path) -> None:
    base = _add_and_commit(repo, "tests/security-assessment/scripts/new_thing.bats")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 0, result.stderr


def test_new_sh_under_evals_passes(repo: Path) -> None:
    base = _add_and_commit(repo, "evals/codebase-recon/fixtures/deploy.sh")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 0, result.stderr


def test_new_exact_allowlisted_file_passes(repo: Path) -> None:
    base = _add_and_commit(repo, ".claude/cloud-setup.sh")
    result = _run_script(repo, "--base", base)
    assert result.returncode == 0, result.stderr


# --- unaffected: editing an existing file (diff-filter=A semantics) --------


def test_editing_an_existing_bats_file_is_unaffected(repo: Path) -> None:
    # Seed an existing .bats file on the base commit itself, then edit
    # (not add) it on a follow-up commit — --diff-filter=A must not flag it.
    existing = repo / "tests" / "skills" / "existing_thing.bats"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("#!/usr/bin/env bats\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: seed existing bats file")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    existing.write_text("#!/usr/bin/env bats\n# edited\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "test: edit existing bats file")

    result = _run_script(repo, "--base", base)
    assert result.returncode == 0, result.stderr


# --- --advisory opt-out -----------------------------------------------------


def test_advisory_flag_warns_but_does_not_fail(repo: Path) -> None:
    base = _add_and_commit(repo, "scripts/new-thing.sh")
    result = _run_script(repo, "--base", base, "--advisory")
    assert result.returncode == 0, result.stderr
    assert "ADVISORY" in result.stderr
    assert "scripts/new-thing.sh" in result.stderr


# --- --list reflects the generalized allowlist shape ------------------------


def test_list_reflects_generalized_allowlist_shape(repo: Path) -> None:
    result = _run_script(repo, "--list")
    assert result.returncode == 0, result.stderr
    assert "exact paths" in result.stdout
    assert "directory prefixes" in result.stdout
    assert "plugins/dev-team/install.sh" in result.stdout
    assert "plugins/security-assessment/" in result.stdout
    assert "evals/" in result.stdout
