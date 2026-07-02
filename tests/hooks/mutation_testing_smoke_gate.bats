#!/usr/bin/env bats
# Tests for mutation-testing-smoke-gate.sh — the PreToolUse hook that
# enforces SKILL.md Step 1c on whole-scope Stryker.NET invocations (#565).
#
# Fixture strategy: hermetic tempdir. _dispatch composes a PreToolUse JSON
# payload with .tool_input.command and .cwd, pipes to the hook, captures
# stdout, stderr, and exit code. Report fixtures follow the real
# mutation-testing-elements schema
# ({"schemaVersion":"1","mutants":[{"id":"…","status":"Killed"|…}]}).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/mutation-testing-smoke-gate.sh"

setup() {
  D="$(mktemp -d -t "smoke-gate-$$-XXXXXX")"
  mkdir -p "$D/StrykerOutput/smoke/reports"
  # Neutralize any escape-hatch env var possibly inherited from the outer
  # shell — every test opts in explicitly when it needs the bypass.
  unset MUTATION_SMOKE_GATE_SKIP
}

teardown() {
  # Restore perms in case a test chmod'd metrics/ to 000 and skipped early.
  [ -d "$D/metrics" ] && chmod 755 "$D/metrics" 2>/dev/null || true
  rm -rf "$D"
}

# --- helpers ----------------------------------------------------------------

# _payload <command> [<cwd-override>]
# Compose a PreToolUse JSON payload with the command and cwd fields.
# When <cwd-override> is unset, uses $D (the hermetic tempdir).
_payload() {
  local cmd="$1"
  local cwd="${2:-$D}"
  jq -c -n --arg c "$cmd" --arg cwd "$cwd" \
    '{hook_event_name: "PreToolUse", tool_name: "Bash", tool_input: {command: $c}, cwd: $cwd}'
}

# _payload_no_cwd <command>
# Payload with no .cwd field — exercises the $PWD fallback path.
_payload_no_cwd() {
  local cmd="$1"
  jq -c -n --arg c "$cmd" \
    '{hook_event_name: "PreToolUse", tool_name: "Bash", tool_input: {command: $c}}'
}

# _dispatch <payload>
# Pipe the payload to the hook and capture output+exit via `run`.
# Payloads may contain any character (single quotes, semicolons, glob chars),
# so route through a heredoc rather than command substitution.
_dispatch() {
  local pl="$1"
  run bash -c "bash '$HOOK'" <<<"$pl"
}

# _write_report_with_statuses <path> <status1> [<status2> ...]
# Write a report with one mutant per positional-arg status.
_write_report_with_statuses() {
  local out="$1"; shift
  mkdir -p "$(dirname "$out")"
  local statuses=()
  local i=0
  for s in "$@"; do
    i=$((i + 1))
    statuses+=("$(jq -c -n --arg id "$i" --arg st "$s" '{id: $id, mutatorName: "T", status: $st}')")
  done
  local joined
  joined="$(IFS=,; echo "${statuses[*]}")"
  printf '{"schemaVersion":"1","mutants":[%s]}\n' "$joined" >"$out"
}

# _write_report_raw <path> <literal-json>
_write_report_raw() {
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "$2" >"$1"
}

# =============================================================================
# Hook source hygiene
# =============================================================================

@test "hook: file exists and is executable" {
  [ -f "$HOOK" ]
  [ -x "$HOOK" ]
}

@test "hook: passes shellcheck" {
  if ! command -v shellcheck >/dev/null 2>&1; then
    skip "shellcheck not installed"
  fi
  run shellcheck "$HOOK"
  [ "$status" -eq 0 ]
}

# =============================================================================
# Step 1.1 — silent-pass paths on non-triggering commands
# =============================================================================

