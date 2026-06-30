#!/usr/bin/env bats
# Doc-shape contract for the /mutation-testing skill's workflow-callable mode.
# Plan: plans/mutation-testing-every-phase.md — Slice 1 (Steps 1.1 + 1.2).
#
# These tests assert the SKILL.md prose carries the invariants Slice 1 establishes:
# - Three new flags: --scope, --emit-json, --workflow-managed-approval.
# - Constraints retain "always ask the user before running" AND document the
#   --workflow-managed-approval carve-out with a named caller allowlist.
# - A documented machine-readable output schema (keys + per-tool examples).
# - The interactive prompt remains observable (literal "Estimated time:" string).
#
# Pattern: mirrors tests/docs/test_design_skill_vocabulary_tests.bats — awk/grep
# section guards against SKILL.md text. We are not exercising runtime behavior;
# the deliverable is the SKILL.md prose, and these guards regress when the
# contract drifts.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/SKILL.md"
LANG_DIR="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/references/languages"

# --- Step 1.1: flag surface --------------------------------------------------

@test "SKILL: ## Parse Arguments names --scope" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--scope/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: ## Parse Arguments names --emit-json" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--emit-json/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: ## Parse Arguments names --workflow-managed-approval" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--workflow-managed-approval/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 1.1: constraints carve-out + invariant retained --------------------

@test "SKILL: ## Constraints retains 'always ask the user before running' invariant" {
  run grep -A 999 '^## Constraints' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qi 'always ask the user before running'
}

@test "SKILL: ## Constraints documents --workflow-managed-approval carve-out" {
  run awk '/^## Constraints/{f=1;next} /^## /{f=0} f && /--workflow-managed-approval/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: carve-out names /coverage-delta as an allowed caller" {
  run awk '/^## Constraints/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '/coverage-delta'
}

@test "SKILL: carve-out names /quality-targets-converge as an allowed caller" {
  run awk '/^## Constraints/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '/quality-targets-converge'
}

@test "SKILL: carve-out cites /test-modernize Phase 0 as the approval boundary" {
  run awk '/^## Constraints/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'Phase 0|workflow-level approval'
}

@test "SKILL: carve-out documents extensibility rule for future callers" {
  # New callers can't silently bypass the prompt — the SKILL must tell them
  # to document their workflow-level approval boundary first.
  run awk '/^## Constraints/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'new caller|must document'
}

# --- Step 1.1: machine-readable output schema --------------------------------

@test "SKILL: has a ## Machine-readable output section" {
  run grep -E '^## Machine-readable output' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema names schema_version" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /schema_version/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema names tool, scope, captured_at, total, killed, survived, equivalent, survivors" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  for key in tool scope captured_at total killed survived equivalent survivors; do
    echo "$output" | grep -q "$key" || {
      echo "missing key: $key"
      return 1
    }
  done
}

@test "SKILL: survivor entries name file, line, operator, status" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  for key in file line operator status; do
    echo "$output" | grep -q "$key" || {
      echo "missing survivor key: $key"
      return 1
    }
  done
}

@test "SKILL: documents no_tool_installed error envelope" {
  run grep -E 'no_tool_installed' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents empty_scope error envelope" {
  run grep -E 'empty_scope' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents unwritable-path error path (stderr + exit non-zero)" {
  run grep -iE 'unwritable|read-only|stderr' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 1.1: interactive mode unchanged ------------------------------------

@test "SKILL: confirmation gate documents literal 'Estimated time:' prompt" {
  # The Gherkin scenario pins the observable Then: stdout contains "Estimated time:"
  run grep -F 'Estimated time:' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: confirmation gate documents skip-when-workflow-managed-approval" {
  # The Step 0 / confirmation block must say it is skipped under the flag.
  run grep -E 'skipped.*--workflow-managed-approval|--workflow-managed-approval.*skipped|--workflow-managed-approval.*bypass|bypass.*--workflow-managed-approval' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 1.1: equivalent-mutant tagging downstream-callable ----------------

@test "SKILL: schema documents status='equivalent' on survivor entries" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q 'equivalent'
}

# --- Step 1.2: per-language KBs carry the native-report schema mapping ------

@test "languages/javascript-stryker.md: has 'Native report' mapping with a Stryker JSON envelope" {
  run grep -iE '^##+ +Native report' "$LANG_DIR/javascript-stryker.md"
  [ "$status" -eq 0 ]
  run grep -q '"tool": "stryker"' "$LANG_DIR/javascript-stryker.md"
  [ "$status" -eq 0 ]
}

@test "languages/java-pitest.md: has 'Native report' mapping with a pitest JSON envelope" {
  run grep -iE '^##+ +Native report' "$LANG_DIR/java-pitest.md"
  [ "$status" -eq 0 ]
  run grep -q '"tool": "pitest"' "$LANG_DIR/java-pitest.md"
  [ "$status" -eq 0 ]
}

@test "languages/python-mutmut.md: has 'Native report' mapping with a mutmut JSON envelope" {
  run grep -iE '^##+ +Native report' "$LANG_DIR/python-mutmut.md"
  [ "$status" -eq 0 ]
  run grep -q '"tool": "mutmut"' "$LANG_DIR/python-mutmut.md"
  [ "$status" -eq 0 ]
}

@test "languages/csharp-stryker-net.md: has 'Native report' mapping with a Stryker.NET JSON envelope" {
  run grep -iE '^##+ +Native report' "$LANG_DIR/csharp-stryker-net.md"
  [ "$status" -eq 0 ]
  run grep -q '"tool": "stryker-net"' "$LANG_DIR/csharp-stryker-net.md"
  [ "$status" -eq 0 ]
}
