#!/usr/bin/env python3
"""csharp_stryker_net_status_loop.py — status + red-flag inspection loop for
long-running Stryker.NET invocations.

Called by csharp_stryker_net_wrapper.py (or usable standalone via the CLI).
Public API (importable):

    parse_dots_count(logfile: Path) -> int
    parse_summary_count(logfile: Path, key: str) -> Optional[int]
    log_has_completion_marker(logfile: Path) -> bool
    emit_status_line(logfile: Path) -> str
    check_red_flags(logfile, threshold, stryker_pid, expected_target=None, state_dir=None, drift_threshold=3) -> list[str]
    status_loop_start(logfile, interval, threshold, stryker_pid, expected_target=None, state_dir=None, drift_threshold=3) -> None

Refs: #558 (original bash), #571 (setup() fork hang on MSYS — closed by
this Python port at the source), #572 (bash → Python migration epic).
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Optional


# =============================================================================
# Log parsers — pure functions
# =============================================================================
_DOTS_HEADER_RE = re.compile(r"^Testing mutants:\s*$")


def parse_dots_count(logfile: Path) -> int:
    """Count '.' characters on the first non-empty line following
    'Testing mutants:'. Dots reporter uses one dot per completed mutant;
    survives log redirection. Returns 0 when the marker is absent OR the
    first following non-empty line isn't a dots line.

    Missing / unreadable file → 0 (silent — the loop tolerates a not-yet-
    written log).
    """
    try:
        with logfile.open() as f:
            collecting = False
            for line in f:
                if _DOTS_HEADER_RE.match(line):
                    collecting = True
                    continue
                if not collecting:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                if line.startswith("."):
                    return line.count(".")
                # First non-empty line after the header wasn't dots.
                return 0
        return 0
    except (OSError, FileNotFoundError):
        return 0


_SUMMARY_RES: dict[str, re.Pattern[str]] = {}


def _summary_re(key: str) -> re.Pattern[str]:
    if key not in _SUMMARY_RES:
        _SUMMARY_RES[key] = re.compile(rf"^{re.escape(key)}:\s+(\d+)")
    return _SUMMARY_RES[key]


def parse_summary_count(logfile: Path, key: str) -> Optional[int]:
    """Extract ``<key>:  <n>`` from the last matching line in the log.

    Returns the count as int, or None if no line matches. Missing file
    also returns None.
    """
    pattern = _summary_re(key)
    last: Optional[int] = None
    try:
        with logfile.open() as f:
            for line in f:
                m = pattern.match(line)
                if m:
                    last = int(m.group(1))
        return last
    except (OSError, FileNotFoundError):
        return None


_COMPLETION_RE = re.compile(r"The final mutation score|Stryker execution finished")


def log_has_completion_marker(logfile: Path) -> bool:
    """True when Stryker's end-of-run marker is present in the log."""
    try:
        with logfile.open() as f:
            for line in f:
                if _COMPLETION_RE.search(line):
                    return True
        return False
    except (OSError, FileNotFoundError):
        return False


_COMPILE_ERROR_RE = re.compile(r"CompileError")
_TARGET_PATH_RE = re.compile(r"^Property TargetPath=(.+)$", re.MULTILINE)


def count_compile_errors(logfile: Path) -> int:
    try:
        return sum(1 for line in logfile.open() if _COMPILE_ERROR_RE.search(line))
    except (OSError, FileNotFoundError):
        return 0


def unexpected_target_path(logfile: Path, expected_fragment: str) -> Optional[str]:
    """Return the first ``Property TargetPath=<path>`` line whose path does
    NOT contain expected_fragment, or None if all match / none present.
    """
    try:
        for line in logfile.open():
            m = _TARGET_PATH_RE.match(line.rstrip("\n"))
            if m:
                path = m.group(1)
                if expected_fragment not in path:
                    return path
        return None
    except (OSError, FileNotFoundError):
        return None


