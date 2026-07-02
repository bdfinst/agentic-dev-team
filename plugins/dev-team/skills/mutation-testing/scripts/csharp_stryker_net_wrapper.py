#!/usr/bin/env python3
"""csharp_stryker_net_wrapper.py — reference wrapper for Stryker.NET.

Cross-platform authoritative: macOS, Linux, Windows Git Bash, and native
Windows all execute the same code path through Python 3's ``subprocess``,
``signal``, and ``pathlib``. Sole runtime dependency is ``python3`` (≥ 3.8)
on PATH — no shell-tooling divergence.

Copy this file AND ``csharp_stryker_net_status_loop.py`` together into your
repo's ``scripts/`` directory, and run in place of a bare ``dotnet stryker``
invocation (override defaults via CLI flags or the corresponding env vars).

Contract preserved from the bash version:

- ``DOTNET_ROOT`` probe across macOS Homebrew (Apple Silicon + Intel),
  Debian/Ubuntu, Fedora/RHEL, user-scope, and Windows install paths
- Pre-building ``${SLN}`` and ``${SHIM_PROJECT}`` BEFORE hiding ``.sln``
  (Stryker's own build step can't rebuild whole-solution after the hide)
- Hiding ``.sln`` during the run + restoring it on any exit path — normal
  exit, non-zero exit, SIGINT (Ctrl-C), SIGTERM, KeyboardInterrupt
- Refusing (exit 2) when a stale ``.sln.stryker-hidden`` coexists with a
  fresh ``.sln`` (idempotent — never silently clobbers either)
- Running Stryker as a subprocess so we can kill it on any signal — no
  orphaned Stryker processes in CI or backgrounded contexts
- Direct log redirect (never a bare ``| tee`` — see #550)

Refs: #554, #557, #558, #559, #564, #567 (Windows verification), #572
(bash → Python migration epic).
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


# =============================================================================
# Exit codes — same as the bash version, byte-compatible.
# =============================================================================
EXIT_OK = 0
EXIT_STALE_HIDDEN_SLN = 2
EXIT_NO_DOTNET_SDK = 3


# =============================================================================
# DOTNET_ROOT probe — the 7-position chain documented in the spec.
# =============================================================================
def default_probe_candidates() -> list[str]:
    """Return the ordered default probe list. Named function so callers (and
    tests) can point at a single authoritative source instead of copying the
    literal path list.
    """
    home = str(Path.home())
    return [
        "/opt/homebrew/opt/dotnet/libexec",  # 1: macOS Apple Silicon Homebrew
        "/usr/local/opt/dotnet/libexec",  # 2: macOS Intel Homebrew
        "/usr/share/dotnet",  # 3: Debian/Ubuntu package
        "/usr/lib/dotnet",  # 4: Fedora/RHEL package
        f"{home}/.dotnet",  # 5: user-scope (dotnet-install.sh)
        "/c/Program Files/dotnet",  # 6: Windows Git Bash Program Files
        "/c/program files/dotnet",  # 7: Windows lowercase drive mount
        # Native-Windows path (drive letter, no MSYS mount). Sensible extension
        # of the bash contract on the native-Windows target.
        r"C:\Program Files\dotnet",
    ]


def probe_dotnet_root(candidates: Sequence[str]) -> Optional[str]:
    """Return the first candidate whose SDK layout is present, or None.

    A candidate hits when any of these are true:
      - ``<c>/dotnet`` is an executable file
      - ``<c>/dotnet.exe`` is an executable file
      - ``<c>/shared`` is a directory

    Empty candidate strings are skipped so callers can concatenate lists
    without worrying about stray separators.
    """
    for candidate in candidates:
        if not candidate:
            continue
        c = Path(candidate)
        dotnet_bin = c / "dotnet"
        dotnet_exe = c / "dotnet.exe"
        shared_dir = c / "shared"
        if (
            (dotnet_bin.is_file() and os.access(dotnet_bin, os.X_OK))
            or (dotnet_exe.is_file() and os.access(dotnet_exe, os.X_OK))
            or shared_dir.is_dir()
        ):
            return str(c)
    return None


def resolve_dotnet_root(
    preset: Optional[str],
    candidates: Sequence[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(dotnet_root, error_message)``.

    - Preset value wins if truthy — matches the bash ``${DOTNET_ROOT:-}`` guard.
    - Probe the candidate list next.
    - Fall back to the directory containing ``dotnet`` on PATH.
    - Return (None, error_message) when nothing resolves.
    """
    if preset:
        return preset, None
    hit = probe_dotnet_root(candidates)
    if hit is not None:
        return hit, None
    on_path = shutil.which("dotnet")
    if on_path:
        return str(Path(on_path).resolve().parent), None
    msg = _no_sdk_message(candidates)
    return None, msg


