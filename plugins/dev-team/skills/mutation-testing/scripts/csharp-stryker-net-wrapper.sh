#!/usr/bin/env bash
# csharp-stryker-net-wrapper.sh — reference wrapper for Stryker.NET on macOS/Linux.
#
# Copy this file AND csharp-stryker-net-status-loop.sh together into your
# repo's `scripts/` directory, edit the header vars below, and run it in
# place of a bare `dotnet stryker` invocation. Windows Git Bash is NOT a
# supported target (DOTNET_ROOT default is Homebrew-macOS specific).
#
# What it owns:
#   - DOTNET_ROOT export (Homebrew macOS defaults; respected if pre-set)
#   - Pre-building ${SLN} and ${SHIM_PROJECT} BEFORE hiding .sln (Stryker's
#     own build step can't rebuild whole-solution after the hide)
#   - Hiding .sln during the run + trap-restoring it on EXIT / INT / TERM
#     (prevents Stryker's SolutionPath auto-discovery from picking up
#     unintended test projects — see #557)
#   - Refusing (exit 2) when a stale .sln.stryker-hidden coexists with a
#     fresh .sln (idempotent — never silently clobbers either)
#   - Backgrounding Stryker so we can hand its PID to the status loop for
#     liveness checks; killing that PID (and the loop PID) on any signal
#     so a wrapper-level SIGINT/SIGTERM never orphans Stryker
#   - Direct `>"$LOGFILE" 2>&1` redirect — never a bare `| tee` (#550)
#
# What it does NOT own:
#   - Progress/red-flag detection (see csharp-stryker-net-status-loop.sh)
#   - Stryker's own config file (that stays in stryker-config.json)
#
# Refs: #554, #557, #558, #559.

set -euo pipefail

# ---- Per-repo edits (header vars) ------------------------------------------
SLN="${SLN:-Foo.sln}"                                # Solution file to hide during run
SHIM_PROJECT="${SHIM_PROJECT:-}"                     # Optional shim test project to pre-build (empty = none)
STRYKER_BIN="${STRYKER_BIN:-dotnet-stryker}"         # Stryker executable name
LOGFILE="${LOGFILE:-StrykerOutput/wrapper.log}"      # Redirect target
STATUS_INTERVAL="${STATUS_INTERVAL:-600}"            # Seconds between status ticks; 0 disables the loop
COMPILE_ERROR_THRESHOLD="${COMPILE_ERROR_THRESHOLD:-25}"   # CompileError count over threshold trips red-flag
# ---------------------------------------------------------------------------

export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"

SLN_HIDDEN="${SLN}.stryker-hidden"
STATUS_PID=""
STRYKER_PID=""

restore_sln() {
    # Restore .sln only when it's currently hidden and no fresh .sln exists
    # at the target path — avoids clobbering a fresh .sln written mid-run.
    if [ -f "$SLN_HIDDEN" ] && [ ! -f "$SLN" ]; then
        mv "$SLN_HIDDEN" "$SLN"
    fi
    # Kill children in reverse spawn order — status loop first, then Stryker.
    # SIGINT/SIGTERM on the wrapper doesn't propagate through `wait` to the
    # backgrounded Stryker automatically; we kill both explicitly.
    if [ -n "$STATUS_PID" ] && kill -0 "$STATUS_PID" 2>/dev/null; then
        kill "$STATUS_PID" 2>/dev/null || true
    fi
    if [ -n "$STRYKER_PID" ] && kill -0 "$STRYKER_PID" 2>/dev/null; then
        kill "$STRYKER_PID" 2>/dev/null || true
    fi
}
trap restore_sln EXIT INT TERM

# Refuse to clobber a fresh .sln with a stale hidden one. Happens BEFORE
# any build or hide operation — the wrapper produces no side effects when
# it refuses.
if [ -f "$SLN_HIDDEN" ] && [ -f "$SLN" ]; then
    printf 'error: stale %s present alongside fresh %s\n' "$SLN_HIDDEN" "$SLN" >&2
    printf 'resolve manually before rerunning (delete the stale hidden file if the fresh %s is correct)\n' "$SLN" >&2
    exit 2
fi

mkdir -p "$(dirname "$LOGFILE")"

# Pre-build BEFORE hiding — `dotnet build $SLN` against a hidden .sln fails.
dotnet build "$SLN" -c Debug --nologo
if [ -n "$SHIM_PROJECT" ]; then
    dotnet build "$SHIM_PROJECT" -c Debug --nologo
fi

mv "$SLN" "$SLN_HIDDEN"

# Background Stryker so its PID is available for the status loop. Direct
# redirect — do NOT pipe to tee (masks Stryker exit status; #550).
"$STRYKER_BIN" "$@" >"$LOGFILE" 2>&1 &
STRYKER_PID=$!

if [ "$STATUS_INTERVAL" -gt 0 ]; then
    # shellcheck disable=SC1091  # sibling file resolved via $BASH_SOURCE dirname
    . "$(dirname "${BASH_SOURCE[0]}")/csharp-stryker-net-status-loop.sh"
    status_loop_start "$LOGFILE" "$STATUS_INTERVAL" "$COMPILE_ERROR_THRESHOLD" "$STRYKER_PID" &
    STATUS_PID=$!
fi

# `wait` propagates Stryker's exit status through set -e. If we're killed
# by a signal, the trap fires and restore_sln kills the child anyway.
wait "$STRYKER_PID"
