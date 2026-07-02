"""Pytest port of tests/scripts/git_origin_host_tests.bats (#613 / #572 Phase 3).

Mirrors the eight bats cases behind the same behavioral contract: classify the
``origin`` remote as ``github`` | ``other`` | ``none``. github.com + enterprise
GHE hosts (``.github.<label>``) → ``github``; substring lookalikes like
``notgithub.example.com`` or ``mygithub.com`` → ``other``; unparseable / absent
remote → ``none`` (fail-open — never blocks).

Both the .py module API (``classify(url)``) and the CLI entry point are
covered. The parity harness under ``plugins/dev-team/tests/hooks/parity/``
gates byte-equivalence between the .sh and .py in Phase 3 rollout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the script's dir is on the path so we can import it as a module.
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import git_origin_host  # type: ignore[import-not-found]  # noqa: E402


_SCRIPT_PY = _SCRIPT_DIR / "git_origin_host.py"


# ---------------------------------------------------------------------------
# classify() — the pure library function
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/o/r", "github"),
        ("git@github.com:o/r.git", "github"),
        ("ssh://git@github.com/o/r", "github"),
        ("https://github.example.com/o/r", "github"),
        ("git@github.mycorp.com:o/r.git", "github"),
        ("https://notgithub.example.com/o/r", "other"),
        ("git@mygithub.com:o/r.git", "other"),
        ("https://gitlab.com/o/r", "other"),
        ("", "none"),
    ],
)
def test_classify(url: str, expected: str) -> None:
    assert git_origin_host.classify(url) == expected


def test_classify_lowercases_host() -> None:
    """Enterprise GHE / GitHub.com may be typed in mixed case in configs."""
    assert git_origin_host.classify("https://GitHub.com/o/r") == "github"
    assert git_origin_host.classify("git@GITHUB.EXAMPLE.COM:o/r.git") == "github"


def test_classify_unparseable_falls_open() -> None:
    """A URL with no recognizable host structure returns ``other``, never crash."""
    # A bare word: no ://, no @, no : — becomes the host string itself.
    assert git_origin_host.classify("weirdstring") == "other"


# ---------------------------------------------------------------------------
# CLI — argv[1] override path + git-remote fallback
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


def test_cli_argv_override_github() -> None:
    r = _run_cli("https://github.com/o/r")
    assert r.returncode == 0
    assert r.stdout.strip() == "github"


def test_cli_argv_override_ssh_scp() -> None:
    r = _run_cli("git@github.com:o/r.git")
    assert r.returncode == 0
    assert r.stdout.strip() == "github"


def test_cli_argv_override_enterprise() -> None:
    r = _run_cli("https://github.example.com/o/r")
    assert r.returncode == 0
    assert r.stdout.strip() == "github"


def test_cli_argv_override_lookalike() -> None:
    r = _run_cli("https://notgithub.example.com/o/r")
    assert r.returncode == 0
    assert r.stdout.strip() == "other"


def test_cli_argv_override_non_github() -> None:
    r = _run_cli("https://gitlab.com/o/r")
    assert r.returncode == 0
    assert r.stdout.strip() == "other"


def test_cli_no_origin_is_none_fail_open(tmp_path: Path) -> None:
    """A repo with no origin remote is ``none`` (fail-open, never blocks)."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
        },
    )
    r = _run_cli(cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "none"


def test_cli_outside_git_repo_is_none(tmp_path: Path) -> None:
    """Fail-open outside any git repo — never blocks."""
    r = _run_cli(cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "none"
