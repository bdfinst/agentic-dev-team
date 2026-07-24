"""Tests for root .gitignore - the per-user model ladder and the routing bump
log must be ignored so corporate config and per-user metrics never leak into
version control. The retired model-overrides.json no longer needs an entry.

Ported from tests/repo/gitignore_overrides.bats (#673).
"""

from __future__ import annotations

import subprocess

import pytest

from _repo_root import REPO_ROOT


@pytest.mark.parametrize(
    "path",
    [
        ".claude/model-ladder.json",
        ".claude/session-model",
        ".claude/metrics/model-routing.log",
    ],
)
def test_path_is_gitignored(path: str) -> None:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{path} is not gitignored: {result.stdout}{result.stderr}"
    )
