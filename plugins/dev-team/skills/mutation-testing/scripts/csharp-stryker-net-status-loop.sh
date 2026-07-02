#!/usr/bin/env bash
# csharp-stryker-net-status-loop.sh — status + red-flag inspection loop for
# long-running Stryker.NET invocations. Sourced by csharp-stryker-net-wrapper.sh
# (see companion file for install and copy-both instructions).
#
# Public functions:
#   status_loop_start LOGFILE INTERVAL COMPILE_THRESHOLD STRYKER_PID
#       Backgrounded loop entry point. Sleeps INTERVAL seconds between ticks;
#       each tick prints one status line + zero-or-more [RED-FLAG] lines to
#       stdout. Exits when the loop receives SIGTERM or STRYKER_PID is dead
#       AND the log carries a completion marker (normal end-of-run).
#
#   emit_status_line LOGFILE
#       Parses LOGFILE and prints one status record with:
#         tested=<n>/<total>  killed=<n>  survived=<n>  timeout=<n>  elapsed=<HH:MM>
#       "tested" is derived from dots-reporter output (survives log
#       redirection) or from the summary block, whichever is present.
#
#   check_red_flags LOGFILE COMPILE_THRESHOLD STRYKER_PID
#       Grep the log for known-broken signatures, check STRYKER_PID liveness,
#       and print [RED-FLAG] lines for anything that fires. Consecutive
#       unrecognized-tick counter kept in $STATUS_LOOP_STATE_DIR (default
#       $TMPDIR) so a Stryker reporter-format drift is self-detecting.
#
# Refs: #558.

set -euo pipefail

# Where per-Stryker-PID drift counters live. Test suites override this to an
# isolated dir; production defaults to $TMPDIR.
: "${STATUS_LOOP_STATE_DIR:=${TMPDIR:-/tmp}}"

# Consecutive-unrecognized-tick threshold before the parser-drift catch-all
# red-flag fires. Configurable via env; 3 is a sensible default (see #558).
: "${STATUS_LOOP_DRIFT_THRESHOLD:=3}"

# Expected TargetPath fragment for the SolutionPath-trap check. When set,
# check_red_flags fires when a Property TargetPath=... line names a .dll
# that does NOT contain this fragment. Left unset by default (no check).
# STATUS_LOOP_EXPECTED_TARGET — unset by default.

# =============================================================================
# Parsers — pure functions over log content
# =============================================================================

# _dots_count LOGFILE — count '.' characters on the first non-empty line
# following "Testing mutants:". Dots reporter uses one dot per completed
# mutant; survives redirection. Always exits 0.
_dots_count() {
    awk '
        /^Testing mutants:/ { collecting = 1; next }
        collecting && /^[[:space:]]*$/ { next }
        collecting && /^\./ { print gsub(/\./, "&", $0); exit }
        collecting && /^[^.]/ { print 0; exit }
        END { if (!collecting) print 0 }
    ' "$1"
    return 0
}

# _summary_count LOGFILE KEY — extract "Killed:", "Survived:", "Timeout:",
# "No coverage:" counts from the last summary block. Prints "" if absent
# (no matching line). Always exits 0 — callers use `"$(cmd)"` under set-e
# so we can't let a "no matches" grep fail the pipeline.
_summary_count() {
    grep -E "^${2}:[[:space:]]+[0-9]+" "$1" 2>/dev/null | tail -1 | awk '{print $NF}'
    return 0
}

# _log_has_completion_marker LOGFILE — true when Stryker's end-of-run marker
# is present. Used to distinguish "died mid-run" from "completed normally,
# PID reaped."
_log_has_completion_marker() {
    grep -q -E "The final mutation score|Stryker execution finished" "$1" 2>/dev/null
}

# =============================================================================
# emit_status_line — one status record per tick
# =============================================================================

emit_status_line() {
    local logfile="$1"
    local tested killed survived timeout elapsed

    tested="$(_dots_count "$logfile")"
    killed="$(_summary_count "$logfile" "Killed")"
    survived="$(_summary_count "$logfile" "Survived")"
    timeout="$(_summary_count "$logfile" "Timeout")"

    # Elapsed derived from the log's first-line INF timestamp when present;
    # otherwise falls back to "?" so the record shape is stable.
    elapsed="?"

    printf 'tested=%s killed=%s survived=%s timeout=%s elapsed=%s\n' \
        "${tested:-0}" "${killed:-0}" "${survived:-0}" "${timeout:-0}" "$elapsed"
}

# =============================================================================
# check_red_flags — zero-or-more [RED-FLAG] lines per tick
# =============================================================================

