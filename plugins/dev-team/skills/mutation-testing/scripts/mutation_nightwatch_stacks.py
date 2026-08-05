#!/usr/bin/env python3
"""mutation_nightwatch_stacks.py — per-stack detection, mechanical repair, and
report-only measurement for ``mutation_nightwatch.py`` (#1754).

Split out of ``mutation_nightwatch.py`` to keep each module under the shipped
file-line budget (``token_efficiency_review.py``'s file-line-limit rule) —
mirrors this skill's existing ``mutation_kill_loop.py`` /
``mutation_kill_headless.py`` / ``mutation_kill_shared.py`` split.
``mutation_nightwatch.py`` imports this module as ``stacks`` and never
duplicates its logic; orchestration (``SleepInhibitor``, ``--detach``, the
report writer, the CLI) stays there.

Detection mirrors ``references/tool-detection.md``. Measurement reuses
``mutation_report.py`` for scoring rather than reimplementing a parser —
``SUPPORTED_STACKS`` is exactly the set that module can already score
(Stryker-shaped JSON, or mutmut's junitxml); pitest and go-mutesting are
detected but not measured — see the module-level note on ``SUPPORTED_STACKS``.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import mutation_report

# =============================================================================
# Stack detection — mirrors references/tool-detection.md's rules, but as
# executable code rather than a table a human has to re-derive by hand.
# =============================================================================


def _detect_javascript(repo_root: Path) -> bool:
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    return "@stryker-mutator/core" in deps or (repo_root / "stryker.conf.json").exists()


def _detect_python(repo_root: Path) -> bool:
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        candidate = repo_root / name
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "mutmut" in text:
            return True
    return False


def _detect_csharp(repo_root: Path) -> bool:
    manifest = repo_root / ".config" / "dotnet-tools.json"
    if not manifest.exists():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    return "dotnet-stryker" in data.get("tools", {})


def _detect_java(repo_root: Path) -> bool:
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        candidate = repo_root / name
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "pitest" in text:
            return True
    return False


def _detect_go(repo_root: Path) -> bool:
    return (repo_root / "go.mod").exists()


# Every stack this script can *recognize*, per references/tool-detection.md.
STACK_DETECTORS = {
    "javascript": _detect_javascript,
    "python": _detect_python,
    "csharp": _detect_csharp,
    "java": _detect_java,
    "go": _detect_go,
}

# The subset mutation_report.py can already score (Stryker-shaped JSON, or
# mutmut's junitxml). pitest (XML) and go-mutesting (stdout, advisory-only)
# have no parser there yet — see the module docstring's "Emitting adapters"
# note in SKILL.md. Recognized-but-unsupported stacks are reported, never
# guessed.
SUPPORTED_STACKS = {"javascript", "python", "csharp"}


def detect_stacks(repo_root: Path) -> dict[str, bool]:
    """Return every known stack name mapped to whether it was detected."""
    return {name: detector(repo_root) for name, detector in STACK_DETECTORS.items()}


# =============================================================================
# Safe subprocess capture — never a bare `<tool> | tee` pipeline (see
# SKILL.md § Capturing run output safely: `tee`'s exit code masks a tool
# failure). Every invocation appends directly to its own log file.
# =============================================================================


def _run_logged(
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess | None:
    """Run ``cmd``, appending its combined output to ``log_path``.

    Returns ``None`` (never raises) when the binary is missing or the run
    times out — both are recorded in the log first so the failure is visible
    without inspecting the return value.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
                text=True,
            )
        except FileNotFoundError as exc:
            log.write(f"\n[mutation-nightwatch] command not found: {exc}\n")
            return None
        except subprocess.TimeoutExpired:
            log.write(f"\n[mutation-nightwatch] command timed out after {timeout}s\n")
            return None


# =============================================================================
# Mechanical build repair — dependency-restore only. Never touches production
# code or tests, never commits. "auto-repair only mechanical build breaks ...
# never production code, never tests, never committed" (#1754).
# =============================================================================


def mechanical_repair(stack: str, repo_root: Path, run_dir: Path) -> str | None:
    """Run a stack's package-pin-sync step before measurement.

    Returns a human-readable NOTE describing the outcome, or ``None`` when
    the stack has no repair step (or nothing needed doing).
    """
    if stack == "javascript":
        if (repo_root / "node_modules").exists():
            return None
        log_path = run_dir / "javascript-repair.log"
        result = _run_logged(["npm", "ci"], repo_root, log_path)
        if result is None or result.returncode != 0:
            return f"NOTE: npm ci (package-pin sync) failed — see {log_path.name}"
        return "npm ci: package-pin sync OK"
    if stack == "csharp":
        log_path = run_dir / "csharp-repair.log"
        result = _run_logged(["dotnet", "restore"], repo_root, log_path)
        if result is None or result.returncode != 0:
            return f"NOTE: dotnet restore (package-pin sync) failed — see {log_path.name}"
        return "dotnet restore: package-pin sync OK"
    return None


# =============================================================================
# Per-stack measurement. Report-only — no generation, ever.
# =============================================================================


@dataclass
class StackResult:
    stack: str
    tool: str
    status: str  # "measured" | "skipped_no_parser" | "skipped" | "error"
    detail: str = ""
    summary: mutation_report.ScoreSummary | None = None
    survivors: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    # The native report path on disk, when the tool produces one at a fixed
    # convention path (Stryker-shaped JSON: javascript, csharp). ``None``
    # for mutmut (python) — junitxml is captured in-memory, not written to
    # a fixed path — and for any non-"measured" status. Consumed by
    # mutation_exclude_policy.py's per-file drafting (#1757), which needs
    # the native report to compute a per-file score, not just the
    # already-flattened `survivors` list.
    report_path: Path | None = None


