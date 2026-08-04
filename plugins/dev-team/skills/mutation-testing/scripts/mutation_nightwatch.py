#!/usr/bin/env python3
"""mutation_nightwatch.py — unattended, LLM-free overnight mutation night-watch.

A third mode alongside the ``mutation-kill`` agent's interactive and
``--headless`` fixing modes (#1754): this one only *measures*. It never
generates a test, never invokes an LLM, and never commits. It exists so a
mutation-score baseline can run unattended overnight and be waiting, already
scored, for the ``mutation-kill`` agent (or a human) the next morning.

Per run:

1. Detect which of this repo's mutation-tool stacks are present
   (``mutation_nightwatch_stacks.detect_stacks``), mirroring
   ``references/tool-detection.md``.
2. For each **supported** stack (one ``mutation_report.py`` can already
   parse: Stryker/JS, Stryker.NET/C#, mutmut/Python — see
   ``mutation_nightwatch_stacks.SUPPORTED_STACKS``), run a mechanical,
   code-untouching dependency-restore step (``mechanical_repair`` — ``npm
   ci`` / ``dotnet restore``: package-pin sync only, never a production or
   test file, never committed), then run the tool's own report-only
   mutation pass and score it via ``mutation_report.py`` (reused, not
   reimplemented).
3. Write ``MORNING-SUMMARY.md`` (human) + ``SURVIVORS.json`` (machine —
   ``{stack, module, file, line, mutator, change, status}`` per survivor) to
   a timestamped run directory AND mirror both into a stable ``LATEST/`` dir
   so downstream tooling never needs to know the run's folder name.
   Refreshed after every module completes (#1756), not only at the very
   end — a mid-run kill or timeout leaves whatever finished so far, never
   nothing.

``--detach`` re-execs the script into a new session/process group so the run
outlives the launching terminal (same pattern as
``hooks/codegraph_bootstrap.py``). A ``SleepInhibitor`` holds the OS awake for
the run's duration on macOS (``caffeinate``) and Linux (``systemd-inhibit``);
on Windows it calls ``SetThreadExecutionState`` directly (no subprocess to
hold open). When none of those are available, the run proceeds but the
missing coverage is always a printed/recorded NOTE, never a silent no-op —
see the CLAUDE.md rule this mirrors: "a gate that cannot fail is worse than
no gate."

Per-stack detection, mechanical repair, and measurement live in
``mutation_nightwatch_stacks.py`` (imported here as ``stacks_lib``) — split
out to keep each module under the shipped file-line budget, mirroring this
skill's existing ``mutation_kill_loop.py`` / ``mutation_kill_headless.py`` /
``mutation_kill_shared.py`` split. This module owns orchestration only:
sleep inhibition, the report writer, ``--detach``, and the CLI.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import mutation_nightwatch_stacks as stacks_lib
from mutation_kill_shared import _timeout_from_env

DEFAULT_OUTPUT_DIR = "reports/mutation-nightwatch"

# Per-stack subprocess ceiling. Long by design (this runs overnight) but never
# unbounded — an infinite-loop mutant or a hung tool must not block the run
# forever. Overridable for repos with a legitimately longer suite.
DEFAULT_STACK_TIMEOUT_S = _timeout_from_env(
    "DEV_TEAM_NIGHTWATCH_TIMEOUT_S", 6 * 60 * 60
)


# =============================================================================
# OS sleep inhibition — never a silent no-op. "A gate that cannot fail is
# worse than no gate" applies here too: if the run can't hold the machine
# awake, that must be a visible NOTE, not silence.
# =============================================================================

# Windows-only; harmless to define unconditionally since it's only read when
# platform.system() == "Windows".
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class SleepInhibitor:
    """Context manager holding the OS awake for the run's duration.

    macOS: ``caffeinate -dims`` as a held-open child process.
    Linux: ``systemd-inhibit --what=sleep:idle -- sleep infinity``, same
    pattern.
    Windows: ``SetThreadExecutionState`` directly — no subprocess needed.
    Anything else (missing binary, unrecognized platform): ``note`` is set
    and the run proceeds uninhibited.

    ``system_name``/``which``/``popen`` are injectable for tests; production
    callers use the defaults.
    """

    def __init__(
        self,
        *,
        system_name: str | None = None,
        which=None,
        popen=subprocess.Popen,
    ) -> None:
        import platform
        import shutil

        self._system_name = system_name if system_name is not None else platform.system()
        self._which = which if which is not None else shutil.which
        self._popen = popen
        self.method: str | None = None
        self.note: str | None = None
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> SleepInhibitor:  # noqa: PYI034 — typing.Self needs 3.11+; floor is py310
        if self._system_name == "Darwin" and self._which("caffeinate"):
            self._proc = self._popen(["caffeinate", "-dims"])
            self.method = "caffeinate"
        elif self._system_name == "Linux" and self._which("systemd-inhibit"):
            self._proc = self._popen(
                [
                    "systemd-inhibit",
                    "--what=sleep:idle",
                    "--why=mutation-nightwatch run",
                    "sleep",
                    "infinity",
                ]
            )
            self.method = "systemd-inhibit"
        elif self._system_name == "Windows":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
                    _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
                )
                self.method = "SetThreadExecutionState"
            except (AttributeError, OSError):
                self.method = None

        if self.method is None:
            self.note = (
                f"NOTE: sleep inhibition unavailable on {self._system_name} — "
                "install caffeinate (macOS) / systemd-inhibit (Linux), or run "
                "on Windows where SetThreadExecutionState is used directly. "
                "The machine may sleep mid-run."
            )
        return self

    def __exit__(self, *exc_info) -> bool:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        elif self.method == "SetThreadExecutionState":
            with contextlib.suppress(AttributeError, OSError):
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)  # type: ignore[attr-defined]
        return False


# =============================================================================
# Report writer — MORNING-SUMMARY.md (human) + SURVIVORS.json (machine),
# mirrored into a stable LATEST/ dir alongside the timestamped run dir.
# =============================================================================


def write_reports(
    run_dir: Path,
    latest_dir: Path,
    results: list[stacks_lib.StackResult],
    started_at: str,
    notes: list[str],
) -> None:
    survivors_payload = {
        "schema_version": 1,
        "generated_at": started_at,
        "survivors": [s for r in results for s in r.survivors],
    }

    lines = ["# Mutation Night-Watch — Morning Summary", "", f"Run started: {started_at}", ""]
    if notes:
        lines.append("## Notes")
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    lines.append(
        "| Stack | Tool | Status | Honest score | Killed | Survived | Timeout | NoCoverage | Duration |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for result in results:
        if result.summary is not None:
            s = result.summary
            lines.append(
                f"| {result.stack} | {result.tool} | {result.status} | "
                f"{s.honest_score:.1f}% | {s.killed} | {s.survived} | {s.timeout} | "
                f"{s.no_coverage} | {result.duration_seconds:.0f}s |"
            )
        else:
            lines.append(
                f"| {result.stack} | {result.tool} | {result.status} | "
                f"— | — | — | — | — | {result.duration_seconds:.0f}s |"
            )
        if result.detail:
            lines.append(f"  - {result.detail}")

    total_survivors = len(survivors_payload["survivors"])
    lines.append("")
    if total_survivors:
        lines.append(
            f"{total_survivors} surviving mutant(s) captured in `SURVIVORS.json` — "
            "hand off to the mutation-kill agent."
        )
    else:
        lines.append("No surviving mutants captured this run.")
    lines.append("")

    for target_dir in (run_dir, latest_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "MORNING-SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
        (target_dir / "SURVIVORS.json").write_text(
            json.dumps(survivors_payload, indent=2) + "\n", encoding="utf-8"
        )


# =============================================================================
# Orchestration
# =============================================================================


def _run_slug(started_at: str) -> str:
    return started_at.replace(":", "").replace("-", "")


def run_nightwatch(
    repo_root: Path,
    output_dir: Path,
    *,
    stacks: list[str] | None = None,
    inhibit_sleep: bool = True,
    timeout: int | None = None,
    started_at: str | None = None,
) -> Path:
    """Run one full night-watch pass. Returns the timestamped run directory.

    ``stacks`` overrides autodetection with an explicit stack-name list.
    ``started_at`` is injectable for tests; production callers omit it and
    get the real current UTC time.
    """
    if started_at is None:
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_dir = output_dir / _run_slug(started_at)
    latest_dir = output_dir / "LATEST"
    run_dir.mkdir(parents=True, exist_ok=True)

    detected = stacks_lib.detect_stacks(repo_root)
    targets = stacks if stacks is not None else sorted(
        name for name, found in detected.items() if found
    )

    notes: list[str] = []
    results: list[stacks_lib.StackResult] = []

    # Refreshed after every module completes (#1756), not only at the very
    # end — a mid-run kill or timeout must leave whatever finished so far,
    # not nothing. The pre-loop write covers the empty-targets case (and a
    # kill during the very first stack's run) with at least the
    # sleep-inhibitor NOTE, if any.
    with SleepInhibitor() if inhibit_sleep else contextlib.nullcontext() as inhibitor:
        if inhibitor is not None and inhibitor.note:
            notes.append(inhibitor.note)
        write_reports(run_dir, latest_dir, results, started_at, notes)
        for name in targets:
            if name not in stacks_lib.SUPPORTED_STACKS:
                results.append(
                    stacks_lib.StackResult(
                        name,
                        name,
                        "skipped_no_parser",
                        f"{name} detected but mutation_report.py has no parser for "
                        "its native report shape yet",
                    )
                )
                write_reports(run_dir, latest_dir, results, started_at, notes)
                continue
            repair_note = stacks_lib.mechanical_repair(name, repo_root, run_dir)
            if repair_note:
                notes.append(repair_note)
            results.append(stacks_lib.MEASURERS[name](repo_root, run_dir, timeout=timeout))
            write_reports(run_dir, latest_dir, results, started_at, notes)

    return run_dir


# =============================================================================
# --detach — re-exec into a new session/process group, same pattern as
# hooks/codegraph_bootstrap.py.
# =============================================================================


def _detach_popen_kwargs(log_file) -> dict:
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": log_file, "stderr": subprocess.STDOUT}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = 0x00000008  # Windows DETACHED_PROCESS
    return kwargs


def relaunch_detached(argv: list[str], log_path: Path, *, popen=subprocess.Popen) -> int:
    """Re-exec this script without ``--detach``, backgrounded so the run
    outlives the launching terminal/session. Returns the child's PID."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), *[a for a in argv if a != "--detach"]]
    log_file = open(log_path, "ab")  # noqa: SIM115 — deliberately kept open past return, owned by the child
    proc = popen(cmd, **_detach_popen_kwargs(log_file))
    log_file.close()
    return proc.pid


