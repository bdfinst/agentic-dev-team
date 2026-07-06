"""BugsJS adapter for the /code-review benchmark harness (#821).

Verified this session against real fetches: `Projects.csv` is
semicolon-delimited `Name;Repository url;Number of bugs`; a project's
`<Project>_bugs.csv` (also semicolon-delimited) carries only test/coverage
counts and a bug-category taxonomy — no commit hash or description. Per
`myGit.py`, the buggy revision is the parent of the `Bug-<id>` git tag
(`tags/Bug-<id>^`); the fix commit is the `Bug-<id>` tag itself. Ground truth
is `git diff tags/Bug-<id>^ tags/Bug-<id>` inside the checked-out project
repo, filtered to drop test/spec files — the issue's explicit instruction:
"use only the fix commit's changed lines as ground truth, not the test
changes" (the `Bug-<id>` tag's commit bundles the fix with its new tests).

Never raises on a missing bug-dataset checkout or an unparsable project;
callers (the runner) treat a `None`/empty return as "skip and log."
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, List, Optional

from .common import BenchmarkCase, Hunk, run_with_timeout, unified_diff_hunks

DEFAULT_RUN_FN = run_with_timeout

_TEST_PATH_MARKERS = ("test/", "spec/", "__tests__/", ".test.js", ".spec.js")


def detect(bugsjs_home: Optional[str]) -> bool:
    """True when `bugsjs_home` looks like a real BugsJS/bug-dataset checkout."""
    if not bugsjs_home:
        return False
    home = Path(bugsjs_home)
    return (home / "main.py").is_file() and (home / "Projects.csv").is_file()


def _read_repo_url(bugsjs_home: str, project: str) -> Optional[str]:
    projects_csv = Path(bugsjs_home) / "Projects.csv"
    if not projects_csv.is_file():
        return None
    with open(projects_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            if row.get("Name", "").strip().lower() == project.strip().lower():
                return row.get("Repository url")
    return None


def _bugs_csv(bugsjs_home: str, project: str) -> Path:
    return Path(bugsjs_home) / "Projects" / project / f"{project}_bugs.csv"


def list_projects(bugsjs_home: str) -> List[str]:
    """Every project name listed in `Projects.csv`."""
    projects_csv = Path(bugsjs_home) / "Projects.csv"
    if not projects_csv.is_file():
        return []
    with open(projects_csv, newline="", encoding="utf-8") as fh:
        return [
            row["Name"].strip()
            for row in csv.DictReader(fh, delimiter=";")
            if row.get("Name", "").strip()
        ]


def list_bugs(project: str, bugsjs_home: str) -> List[BenchmarkCase]:
    """Parse `<Project>_bugs.csv` bug ids into BenchmarkCases.

    Ground truth hunks are populated separately by `ground_truth()` once the
    project repo is cloned (the fix diff isn't available from the CSV
    metadata alone — it requires the actual git history).
    """
    csv_path = _bugs_csv(bugsjs_home, project)
    if not csv_path.is_file():
        return []
    repo_url = _read_repo_url(bugsjs_home, project)

    cases: List[BenchmarkCase] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            bug_id = row.get("ID")
            if not bug_id:
                continue
            cases.append(
                BenchmarkCase(
                    dataset="bugsjs",
                    project=project,
                    bug_id=bug_id,
                    language="javascript",
                    ground_truth_files=[],
                    ground_truth_hunks=[],
                    description=row.get("Bug category"),
                    extra={"repo_url": repo_url},
                )
            )
    return cases


def checkout(
    case: BenchmarkCase,
    workdir: str,
    bugsjs_home: Optional[str] = None,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 600,
) -> bool:
    """Clone the project's repo and check out `tags/Bug-<id>^` (the buggy revision).

    Returns True only if both the clone and checkout succeed.
    """
    repo_url = (case.extra or {}).get("repo_url")
    if not repo_url:
        return False
    try:
        clone = run_fn(
            timeout,
            ["git", "clone", repo_url, workdir],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            return False
        checkout_proc = run_fn(
            timeout,
            ["git", "checkout", f"tags/Bug-{case.bug_id}^"],
            cwd=workdir,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return False
    return checkout_proc.returncode == 0


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _TEST_PATH_MARKERS)


def ground_truth(
    case: BenchmarkCase,
    cloned_repo_dir: str,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 60,
) -> List[Hunk]:
    """`git diff tags/Bug-<id>^ tags/Bug-<id>` inside the clone, source files only.

    Returns `[]` (not `None`) on any git failure — an empty ground truth is
    the runner's signal to skip the case, same as a missing patch for
    Defects4J.
    """
    try:
        proc = run_fn(
            timeout,
            ["git", "diff", f"tags/Bug-{case.bug_id}^", f"tags/Bug-{case.bug_id}"],
            cwd=cloned_repo_dir,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return []
    if proc.returncode != 0:
        return []
    stdout = proc.stdout
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    hunks = unified_diff_hunks(stdout or "")
    return [h for h in hunks if not _is_test_path(h.file)]
