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
from typing import Any, Dict, List, Optional, Sequence

from .common import BenchmarkCase, run_with_timeout, unified_diff_hunks

DEFAULT_RUN_FN = run_with_timeout


def detect(defects4j_home: Optional[str], defects4j_bin: Optional[str] = None) -> bool:
    """True when a `defects4j` binary is reachable and `defects4j_home` looks like a real checkout.

    `defects4j_bin`, when given, is an explicit path to the executable
    (e.g. an auto-provisioned cache clone's `framework/bin/defects4j`) and
    is checked directly instead of requiring `defects4j` on `PATH` — a
    fresh auto-clone won't be on `PATH`. Omitting it preserves the
    original PATH-based lookup.
    """
    if not defects4j_home:
        return False
    if not (Path(defects4j_home) / "framework" / "projects").is_dir():
        return False
    if defects4j_bin:
        return Path(defects4j_bin).is_file()
    return shutil.which("defects4j") is not None


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
    defects4j_bin: str = "defects4j",
    env: Optional[Dict[str, str]] = None,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 600,
) -> bool:
    """`defects4j checkout -p <project> -v <bug_id>b -w <workdir>`.

    Returns True on a zero exit code, False on any failure — never raises.
    `defects4j_bin` defaults to the bare command name (PATH lookup); pass
    an explicit path for an auto-provisioned cache clone. `env`, when
    given, overrides the subprocess environment (#951 — an auto-resolved
    Java 11 + Perl CPAN env from `bootstrap.build_defects4j_env()`);
    `None` inherits this process's environment unchanged.
    """
    argv = [
        defects4j_bin,
        "checkout",
        "-p",
        case.project,
        "-v",
        f"{case.bug_id}b",
        "-w",
        workdir,
    ]
    try:
        proc = run_fn(timeout, argv, capture_output=True, text=True, env=env)
    except (OSError, ValueError):
        return False
    return proc.returncode == 0


def run_tests(
    case: BenchmarkCase,
    checkout_dir: str,
    defects4j_bin: str = "defects4j",
    env: Optional[Dict[str, str]] = None,
    run_fn=DEFAULT_RUN_FN,
    compile_timeout: int = 300,
    test_timeout: int = 600,
) -> Dict[str, Any]:
    """Configure (`defects4j compile`) and run (`defects4j test`) the buggy checkout.

    Diagnostic sanity check, not a gate: confirms the buggy revision
    actually reproduces a failing test via Defects4J's own bookkeeping
    (`<checkout_dir>/failing_tests`), which lists trigger tests as lines
    `--- <test.class>::<method>`. Never raises — any subprocess/OS failure
    is folded into the returned dict, same contract as `checkout()`/
    `describe()` above. `defects4j_bin` defaults to the bare command name
    (PATH lookup); pass an explicit path for an auto-provisioned cache
    clone. `env` overrides the subprocess environment (#951); `None`
    inherits this process's environment unchanged.
    """
    try:
        compile_proc = run_fn(
            compile_timeout,
            [defects4j_bin, "compile"],
            cwd=checkout_dir,
            capture_output=True,
            text=True,
            env=env,
        )
    except (OSError, ValueError) as exc:
        return {
            "configured": False,
            "ran": False,
            "reproduced": False,
            "error": str(exc),
        }
    if compile_proc.returncode != 0:
        return {"configured": False, "ran": False, "reproduced": False}

    try:
        test_proc = run_fn(
            test_timeout,
            [defects4j_bin, "test"],
            cwd=checkout_dir,
            capture_output=True,
            text=True,
            env=env,
        )
    except (OSError, ValueError) as exc:
        return {
            "configured": True,
            "ran": False,
            "reproduced": False,
            "error": str(exc),
        }

    failing_tests: List[str] = []
    failing_tests_path = Path(checkout_dir) / "failing_tests"
    if failing_tests_path.is_file():
        failing_tests = [
            line[len("---") :].strip()
            for line in failing_tests_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("---")
        ]

    return {
        "configured": True,
        "ran": test_proc.returncode == 0,
        "reproduced": bool(failing_tests),
        "failing_tests": failing_tests,
    }


def describe(
    case: BenchmarkCase,
    defects4j_bin: str = "defects4j",
    env: Optional[Dict[str, str]] = None,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 60,
) -> Optional[str]:
    """Best-effort `defects4j info -p <project> -b <bug_id>`. `None` on any failure."""
    argv = [defects4j_bin, "info", "-p", case.project, "-b", case.bug_id]
    try:
        proc = run_fn(timeout, argv, capture_output=True, text=True, env=env)
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    stdout = proc.stdout
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    return stdout or None