@test "hook: silent-pass on empty command" {
  _dispatch "$(_payload "")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on non-Stryker command" {
  _dispatch "$(_payload "git status")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on unrelated dotnet command" {
  _dispatch "$(_payload "dotnet build MyProject.sln")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on single-file --mutate glob (smoke probe itself)" {
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json --mutate 'src/Foo.cs' -O StrykerOutput/smoke")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on --mutate with double-quoted single file" {
  _dispatch "$(_payload 'dotnet stryker --mutate "src/Foo.cs"')"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on wrapper invocation with single-file --mutate" {
  _dispatch "$(_payload "./scripts/csharp-stryker-net-wrapper.sh --mutate 'src/Foo.cs' -O StrykerOutput/smoke")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# =============================================================================
# Step 1.2 — block paths + report parsing
# =============================================================================

@test "hook: block on semicolon-separated multi-file --mutate (Stryker.NET syntax)" {
  # #565 blocker: `--mutate 'src/Foo.cs;src/Bar.cs'` counts as multi-file
  # and triggers the gate. This scenario was called out by name in the spec
  # and MUST be locked in with a dedicated test.
  _dispatch "$(_payload "dotnet stryker --mutate 'src/Foo.cs;src/Bar.cs'")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q "smoke gate"
}

@test "hook: block on whole-scope run when no smoke report exists" {
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json --mutate '**/Validators/**/*.cs'")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q "StrykerOutput/smoke/reports/mutation-report.json"
}

@test "hook: block message on missing report includes the example smoke-probe command" {
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q -- "-O StrykerOutput/smoke"
  echo "$output" | grep -q -- "--mutate"
}

@test "hook: every block message names MUTATION_SMOKE_GATE_SKIP=1" {
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q "MUTATION_SMOKE_GATE_SKIP=1"
}

@test "hook: block when report contains only Survived statuses (Killed=0, Survived>0)" {
  _write_report_with_statuses "$D/StrykerOutput/smoke/reports/mutation-report.json" \
    Survived Survived Survived Survived Survived Survived Survived Survived Survived Survived
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 2 ]
  # Names observed counts.
  echo "$output" | grep -qE "killed=0"
  echo "$output" | grep -qE "survived=10"
  # References the failure-mode issues.
  echo "$output" | grep -q "#554"
  echo "$output" | grep -q "#557"
  # Points at SKILL.md Step 1c for the diagnostic checklist.
  echo "$output" | grep -q "Step 1c"
}

@test "hook: block when report contains only NoCoverage + CompileError (no scored mutants)" {
  _write_report_with_statuses "$D/StrykerOutput/smoke/reports/mutation-report.json" \
    NoCoverage NoCoverage NoCoverage CompileError CompileError
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q "no scored mutants"
  echo "$output" | grep -q "different probe file"
}

@test "hook: block when mutants[] is empty" {
  _write_report_raw "$D/StrykerOutput/smoke/reports/mutation-report.json" \
    '{"schemaVersion":"1","mutants":[]}'
  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 2 ]
  echo "$output" | grep -q "no scored mutants"
}

@test "hook: silent-pass when report has at least one Killed mutant" {
  # Reuse the real Stryker.NET fixture verbatim — Killed + Survived.
  cp "$REPO_ROOT/tests/hooks/fixtures/stryker-net/mutation-report-zero-kill.json" \
    "$D/StrykerOutput/smoke/reports/mutation-report.json"
  # Sanity-check the fixture has what we expect (one Killed, one Survived).
  local killed
  killed="$(jq -r '[.mutants[] | select(.status=="Killed")] | length' "$D/StrykerOutput/smoke/reports/mutation-report.json")"
  [ "$killed" -ge 1 ]

  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: silent-pass on stale report (freshness NOT checked in v1)" {
  # Locks the v1 documented decision: no freshness check.
  # A stale-but-passing report continues to pass the gate.
  _write_report_with_statuses "$D/StrykerOutput/smoke/reports/mutation-report.json" \
    Killed Survived
  # Set mtime to 30 days ago. `touch -t YYYYMMDDhhmm` is cross-platform.
  local old
  old="$(python3 -c 'import datetime; print((datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d%H%M"))')"
  touch -t "$old" "$D/StrykerOutput/smoke/reports/mutation-report.json"

  _dispatch "$(_payload "dotnet stryker --config-file stryker-config.json")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