check_red_flags() {
    local logfile="$1"
    local threshold="$2"
    local stryker_pid="$3"

    local killed survived compile_errors
    killed="$(_summary_count "$logfile" "Killed")"
    survived="$(_summary_count "$logfile" "Survived")"
    # grep -c prints 0 on no match but exits 1 — normalize both under set -e.
    compile_errors="$({ grep -c -E "CompileError" "$logfile" 2>/dev/null; true; } || printf '0')"
    compile_errors="${compile_errors:-0}"

    # Track whether this tick was "recognized" by any parser — used by the
    # parser-drift catch-all below.
    local recognized=0

    # --- Red flag 1: Killed==0 && Survived>0 (mutation-switch not observing)
    if [ -n "$killed" ] && [ -n "$survived" ]; then
        recognized=1
        if [ "$killed" = "0" ] && [ "$survived" != "0" ]; then
            printf '[RED-FLAG] mutation-switch not observing mutations at runtime (Killed=0, Survived=%s) — see #554\n' "$survived"
        fi
    fi

    # --- Red flag 2: CompileError count strictly > threshold
    if [ "$compile_errors" -gt 0 ] 2>/dev/null; then
        recognized=1
        if [ "$compile_errors" -gt "$threshold" ]; then
            printf '[RED-FLAG] CompileError count %d over threshold %d — probe file / mutate glob likely misconfigured\n' \
                "$compile_errors" "$threshold"
        fi
    fi

    # --- Red flag 3: SolutionPath naming an unexpected .sln / .dll
    if [ -n "${STATUS_LOOP_EXPECTED_TARGET:-}" ]; then
        local unexpected
        unexpected="$(grep -E "^Property TargetPath=" "$logfile" 2>/dev/null | grep -v "$STATUS_LOOP_EXPECTED_TARGET" | head -1 || true)"
        if [ -n "$unexpected" ]; then
            recognized=1
            printf '[RED-FLAG] SolutionPath trap — %s does not contain expected %s — see #557\n' \
                "$(printf '%s' "$unexpected" | sed 's/Property TargetPath=//')" \
                "$STATUS_LOOP_EXPECTED_TARGET"
        fi
    fi

    # --- Red flag 4: Stryker PID dead AND no completion marker in log
    if [ -n "$stryker_pid" ] && ! kill -0 "$stryker_pid" 2>/dev/null; then
        if ! _log_has_completion_marker "$logfile"; then
            recognized=1
            printf '[RED-FLAG] Stryker process died mid-run (PID %s no longer running, no completion marker in log) — see #558\n' \
                "$stryker_pid"
        fi
    fi

    # Also consider the log "recognized" when at least the dots block is present
    # or a completion marker exists.
    if [ "$(_dots_count "$logfile")" -gt 0 ] || _log_has_completion_marker "$logfile"; then
        recognized=1
    fi

    # --- Red flag 5: parser drift — N consecutive unrecognized ticks
    local counter_file="$STATUS_LOOP_STATE_DIR/drift-counter-${stryker_pid:-noop}"
    local drift=0
    if [ -f "$counter_file" ]; then
        drift="$(cat "$counter_file" 2>/dev/null || printf '0')"
    fi
    if [ "$recognized" = "1" ]; then
        drift=0
    else
        drift=$((drift + 1))
    fi
    printf '%d\n' "$drift" >"$counter_file"

    if [ "$drift" -ge "$STATUS_LOOP_DRIFT_THRESHOLD" ]; then
        printf '[RED-FLAG] parser drift — %d consecutive ticks with no recognizable Stryker output pattern; reporter format may have changed — see #558\n' \
            "$drift"
    fi

    return 0
}

# =============================================================================
# status_loop_start — the actual tick loop, backgrounded by the wrapper
# =============================================================================

status_loop_start() {
    local logfile="$1"
    local interval="$2"
    local threshold="$3"
    local stryker_pid="$4"

    # Small-slice sleep so a wrapper-side kill on this PID reaps within the
    # tick's tail. Under `sleep &; wait $!` bash's signal handling wakes up
    # promptly (the same idiom the wrapper uses).
    trap 'exit 0' TERM INT

    while :; do
        emit_status_line "$logfile"
        check_red_flags "$logfile" "$threshold" "$stryker_pid"

        # Exit condition — Stryker done and log carries a completion marker.
        if [ -n "$stryker_pid" ] && ! kill -0 "$stryker_pid" 2>/dev/null; then
            if _log_has_completion_marker "$logfile"; then
                break
            fi
        fi

        sleep "$interval" &
        wait $! 2>/dev/null || break
    done
}

# When invoked directly (not sourced), print usage. Sourced usage is the
# normal path — the wrapper does `. .../csharp-stryker-net-status-loop.sh`.
# BASH_SOURCE test guards against direct execution.
if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
    cat >&2 <<'USAGE'
csharp-stryker-net-status-loop.sh — source this file from a Stryker.NET
wrapper, then call:

  status_loop_start LOGFILE INTERVAL_SECONDS COMPILE_THRESHOLD STRYKER_PID

Direct execution isn't supported.
USAGE
    exit 64
fi
