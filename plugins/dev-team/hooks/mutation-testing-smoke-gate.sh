#!/usr/bin/env bash
# mutation-testing-smoke-gate.sh — Claude Code PreToolUse hook (#565).
#
# Enforces SKILL.md § Step 1c smoke gate: blocks whole-scope Stryker.NET
# invocations until a single-file smoke probe has landed a
# mutation-report.json under StrykerOutput/smoke/reports/ with at least one
# Killed mutant. Prevents the silent 0.00 % failure mode caused by the
# mutation-switch not observing mutations at runtime (see #554, #557).
#
# Contract:
#   Input : PreToolUse JSON on stdin
#   Output: exit 2 + message on stdout to BLOCK
#           exit 0 + no stdout for SILENT-PASS
#           exit 0 + ADVISORY-prefixed stdout for missing-dep / malformed / drift
#   Env   : MUTATION_SMOKE_GATE_SKIP=1 → silent bypass + audit-log line
#
# Known limitations:
#   - Regex trigger detection can be defeated by exotic shell escaping
#     (heredocs, eval, dynamic arrays) — same class as destructive-guard.sh.
#   - Freshness of the smoke report is not checked in v1 (stale report
#     with Killed>0 continues to pass).
#
# Refs: #565 (this hook), #554, #557 (the failure modes it guards against).

set -uo pipefail

# =============================================================================
# Dependency guards — a missing dep must NOT become a de facto gate.
# Advisory + exit 0. Same pattern as mutation-gate.sh.
# =============================================================================

if ! command -v jq >/dev/null 2>&1; then
    printf 'ADVISORY: mutation-testing-smoke-gate: jq is required but not installed; gate not enforced\n'
    exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf 'ADVISORY: mutation-testing-smoke-gate: python3 is required but not installed; gate not enforced\n'
    exit 0
fi

# =============================================================================
# Parse PreToolUse payload
# =============================================================================

INPUT="$(cat)"
COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"

# Empty or missing command — nothing to check, silent-pass.
[ -n "$COMMAND" ] || exit 0

# Extract cwd from the payload; fall back to $PWD when absent.
# Both the smoke-report lookup and (Step 1.3) the audit-log path resolve
# against this single base so no split-cwd behavior emerges.
PAYLOAD_CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
: "${PAYLOAD_CWD:=$PWD}"

# =============================================================================
# Trigger detection
# =============================================================================

# Match "dotnet stryker" OR a path ending in csharp-stryker-net-wrapper.sh.
is_stryker_command() {
    printf '%s' "$1" | grep -qE '(^|[^a-zA-Z0-9])dotnet[[:space:]]+stryker(\b|$)|csharp-stryker-net-wrapper\.sh'
}

# Extract the --mutate value (handles --mutate=X, --mutate X, -m X).
# Prints the value to stdout or nothing if absent. Uses shlex to respect
# shell quoting so `--mutate 'src/Foo.cs'` and `--mutate "src/Foo.cs"` both
# yield the unquoted path.
extract_mutate_value() {
    printf '%s' "$1" | python3 -c '
import sys, shlex
try:
    tokens = shlex.split(sys.stdin.read())
except ValueError:
    sys.exit(0)
for i, t in enumerate(tokens):
    if t.startswith("--mutate="):
        print(t.split("=", 1)[1]); sys.exit(0)
    if t == "--mutate" or t == "-m":
        if i + 1 < len(tokens):
            print(tokens[i + 1]); sys.exit(0)
' 2>/dev/null || true
}

# A --mutate value counts as "single-file" only when it contains no glob
# metacharacters (*, ?, [) AND no semicolon (Stryker.NET's ';'-separated
# multi-file syntax counts as multi-file).
is_single_file_mutate() {
    case "$1" in
        "")            return 1 ;;
        *[\*\?\[]* )   return 1 ;;
        *";"*)         return 1 ;;
        *)             return 0 ;;
    esac
}

# Not a Stryker.NET invocation — silent-pass.
is_stryker_command "$COMMAND" || exit 0

# Single-file --mutate — this IS the smoke probe; do not block it.
MUTATE_VALUE="$(extract_mutate_value "$COMMAND")"
is_single_file_mutate "$MUTATE_VALUE" && exit 0

# =============================================================================
# Whole-scope run detected — Step 1.2 adds report-check + block logic here.
# Step 1.3 adds escape-hatch + advisory branches ahead of this fallthrough.
# =============================================================================

# TEMPORARY placeholder — remains until Step 1.2 GREEN wires in report checks.
# Silent-pass keeps Step 1.1's tests honest (they only assert silent-pass
# paths; the semicolon-block test lives in Step 1.2, alongside the report
# checks it needs to be meaningful).
exit 0