# =============================================================================
# emit_status_line — one status record per tick
# =============================================================================
def emit_status_line(logfile: Path) -> str:
    """Return one status record string:

        tested=<n> killed=<n> survived=<n> timeout=<n> elapsed=<HH:MM|?>

    Callers write this to stdout (or wherever they route it).
    """
    tested = parse_dots_count(logfile)
    killed = parse_summary_count(logfile, "Killed")
    survived = parse_summary_count(logfile, "Survived")
    timeout = parse_summary_count(logfile, "Timeout")
    # Elapsed derived from the log's first-line INF timestamp when present.
    elapsed = "?"
    return (
        f"tested={tested} "
        f"killed={killed if killed is not None else 0} "
        f"survived={survived if survived is not None else 0} "
        f"timeout={timeout if timeout is not None else 0} "
        f"elapsed={elapsed}"
    )


# =============================================================================
# check_red_flags — the five detectors + parser-drift catch-all
# =============================================================================
def _drift_counter_path(state_dir: Path, stryker_pid: Optional[int]) -> Path:
    """Per-PID counter file. Falls back to 'noop' when PID is missing so the
    counter still gets a stable location (tests that omit PID share one).
    """
    pid_component = str(stryker_pid) if stryker_pid else "noop"
    return state_dir / f"drift-counter-{pid_component}"


