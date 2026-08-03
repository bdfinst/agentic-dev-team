"""Unit tests for hooks/repo_review_nudge.py (#1739/#1743).

SessionStart hook that suggests running /repo-review when the percentage of
the codebase changed since the last recorded run (or since the repo's
first commit, if never run — which always resolves to exactly 100%) crosses
a threshold. Fail-open, never blocks a session.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "repo_review_nudge.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def _run(cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = hermetic_git_env(home=cwd)
    if extra_env:
        env.update(extra_env)
    payload = {"hook_event_name": "SessionStart", "cwd": str(cwd)}
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=hermetic_git_env(home=cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(cwd: Path) -> None:
    _git(cwd, "init", "-q")
    _git(cwd, "config", "user.email", "test@example.com")
    _git(cwd, "config", "user.name", "Test")


def _commit_lines(cwd: Path, filename: str, line_count: int, message: str) -> str:
    (cwd / filename).write_text("\n".join(f"line {i}" for i in range(line_count)) + "\n")
    _git(cwd, "add", filename)
    _git(cwd, "commit", "-q", "-m", message)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(cwd),
        env=hermetic_git_env(home=cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write_state(cwd: Path, last_commit: str) -> None:
    state_dir = cwd / ".claude" / "memory"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "repo-review-state.json").write_text(
        json.dumps({"last_commit": last_commit, "last_run_at": "2026-01-01T00:00:00Z"})
    )


def test_non_git_directory_is_silent(tmp_path: Path) -> None:
    r = _run(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


def test_no_payload_is_silent(tmp_path: Path) -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env=hermetic_git_env(home=tmp_path),
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""


def test_never_run_is_always_100_percent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 50, "first commit")
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "100.0%" in r.stdout
    assert "50" in r.stdout  # added and total are both 50 lines


def test_never_run_silent_when_threshold_exceeds_100(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 50, "first commit")
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "150"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_below_threshold_since_last_run_is_silent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 90, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 10, "small follow-up")
    # 10 added / 100 total = 10% — below a 50% threshold.
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "50"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_above_threshold_since_last_run_nudges(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 90, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 10, "small follow-up")
    # 10 added / 100 total = 10% — above a 5% threshold.
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "10.0%" in r.stdout


def test_unreachable_last_commit_falls_back_to_100_percent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 40, "first commit")
    _write_state(tmp_path, "0" * 40)  # syntactically valid shape, but unreachable
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "100.0%" in r.stdout


def test_invalid_last_commit_shape_treated_as_never_run(tmp_path: Path) -> None:
    """#1743: last_commit is untrusted input — a value that doesn't match
    the commit-sha shape (e.g. one a hostile state file could plant to try
    an argument-injection-flavored revspec) must never reach git at all,
    and must fall back to "no prior state" exactly like a missing file."""
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 40, "first commit")
    _write_state(tmp_path, "-not-a-real-sha")
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "100.0%" in r.stdout


def test_malformed_state_file_treated_as_never_run(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 40, "first commit")
    state_dir = tmp_path / ".claude" / "memory"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "repo-review-state.json").write_text("{not json")
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout


def test_default_threshold_used_when_env_var_invalid(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 1000, "large baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 5, "tiny follow-up")
    # 5 added / 1005 total =~ 0.5% — below the 1% default.
    r = _run(tmp_path, {"DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "not-a-number"})
    assert r.returncode == 0
    assert r.stdout == ""
