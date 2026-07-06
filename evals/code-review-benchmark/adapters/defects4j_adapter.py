"""Defects4J adapter for the /code-review benchmark harness (#821).

Ground truth comes from the real developer patch shipped with the framework
(`framework/projects/<project>/patches/<bug_id>.src.patch`) — verified this
session against a real fetch of `Lang/patches/1.src.patch`, a standard
`diff --git` / `--- a/` / `+++ b/` / `@@ -a,b +c,d @@` unified diff. Bug
metadata (buggy/fixed revisions) comes from `active-bugs.csv`, columns
`bug.id,revision.id.buggy,revision.id.fixed,report.id,report.url` (also
verified against a real fetch).

Never raises on a missing `defects4j` install or an unparsable bug — callers
(the runner) treat a `None` return as "skip and log," per the harness's
fail-loudly-and-skip contract.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any, List, Optional, Sequence

from .common import BenchmarkCase, run_with_timeout, unified_diff_hunks

DEFAULT_RUN_FN = run_with_timeout


def detect(defects4j_home: Optional[str]) -> bool:
    """True when `defects4j` is on PATH and `defects4j_home` looks like a real checkout."""
    if shutil.which("defects4j") is None:
        return False
    if not defects4j_home:
        return False
    return (Path(defects4j_home) / "framework" / "projects").is_dir()


def _active_bugs_csv(defects4j_home: str, project: str) -> Path:
    return Path(defects4j_home) / "framework" / "projects" / project / "active-bugs.csv"


def list_projects(defects4j_home: str) -> List[str]:
    """Every project dir under `framework/projects` that has an `active-bugs.csv`."""
    projects_dir = Path(defects4j_home) / "framework" / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir() and (p / "active-bugs.csv").is_file()
    )


def _patch_path(defects4j_home: str, project: str, bug_id: str) -> Path:
    return (
        Path(defects4j_home)
        / "framework"
        / "projects"
        / project
        / "patches"
        / f"{bug_id}.src.patch"
    )


def list_bugs(project: str, defects4j_home: str) -> List[BenchmarkCase]:
    """Parse `active-bugs.csv` + each bug's `.src.patch` into BenchmarkCases.

    A bug whose patch is missing or unparsable is skipped (not included in
    the returned list) rather than raising — the caller logs the gap.
    """
    csv_path = _active_bugs_csv(defects4j_home, project)
    if not csv_path.is_file():
        return []

    cases: List[BenchmarkCase] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            bug_id = row.get("bug.id")
            if not bug_id:
                continue
            patch_path = _patch_path(defects4j_home, project, bug_id)
            if not patch_path.is_file():
                continue
            try:
                diff_text = patch_path.read_text(encoding="utf-8")
            except OSError:
                continue
            hunks = unified_diff_hunks(diff_text)
            if not hunks:
                continue
            files = sorted({h.file for h in hunks})
            cases.append(
                BenchmarkCase(
                    dataset="defects4j",
                    project=project,
                    bug_id=bug_id,
                    language="java",
                    ground_truth_files=files,
                    ground_truth_hunks=[h.to_dict() for h in hunks],
                    description=row.get("report.url"),
                    extra={
                        "revision_buggy": row.get("revision.id.buggy"),
                        "revision_fixed": row.get("revision.id.fixed"),
                        "report_id": row.get("report.id"),
                    },
                )
            )
    return cases


def checkout(
    case: BenchmarkCase,
    workdir: str,
    defects4j_home: Optional[str] = None,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 600,
) -> bool:
    """`defects4j checkout -p <project> -v <bug_id>b -w <workdir>`.

    Returns True on a zero exit code, False on any failure — never raises.
    """
    argv = [
        "defects4j",
        "checkout",
        "-p",
        case.project,
        "-v",
        f"{case.bug_id}b",
        "-w",
        workdir,
    ]
    try:
        proc = run_fn(timeout, argv, capture_output=True, text=True)
    except (OSError, ValueError):
        return False
    return proc.returncode == 0


def describe(
    case: BenchmarkCase,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 60,
) -> Optional[str]:
    """Best-effort `defects4j info -p <project> -b <bug_id>`. `None` on any failure."""
    argv = ["defects4j", "info", "-p", case.project, "-b", case.bug_id]
    try:
        proc = run_fn(timeout, argv, capture_output=True, text=True)
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    stdout = proc.stdout
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    return stdout or None