def _no_sdk_message(candidates: Sequence[str]) -> str:
    lines = [
        "error: no .NET SDK found; DOTNET_ROOT is unset and no candidate resolved",
        "  probed:",
    ]
    for c in candidates:
        if c:
            lines.append(f"    {c}")
    lines.append("  also tried: dirname of `dotnet` on PATH — dotnet not on PATH")
    lines.append(
        "set DOTNET_ROOT explicitly, or install .NET: https://dotnet.microsoft.com/download"
    )
    return "\n".join(lines) + "\n"


# =============================================================================
# Stale-hidden-.sln refusal
# =============================================================================
def check_stale_hidden_sln(sln: Path, sln_hidden: Path) -> Optional[str]:
    """Return an error message if a stale hidden .sln coexists with a fresh
    one; otherwise None. Refusal is deterministic — the wrapper produces no
    side effects when it refuses.
    """
    if sln_hidden.exists() and sln.exists():
        return (
            f"error: stale {sln_hidden} present alongside fresh {sln}\n"
            f"resolve manually before rerunning "
            f"(delete the stale hidden file if the fresh {sln} is correct)\n"
        )
    return None


# =============================================================================
# .sln hide/restore — used inside a try/finally so restore runs on any exit.
# =============================================================================
def hide_sln(sln: Path, sln_hidden: Path) -> None:
    """Move .sln to .sln.stryker-hidden. Idempotent — a no-op if already hidden."""
    if sln.exists() and not sln_hidden.exists():
        sln.rename(sln_hidden)


def restore_sln(sln: Path, sln_hidden: Path) -> None:
    """Restore .sln from .sln.stryker-hidden. Guarded so we never clobber a
    fresh .sln written mid-run (rare but real — some IDEs rewrite the file).
    """
    if sln_hidden.exists() and not sln.exists():
        sln_hidden.rename(sln)


