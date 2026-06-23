#!/usr/bin/env bats
# Tests for ADR 0009 (human consent gate) and ADR 0010 (per-session granularity)

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
ADR_0009="$REPO_ROOT/docs/adr/0009-human-consent-gate-for-learning-loop.md"
ADR_0010="$REPO_ROOT/docs/adr/0010-per-session-analysis-granularity.md"

@test "ADR 0009: file exists" {
  [ -f "$ADR_0009" ]
}

@test "ADR 0009: has Accepted status and required sections" {
  grep -qE "^## Status" "$ADR_0009"
  grep -q "Accepted" "$ADR_0009"
  grep -qE "^## Context" "$ADR_0009"
  grep -qE "^## Decision" "$ADR_0009"
  grep -qE "^## Consequences" "$ADR_0009"
}

@test "ADR 0009: Decision section contains 'queued' and not 'auto-applied'" {
  decision=$(awk '/^## Decision/{f=1; next} /^## /{f=0} f' "$ADR_0009")
  echo "$decision" | grep -qi "queued"
  ! echo "$decision" | grep -qi "auto-applied"
}

@test "ADR 0010: file exists" {
  [ -f "$ADR_0010" ]
}

@test "ADR 0010: has Accepted status and required sections" {
  grep -qE "^## Status" "$ADR_0010"
  grep -q "Accepted" "$ADR_0010"
  grep -qE "^## Context" "$ADR_0010"
  grep -qE "^## Decision" "$ADR_0010"
  grep -qE "^## Consequences" "$ADR_0010"
}

@test "ADR 0010: Decision section contains 'SessionStop' and not 'per turn'" {
  decision=$(awk '/^## Decision/{f=1; next} /^## /{f=0} f' "$ADR_0010")
  echo "$decision" | grep -q "SessionStop"
  ! echo "$decision" | grep -qi "per turn"
}