# =============================================================================
# CLI
# =============================================================================


def parse_args(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_nightwatch.py",
        description=(
            "Unattended, LLM-free overnight mutation night-watch: report-only "
            "measurement, never generation."
        ),
    )
    p.add_argument("--repo-root", default=".", help="Repo root to scan (default: cwd)")
    p.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Report output dir, relative to --repo-root (default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--detach",
        action="store_true",
        help="Re-exec detached (new session/process group) and return immediately.",
    )
    p.add_argument(
        "--stacks",
        help="Comma-separated stack override (default: autodetect). Choices: "
        + ", ".join(sorted(stacks_lib.STACK_DETECTORS)),
    )
    p.add_argument(
        "--no-sleep-inhibit",
        action="store_true",
        help="Skip OS sleep inhibition (CI, or a machine that never sleeps).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_STACK_TIMEOUT_S,
        help=f"Per-stack subprocess ceiling in seconds (default: {DEFAULT_STACK_TIMEOUT_S})",
    )
    return p.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    if args.detach:
        log_path = output_dir / "detached-launch.log"
        pid = relaunch_detached(argv, log_path)
        print(f"mutation-nightwatch detached: pid={pid} log={log_path}")
        return 0

    stack_names = [s.strip() for s in args.stacks.split(",")] if args.stacks else None
    run_dir = run_nightwatch(
        repo_root,
        output_dir,
        stacks=stack_names,
        inhibit_sleep=not args.no_sleep_inhibit,
        timeout=args.timeout,
    )
    print(f"mutation-nightwatch run complete: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