def _pid_is_alive(pid: int) -> bool:
    """Cross-platform 'signal 0' liveness check. Returns False on Windows
    when the PID doesn't exist (OSError WinError 87); True when it does.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but is owned by another user — from the loop's
        # perspective, it's alive.
        return True
    except OSError:
        # Unknown error — err on the side of "alive" to avoid false
        # died-mid-run red flags.
        return True


def check_red_flags(
    logfile: Path,
    threshold: int,
    stryker_pid: Optional[int],
    expected_target: Optional[str] = None,
    state_dir: Optional[Path] = None,
    drift_threshold: int = 3,
) -> list[str]:
    """Grep the log for known-broken signatures, check PID liveness, and
    return zero or more ``[RED-FLAG] …`` lines. Consecutive-unrecognized-tick
    counter is kept in a file under ``state_dir`` (default $TMPDIR), so a
    reporter-format drift is self-detecting.
    """
    if state_dir is None:
        state_dir = Path(os.environ.get("TMPDIR", "/tmp"))
    state_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    recognized = False

    killed = parse_summary_count(logfile, "Killed")
    survived = parse_summary_count(logfile, "Survived")
    compile_errors = count_compile_errors(logfile)

    # --- Red flag 1: Killed==0 && Survived>0 (mutation-switch not observing)
    if killed is not None and survived is not None:
        recognized = True
        if killed == 0 and survived > 0:
            lines.append(
                f"[RED-FLAG] mutation-switch not observing mutations at "
                f"runtime (Killed=0, Survived={survived}) — see #554"
            )

    # --- Red flag 2: CompileError count strictly > threshold
    if compile_errors > 0:
        recognized = True
        if compile_errors > threshold:
            lines.append(
                f"[RED-FLAG] CompileError count {compile_errors} over "
                f"threshold {threshold} — probe file / mutate glob likely "
                f"misconfigured"
            )

    # --- Red flag 3: SolutionPath naming an unexpected TargetPath
    if expected_target:
        unexpected = unexpected_target_path(logfile, expected_target)
        if unexpected:
            recognized = True
            lines.append(
                f"[RED-FLAG] SolutionPath trap — {unexpected} does not "
                f"contain expected {expected_target} — see #557"
            )

    # --- Red flag 4: Stryker PID dead AND no completion marker
    if stryker_pid is not None and not _pid_is_alive(stryker_pid):
        if not log_has_completion_marker(logfile):
            recognized = True
            lines.append(
                f"[RED-FLAG] Stryker process died mid-run (PID {stryker_pid} "
                f"no longer running, no completion marker in log) — see #558"
            )

    # A log with dots or a completion marker is "recognized" even if no
    # summary parser fired — this stops false drift-alerts during a healthy
    # mid-run tick.
    if parse_dots_count(logfile) > 0 or log_has_completion_marker(logfile):
        recognized = True

    # --- Red flag 5: parser drift — N consecutive unrecognized ticks
    counter_file = _drift_counter_path(state_dir, stryker_pid)
    drift = 0
    if counter_file.exists():
        try:
            drift = int(counter_file.read_text().strip() or "0")
        except (OSError, ValueError):
            drift = 0
    drift = 0 if recognized else drift + 1
    try:
        counter_file.write_text(f"{drift}\n")
    except OSError:
        # If we can't write the counter, the drift check degrades to
        # per-tick — better than crashing the loop.
        pass

    if drift >= drift_threshold:
        lines.append(
            f"[RED-FLAG] parser drift — {drift} consecutive ticks with no "
            f"recognizable Stryker output pattern; reporter format may have "
            f"changed — see #558"
        )

    return lines


# =============================================================================
# status_loop_start — the tick loop
# =============================================================================
_STOP = {"requested": False}


def _stop_handler(signum: int, _frame) -> None:
    _STOP["requested"] = True


def status_loop_start(
    logfile: Path,
    interval: float,
    threshold: int,
    stryker_pid: Optional[int],
    *,
    expected_target: Optional[str] = None,
    state_dir: Optional[Path] = None,
    drift_threshold: int = 3,
    output=sys.stdout,
) -> None:
    """Tick loop. Prints one status line + zero-or-more red-flag lines per
    tick. Exits cleanly when Stryker has completed (PID dead AND completion
    marker present) or when SIGTERM/SIGINT is received.

    ``output`` defaults to ``sys.stdout`` but can be overridden for tests.
    """
    # Install signal handlers so the loop reaps on Ctrl-C / kill.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop_handler)
        except (ValueError, OSError):
            # Called from a thread on some platforms — non-main-thread
            # signal.signal raises ValueError. That's OK; the loop still
            # terminates via the completion-marker check.
            pass

    while not _STOP["requested"]:
        print(emit_status_line(logfile), file=output, flush=True)
        for line in check_red_flags(
            logfile,
            threshold,
            stryker_pid,
            expected_target=expected_target,
            state_dir=state_dir,
            drift_threshold=drift_threshold,
        ):
            print(line, file=output, flush=True)

        # Exit condition — Stryker done and log carries a completion marker.
        if stryker_pid is not None and not _pid_is_alive(stryker_pid):
            if log_has_completion_marker(logfile):
                break

        # Sleep in small slices so signal handlers wake up promptly.
        remaining = float(interval)
        slice_s = 0.1
        while remaining > 0 and not _STOP["requested"]:
            time.sleep(min(slice_s, remaining))
            remaining -= slice_s


# =============================================================================
# CLI entry point — for standalone use
# =============================================================================
def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="csharp_stryker_net_status_loop.py",
        description=(
            "Status + red-flag inspection loop for long-running Stryker.NET "
            "invocations. Usable standalone; typically called by "
            "csharp_stryker_net_wrapper.py."
        ),
    )
    p.add_argument(
        "logfile", type=Path, help="Path to the Stryker log file being tailed"
    )
    p.add_argument(
        "interval",
        type=float,
        help="Seconds between status ticks (0 = one tick and exit)",
    )
    p.add_argument(
        "threshold", type=int, help="CompileError count above which the red-flag fires"
    )
    p.add_argument(
        "stryker_pid",
        type=int,
        nargs="?",
        default=None,
        help="PID of the Stryker subprocess to monitor (optional)",
    )
    p.add_argument(
        "--expected-target",
        default=None,
        help="Fragment expected in Property TargetPath=... lines",
    )
    p.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for drift-counter state (default: $TMPDIR)",
    )
    p.add_argument(
        "--drift-threshold",
        type=int,
        default=3,
        help="Consecutive unrecognized ticks before drift red-flag",
    )
    args = p.parse_args(argv)

    if args.interval <= 0:
        # One-shot mode — emit one status + red-flag pass and exit.
        print(emit_status_line(args.logfile), flush=True)
        for line in check_red_flags(
            args.logfile,
            args.threshold,
            args.stryker_pid,
            expected_target=args.expected_target,
            state_dir=args.state_dir,
            drift_threshold=args.drift_threshold,
        ):
            print(line, flush=True)
        return 0

    status_loop_start(
        args.logfile,
        args.interval,
        args.threshold,
        args.stryker_pid,
        expected_target=args.expected_target,
        state_dir=args.state_dir,
        drift_threshold=args.drift_threshold,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