# =============================================================================
# Main
# =============================================================================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse header-var overrides and pass-through Stryker args.

    Everything after ``--`` (or unknown flags) is forwarded verbatim to
    ``dotnet stryker``. Header vars can be set via env or CLI flag; CLI wins.
    """
    p = argparse.ArgumentParser(
        prog="csharp_stryker_net_wrapper.py",
        description="Reference wrapper for Stryker.NET — cross-platform via Python.",
        add_help=True,
    )
    p.add_argument(
        "--sln",
        default=os.environ.get("SLN", "Foo.sln"),
        help="Solution file to hide during run (default: %(default)s)",
    )
    p.add_argument(
        "--shim-project",
        default=os.environ.get("SHIM_PROJECT", ""),
        help="Optional shim test project to pre-build. Empty = none.",
    )
    p.add_argument(
        "--stryker-bin",
        default=os.environ.get("STRYKER_BIN", "dotnet-stryker"),
        help="Stryker executable name (default: %(default)s)",
    )
    p.add_argument(
        "--logfile",
        default=os.environ.get("LOGFILE", "StrykerOutput/wrapper.log"),
        help="Log redirect target (default: %(default)s)",
    )
    p.add_argument(
        "--stryker-concurrency",
        default=os.environ.get("STRYKER_MUTANT_CONCURRENCY"),
        help=(
            "Stryker's own mutant-testing-process concurrency (its -c/"
            "--concurrency flag). Deliberately NOT -c/--concurrency here — "
            "see csharp-stryker-net.md. Env equivalent: "
            "STRYKER_MUTANT_CONCURRENCY. Default: max(1, cpu_count - 2)."
        ),
    )
    return p.parse_known_args(list(argv))[0], p.parse_known_args(list(argv))[1]


# =============================================================================
# Concurrency default — Stryker's own `-c`/`--concurrency` mutant-testing-
# process count. Defaults to cores-2 instead of Stryker's flat default of 5.
# =============================================================================
def default_concurrency(cpu_count: Optional[int]) -> int:
    """Return ``max(1, (cpu_count or 2) - 2)``.

    ``cpu_count`` is normally ``os.cpu_count()``, which returns ``None`` when
    the machine's core count can't be determined — falls back to 2 so the
    computed default is still 1 (never 0 or negative).
    """
    return max(1, (cpu_count or 2) - 2)


def _pass_through_concurrency_flag(stryker_args: Sequence[str]) -> Optional[str]:
    """Return the pass-through concurrency flag (``-c`` or ``--concurrency``)
    present in ``stryker_args``, or ``None``. Consolidates the "does the
    caller already specify concurrency" check used by both the explicit-
    value and computed-default injection paths.
    """
    for flag in ("-c", "--concurrency"):
        if flag in stryker_args:
            return flag
    return None


def build_project(project: str, cwd: Optional[Path] = None) -> int:
    """Run ``dotnet build <project> -c Debug --nologo`` in the given cwd.
    Returns the subprocess exit code.
    """
    return subprocess.call(
        ["dotnet", "build", project, "-c", "Debug", "--nologo"],
        cwd=cwd,
    )


def run_stryker(stryker_bin: str, stryker_args: Sequence[str], logfile: Path) -> int:
    """Run Stryker with stdout+stderr redirected to logfile. Returns exit code.

    Signal handling: Python's default SIGINT delivery raises KeyboardInterrupt
    in the parent, which our main() catches to run the finally block. The
    Popen child inherits the process group by default — a tty Ctrl-C reaches
    both. On explicit `signal` from a parent process manager, main()'s signal
    handlers intercept and terminate the child before re-raising.
    """
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("wb") as log:
        proc = subprocess.Popen(
            [stryker_bin, *stryker_args],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        # Track for signal handlers.
        _RUNNING_STRYKER["proc"] = proc
        try:
            return proc.wait()
        finally:
            _RUNNING_STRYKER["proc"] = None


_RUNNING_STRYKER: dict[str, Optional[subprocess.Popen]] = {"proc": None}


def _install_signal_handlers() -> list[tuple[int, object]]:
    """Install SIGINT + SIGTERM handlers that terminate any running Stryker
    subprocess before re-raising KeyboardInterrupt / exiting. On Windows,
    SIGTERM is delivered as SIGBREAK — signal.signal accepts SIGTERM but
    doesn't actually receive it; we register SIGBREAK too where available.

    Returns a list of (signum, previous_handler) tuples so ``main()`` can
    restore the process's prior handlers on exit. This matters when
    ``main()`` is called from another Python program (e.g. pytest) that
    itself installs signal handlers — leaving ours in place across the
    caller's remaining lifetime causes KeyboardInterrupt storms on
    unrelated later code.
    """

    def _handler(signum: int, _frame) -> None:
        proc = _RUNNING_STRYKER.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        # Re-raise as KeyboardInterrupt for main()'s finally to fire cleanly.
        raise KeyboardInterrupt(f"signal {signum}")

    previous: list[tuple[int, object]] = []
    signals_to_install = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        signals_to_install.append(signal.SIGTERM)
    if hasattr(signal, "SIGBREAK"):
        # Windows console Ctrl-Break.
        signals_to_install.append(signal.SIGBREAK)
    for sig in signals_to_install:
        previous.append((sig, signal.getsignal(sig)))
        signal.signal(sig, _handler)
    return previous


def _restore_signal_handlers(previous: list[tuple[int, object]]) -> None:
    """Restore the signal handlers captured by _install_signal_handlers."""
    for sig, handler in previous:
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, TypeError):
            # Non-main-thread invocation or platform quirk — leave whatever
            # is now in place; better than crashing at cleanup time.
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point. Returns the process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args, stryker_args = parse_args(argv)

    # ---- DOTNET_ROOT resolution ---------------------------------------------
    dotnet_root, err = resolve_dotnet_root(
        preset=os.environ.get("DOTNET_ROOT"),
        candidates=default_probe_candidates(),
    )
    if err is not None:
        sys.stderr.write(err)
        return EXIT_NO_DOTNET_SDK
    assert dotnet_root is not None
    os.environ["DOTNET_ROOT"] = dotnet_root

    # ---- Stale-hidden refusal (BEFORE any state mutation) -------------------
    sln = Path(args.sln)
    sln_hidden = Path(f"{args.sln}.stryker-hidden")
    stale_err = check_stale_hidden_sln(sln, sln_hidden)
    if stale_err is not None:
        sys.stderr.write(stale_err)
        return EXIT_STALE_HIDDEN_SLN

    # ---- Install signal handlers now that we're about to spawn children ----
    # Save previous handlers so we restore them on exit. Critical when main()
    # is called from another Python program (pytest) — leaving our handlers
    # in place across the caller's lifetime causes KeyboardInterrupt storms
    # on unrelated later code.
    previous_signal_handlers = _install_signal_handlers()

    exit_code: int = EXIT_OK
    try:
        # Pre-build BEFORE hiding — build against a hidden .sln fails.
        rc = build_project(args.sln)
        if rc != 0:
            return rc
        if args.shim_project:
            rc = build_project(args.shim_project)
            if rc != 0:
                return rc

        # Hide .sln during the run.
        hide_sln(sln, sln_hidden)

        # Inject Stryker's own mutant-testing concurrency (`-c`) unless the
        # caller's pass-through args already specify one — pass-through
        # always wins over both an explicit --stryker-concurrency/env value
        # and the computed default; never silently override an explicit
        # caller-supplied value.
        pass_through_flag = _pass_through_concurrency_flag(stryker_args)
        if pass_through_flag is None:
            if args.stryker_concurrency is not None:
                value = str(args.stryker_concurrency)
            else:
                value = str(default_concurrency(os.cpu_count()))
            stryker_args = [*stryker_args, "-c", value]
        elif args.stryker_concurrency is not None:
            idx = stryker_args.index(pass_through_flag)
            pass_through_value = (
                stryker_args[idx + 1] if idx + 1 < len(stryker_args) else ""
            )
            sys.stderr.write(
                f'note: pass-through "{pass_through_flag} '
                f'{pass_through_value}" overrode explicit '
                f'"--stryker-concurrency {args.stryker_concurrency}"\n'
            )

        # Run Stryker; capture its exit code.
        exit_code = run_stryker(
            stryker_bin=args.stryker_bin,
            stryker_args=stryker_args,
            logfile=Path(args.logfile),
        )
    except KeyboardInterrupt:
        # SIGINT / SIGTERM propagated through the signal handlers. The Popen
        # child was terminate()'d already; we now fall through to the finally
        # block for .sln restoration.
        exit_code = 130  # conventional SIGINT exit code
    finally:
        # ALWAYS restore .sln — no matter which exit path.
        restore_sln(sln, sln_hidden)
        # Restore previous signal handlers — critical for library-style use.
        _restore_signal_handlers(previous_signal_handlers)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
