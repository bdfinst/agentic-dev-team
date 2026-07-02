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
# Whole-scope run detected — check the smoke report.
# =============================================================================

# print_block_message <specific-diagnostic-line>
# Writes the shared block-message body with the caller's specific diagnostic
# inserted. Every block path funnels through this function so the example
# command, escape-hatch hint, and Step 1c reference are consistent.
print_block_message() {
    local diagnostic="$1"
    cat <<EOF
[BLOCK] mutation-testing-smoke-gate: whole-scope Stryker.NET run detected

$diagnostic

The Step 1c smoke gate (see SKILL.md § Step 1c) requires a single-file
mutation probe with Killed > 0 before authorizing a full run. This
prevents the silent 0.00 % failure mode (see #554, #557).

To run the smoke probe:

  dotnet stryker --config-file stryker-config.json \\
    --mutate 'path/to/one/covered/file.cs' \\
    -O StrykerOutput/smoke

Then re-run this command. To bypass this gate for a legitimate exception,
set MUTATION_SMOKE_GATE_SKIP=1 in the environment (audit-logged).
EOF
}

REPORT_PATH="$PAYLOAD_CWD/StrykerOutput/smoke/reports/mutation-report.json"

# Missing report — nothing to parse; block with the missing-path diagnostic.
if [ ! -f "$REPORT_PATH" ]; then
    print_block_message "no smoke report at $REPORT_PATH"
    exit 2
fi

# Count mutants by status against the mutation-testing-elements schema.
# .mutants[]? tolerates a missing key without erroring; the schema-drift
# advisory (Step 1.3) handles that case explicitly.
KILLED="$(jq -r '[.mutants[]? | select(.status=="Killed")] | length' "$REPORT_PATH" 2>/dev/null || echo 0)"
SURVIVED="$(jq -r '[.mutants[]? | select(.status=="Survived")] | length' "$REPORT_PATH" 2>/dev/null || echo 0)"

# At least one Killed → gate passes silently.
if [ "$KILLED" -gt 0 ]; then
    exit 0
fi

# Killed==0 && Survived>0 → mutation-switch not observing mutations (#554/#557).
if [ "$SURVIVED" -gt 0 ]; then
    print_block_message "killed=0 survived=$SURVIVED — mutation-switch not observing mutations at runtime (see #554, #557 and SKILL.md Step 1c diagnostic checklist)"
    exit 2
fi

# Killed==0 && Survived==0 → empty mutants[] or only NoCoverage/CompileError.
print_block_message "no scored mutants in smoke report — pick a different probe file with real test coverage"
exit 2
