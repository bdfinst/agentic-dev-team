#!/usr/bin/env bash
# csharp-stryker-net-wrapper.sh — reference wrapper for Stryker.NET.
#
# DOTNET_ROOT resolution: cross-platform (macOS, Linux, Windows Git Bash).
# The wrapper probes each platform's standard .NET install paths and falls
# back to $(dirname "$(command -v dotnet)") on PATH before failing with an
# actionable error message (exit 3).
#
# Process/signal cleanup (SIGINT/SIGTERM handling, backgrounded-child
# reaping): verified on macOS + Linux; Windows Git Bash job-control and
# signal semantics diverge from POSIX and are NOT yet verified here — see
# https://github.com/bdfinst/agentic-dev-team/issues/567 for the
# tracking issue.
#
# Copy this file AND csharp-stryker-net-status-loop.sh together into your
# repo's `scripts/` directory, edit the header vars below, and run it in
# place of a bare `dotnet stryker` invocation.
#
# What it owns:
#   - DOTNET_ROOT probe across macOS Homebrew (Apple Silicon + Intel),
#     Debian/Ubuntu, Fedora/RHEL, user-scope, and Windows Git Bash paths
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
# Refs: #554, #557, #558, #559, #564.

set -euo pipefail

# =============================================================================
# DOTNET_ROOT probe — sourceable function (issue #564)
# =============================================================================
#
# Iterates the argument list of candidate directories and prints the first
# one whose SDK layout is present (executable `dotnet`, executable `dotnet.exe`,
# or `shared/` directory). Returns 0 on hit, 1 when no candidate resolves.
#
# Empty candidate arguments are skipped so callers can concatenate lists
# without worrying about stray separators.
_probe_dotnet_root() {
    local candidate
    for candidate in "$@"; do
        [ -z "$candidate" ] && continue
        if [ -x "$candidate/dotnet" ] \
            || [ -x "$candidate/dotnet.exe" ] \
            || [ -d "$candidate/shared" ]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

# Sourced-vs-executed guard: when this file is sourced (e.g. from a bats
# test) BASH_SOURCE[0] is the file path but $0 is the sourcing shell's $0
# (bats-exec-test on the tests side). When executed directly they are
# equal. Sourced case: expose _probe_dotnet_root and return without
# running the main flow.
if [ "${BASH_SOURCE[0]:-}" != "${0:-}" ]; then
    return 0
fi

# ---- Per-repo edits (header vars) ------------------------------------------
SLN="${SLN:-Foo.sln}"                                # Solution file to hide during run
SHIM_PROJECT="${SHIM_PROJECT:-}"                     # Optional shim test project to pre-build (empty = none)
STRYKER_BIN="${STRYKER_BIN:-dotnet-stryker}"         # Stryker executable name
LOGFILE="${LOGFILE:-StrykerOutput/wrapper.log}"      # Redirect target
STATUS_INTERVAL="${STATUS_INTERVAL:-600}"            # Seconds between status ticks; 0 disables the loop
COMPILE_ERROR_THRESHOLD="${COMPILE_ERROR_THRESHOLD:-25}"   # CompileError count over threshold trips red-flag
# ---------------------------------------------------------------------------

# Default probe candidates — the 7-position chain documented in
# docs/specs/csharp-stryker-net-wrapper-cross-platform.md. PATH fallback is
# a separate code path (see below) and is NOT counted in this list. Hoisted
# to a named array so the ordering is a first-class identifier the code and
# lint tests reference. Bash 3.2-safe (indexed arrays are supported).
_default_probe_candidates=(
    "/opt/homebrew/opt/dotnet/libexec"     # position 1: macOS Apple Silicon Homebrew
    "/usr/local/opt/dotnet/libexec"        # position 2: macOS Intel Homebrew
    "/usr/share/dotnet"                    # position 3: Debian/Ubuntu package
    "/usr/lib/dotnet"                      # position 4: Fedora/RHEL package
    "${HOME}/.dotnet"                      # position 5: user-scope (dotnet-install.sh)
    "/c/Program Files/dotnet"              # position 6: Windows Git Bash Program Files
    "/c/program files/dotnet"              # position 7: Windows Git Bash lowercase drive mount
)

if [ -z "${DOTNET_ROOT:-}" ]; then
    # Empty-safe array expansion (per CLAUDE.md bash 3.2 guidance).
    if resolved="$(_probe_dotnet_root "${_default_probe_candidates[@]+"${_default_probe_candidates[@]}"}")"; then
        DOTNET_ROOT="$resolved"
    elif command -v dotnet >/dev/null 2>&1; then
        DOTNET_ROOT="$(dirname "$(command -v dotnet)")"
    else
        {
            printf 'error: no .NET SDK found; DOTNET_ROOT is unset and no candidate resolved\n'
            printf '  probed: /opt/homebrew/opt/dotnet/libexec, /usr/local/opt/dotnet/libexec,\n'
            printf '          /usr/share/dotnet, /usr/lib/dotnet, %s/.dotnet,\n' "${HOME}"
            printf '          /c/Program Files/dotnet, /c/program files/dotnet\n'
            # shellcheck disable=SC2016  # literal $(command -v dotnet) in message text, not an expansion
            printf '  also tried: dirname $(command -v dotnet) — dotnet not on PATH\n'
            printf 'set DOTNET_ROOT explicitly, or install .NET: https://dotnet.microsoft.com/download\n'
        } >&2
        exit 3
    fi
fi
export DOTNET_ROOT

SLN_HIDDEN="${SLN}.stryker-hidden"
STATUS_PID=""
STRYKER_PID=""

restore_sln() {
    # Restore .sln only when it's currently hidden and no fresh .sln exists
    # at the target path — avoids clobbering a fresh .sln written mid-run.
    if [ -f "$SLN_HIDDEN" ] && [ ! -f "$SLN" ]; then
        mv "$SLN_HIDDEN" "$SLN"
    fi
    # Kill children — order: status loop (spawned by us), then Stryker (backgrounded).
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
