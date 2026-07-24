"""#193 - the review gate binds staged CONTENT (via review-gate-hash.sh), so
editing a reviewed file after the gate is written re-blocks the commit. Both
the writer (/code-review step 9) and the reader (pre-commit-review.sh) use
the one shared helper, so they cannot diverge.

Ported from tests/repo/review_gate_hash_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"
GATEHASH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "review_gate_hash.py"


@pytest.fixture
def work(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    return tmp_path


def _git(
    work: Path, hermetic_env: dict[str, str], *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(work), env=hermetic_env, capture_output=True, text=True
    )


def _commit_hook(
    work: Path, hermetic_env: dict[str, str]
) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=str(work),
        env=hermetic_env,
        input=payload,
        capture_output=True,
        text=True,
    )


def _write_gate(work: Path, hermetic_env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(GATEHASH)],
        cwd=str(work),
        env=hermetic_env,
        capture_output=True,
        text=True,
        check=True,
    )
    (work / ".review-passed").write_text(result.stdout)


def test_gate_exact_staged_content_that_was_reviewed_commits_cleanly(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 0
    assert not (work / ".review-passed").is_file()  # consumed on success


def test_gate_editing_a_reviewed_files_content_reblocks_the_commit(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)  # reviewed a.ts @ v1
    (work / "a.ts").write_text("v2-unreviewed\n")
    _git(work, hermetic_env, "add", "a.ts")  # same path, new content
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 2  # FIXED: blocked (was 0 under path-only hash)
    assert "BLOCKED" in result.stdout + result.stderr


def test_gate_staging_an_extra_unreviewed_file_reblocks_the_commit(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)
    (work / "b.ts").write_text("new\n")
    _git(work, hermetic_env, "add", "b.ts")
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 2


def test_gate_writer_and_hook_compute_the_same_content_hash(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("line1\nline2\n")
    _git(work, hermetic_env, "add", "a.ts")
    # the helper's output (writer) must equal the hash the hook recomputes
    # (reader)
    _write_gate(work, hermetic_env)
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 0
