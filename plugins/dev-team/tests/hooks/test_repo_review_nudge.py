"""Unit tests for hooks/repo_review_nudge.py (#1739/#1743/#1746).

SessionStart hook that suggests running /repo-review once its three-part
trigger fires: an absolute ceiling (always nudge above it, regardless of
percentage), an absolute floor (never nudge below it, regardless of
percentage), and a percentage-of-codebase-changed rule in between. "Never
run" always resolves to exactly 100% changed. Fail-open, never blocks a
session.
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

# Disables the floor/ceiling guards (0 = no minimum, a huge number = an
# unreachable maximum in these tiny fixture repos) so tests that exist to
# pin the *percentage* rule aren't coupled to the floor/ceiling defaults —
# those get their own dedicated tests below.
_PERCENT_ONLY_ENV = {
    "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "0",
    "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "999999",
}


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
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "100.0%" in r.stdout
    assert "50" in r.stdout  # added and total are both 50 lines


def test_never_run_silent_when_threshold_exceeds_100(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 50, "first commit")
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "150"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_below_threshold_since_last_run_is_silent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 90, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 10, "small follow-up")
    # 10 added / 100 total = 10% — below a 50% threshold.
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "50"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_above_threshold_since_last_run_nudges(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 90, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 10, "small follow-up")
    # 10 added / 100 total = 10% — above a 5% threshold.
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "10.0%" in r.stdout


def test_unreachable_last_commit_falls_back_to_100_percent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 40, "first commit")
    _write_state(tmp_path, "0" * 40)  # syntactically valid shape, but unreachable
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
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
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "100.0%" in r.stdout


def test_malformed_state_file_treated_as_never_run(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_lines(tmp_path, "a.txt", 40, "first commit")
    state_dir = tmp_path / ".claude" / "memory"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "repo-review-state.json").write_text("{not json")
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5"})
    assert r.returncode == 0
    assert "/repo-review" in r.stdout


def test_default_percent_threshold_used_when_env_var_invalid(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 1000, "large baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 5, "tiny follow-up")
    # 5 added / 1005 total =~ 0.5% — below the 10% default.
    r = _run(tmp_path, {**_PERCENT_ONLY_ENV, "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "not-a-number"})
    assert r.returncode == 0
    assert r.stdout == ""


# --- Floor (#1746): suppress nagging on small repos -------------------------


def test_floor_suppresses_nudge_even_above_percent_threshold(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 40, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 10, "trivial follow-up")
    # 10 added / 50 total = 20% — well above a 5% threshold, but 10 added
    # lines is below a 50-line floor: must stay silent regardless.
    r = _run(
        tmp_path,
        {
            "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5",
            "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "50",
            "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "999999",
        },
    )
    assert r.returncode == 0
    assert r.stdout == ""


def test_floor_allows_nudge_once_added_meets_it(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 40, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 60, "substantial follow-up")
    # 60 added / 100 total = 60% — above both a 5% threshold and a 50-line floor.
    r = _run(
        tmp_path,
        {
            "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5",
            "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "50",
            "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "999999",
        },
    )
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
    assert "60.0%" in r.stdout


def test_invalid_min_added_lines_falls_back_to_default_floor(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 40, "baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 50, "follow-up under the real 200-line default floor")
    # 50 added / 90 total =~ 55.6% — comfortably above a 5% threshold, but
    # 50 added lines is below the real default floor (200): an invalid
    # override must fall back to that default, not disable the floor.
    r = _run(
        tmp_path,
        {
            "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "5",
            "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "not-a-number",
            "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "999999",
        },
    )
    assert r.returncode == 0
    assert r.stdout == ""


# --- Ceiling (#1746): don't go silent on large repos ------------------------


def test_ceiling_forces_nudge_even_below_percent_threshold(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    last = _commit_lines(tmp_path, "a.txt", 2000, "large baseline")
    _write_state(tmp_path, last)
    _commit_lines(tmp_path, "b.txt", 60, "follow-up")
    # 60 added / 2060 total =~ 2.9% — below a 10% threshold, but 60 added
    # lines is above a 50-line ceiling: must nudge regardless.
    r = _run(
        tmp_path,
        {
            "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "10",
            "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "0",
            "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "50",
        },
    )
    assert r.returncode == 0
    assert "/repo-review" in r.stdout


def test_default_ceiling_forces_nudge_despite_unreachable_percent_threshold(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    # Never run => 100%, but an absurdly high percent threshold means the
    # percent rule alone could never fire. The real default ceiling (5000)
    # must still force a nudge on its own.
    _commit_lines(tmp_path, "a.txt", 5001, "very large first commit")
    r = _run(
        tmp_path,
        {
            "DEV_TEAM_REPO_REVIEW_PERCENT_THRESHOLD": "99999",
            "DEV_TEAM_REPO_REVIEW_MIN_ADDED_LINES": "0",
            "DEV_TEAM_REPO_REVIEW_MAX_ADDED_LINES": "not-a-number",
        },
    )
    assert r.returncode == 0
    assert "/repo-review" in r.stdout