def _flat_survivors(report_path: Path, stack: str) -> list[dict]:
    out: list[dict] = []
    for file_key in mutation_report.files_with_survivors(report_path):
        grouped = mutation_report.survivors_by_mutator(report_path, file_key)
        for mutator, mutants in grouped.items():
            for mutant in mutants:
                out.append(
                    {
                        "stack": stack,
                        "module": stack,
                        "file": file_key,
                        "line": mutant.get("location", {}).get("start", {}).get("line"),
                        "mutator": mutator,
                        "change": mutant.get("replacement", ""),
                        "status": "survived",
                    }
                )
    return out


def _flat_survivors_mutmut(xml_text: str, stack: str) -> list[dict]:
    data = mutation_report.parse_mutmut_junitxml(xml_text)
    out: list[dict] = []
    for file_key, info in data.get("files", {}).items():
        for mutant in info.get("mutants", []):
            if mutant.get("status") != mutation_report.STATUS_SURVIVED:
                continue
            out.append(
                {
                    "stack": stack,
                    "module": stack,
                    "file": file_key,
                    "line": mutant.get("location", {}).get("start", {}).get("line"),
                    "mutator": mutant.get("mutatorName", "mutmut"),
                    "change": mutant.get("replacement", ""),
                    "status": "survived",
                }
            )
    return out


def measure_javascript(
    repo_root: Path, run_dir: Path, *, timeout: int | None = None
) -> StackResult:
    log_path = run_dir / "javascript.log"
    start = time.monotonic()
    result = _run_logged(["npx", "stryker", "run"], repo_root, log_path, timeout=timeout)
    duration = time.monotonic() - start
    if result is None:
        return StackResult(
            "javascript",
            "stryker",
            "error",
            f"stryker did not run — see {log_path.name}",
            duration_seconds=duration,
        )
    # A tool exit-code below its configured break threshold is expected on a
    # low-scoring run, not a measurement failure — never gate on returncode.
    report_path = repo_root / "reports" / "mutation" / "mutation.json"
    if not mutation_report.load_report(report_path):
        return StackResult(
            "javascript",
            "stryker",
            "error",
            f"no mutation report at {report_path} — see {log_path.name}",
            duration_seconds=duration,
        )
    return StackResult(
        "javascript",
        "stryker",
        "measured",
        summary=mutation_report.score_report(report_path),
        survivors=_flat_survivors(report_path, "javascript"),
        duration_seconds=duration,
        report_path=report_path,
    )


def measure_python(
    repo_root: Path, run_dir: Path, *, timeout: int | None = None
) -> StackResult:
    log_path = run_dir / "python.log"
    start = time.monotonic()
    run_result = _run_logged(["mutmut", "run"], repo_root, log_path, timeout=timeout)
    if run_result is None:
        return StackResult(
            "python",
            "mutmut",
            "error",
            f"mutmut run did not execute — see {log_path.name}",
            duration_seconds=time.monotonic() - start,
        )
    try:
        xml_result = subprocess.run(
            ["mutmut", "junitxml"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return StackResult(
            "python",
            "mutmut",
            "error",
            f"mutmut junitxml failed: {exc}",
            duration_seconds=time.monotonic() - start,
        )
    duration = time.monotonic() - start
    return StackResult(
        "python",
        "mutmut",
        "measured",
        summary=mutation_report.score_mutmut_junitxml(xml_result.stdout),
        survivors=_flat_survivors_mutmut(xml_result.stdout, "python"),
        duration_seconds=duration,
    )


def measure_csharp(
    repo_root: Path, run_dir: Path, *, timeout: int | None = None
) -> StackResult:
    sln_candidates = sorted(repo_root.glob("*.sln"))
    if len(sln_candidates) != 1:
        return StackResult(
            "csharp",
            "stryker-net",
            "skipped",
            f"expected exactly one .sln in repo root, found {len(sln_candidates)} "
            "— cannot auto-select; run mutation-kill manually",
        )
    if not (repo_root / "stryker-config.json").exists():
        return StackResult("csharp", "stryker-net", "skipped", "no stryker-config.json found")

    wrapper = Path(__file__).resolve().parent / "csharp_stryker_net_wrapper.py"
    output_dir = run_dir / "csharp"
    log_path = run_dir / "csharp.log"
    start = time.monotonic()
    cmd = [
        sys.executable,
        str(wrapper),
        "--sln",
        sln_candidates[0].name,
        "--",
        "--config-file",
        "stryker-config.json",
        "-O",
        str(output_dir),
    ]
    result = _run_logged(cmd, repo_root, log_path, timeout=timeout)
    duration = time.monotonic() - start
    if result is None:
        return StackResult(
            "csharp",
            "stryker-net",
            "error",
            f"csharp_stryker_net_wrapper.py did not run — see {log_path.name}",
            duration_seconds=duration,
        )
    report_path = output_dir / "reports" / "mutation-report.json"
    if not mutation_report.load_report(report_path):
        return StackResult(
            "csharp",
            "stryker-net",
            "error",
            f"no mutation report at {report_path} — see {log_path.name}",
            duration_seconds=duration,
        )
    return StackResult(
        "csharp",
        "stryker-net",
        "measured",
        summary=mutation_report.score_report(report_path),
        survivors=_flat_survivors(report_path, "csharp"),
        duration_seconds=duration,
        report_path=report_path,
    )


MEASURERS = {
    "javascript": measure_javascript,
    "python": measure_python,
    "csharp": measure_csharp,
}
