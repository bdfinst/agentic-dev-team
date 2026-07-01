#!/usr/bin/env bats
# Contract for eval fixtures that grade test-smell-review output.
# Each fixture MUST require the appropriate remedy-family slug via mustMention
# so verdict.py:40 (which concatenates issue.message + summary and scans for
# mustMention keywords in prose) actually enforces the family cite (#534).
#
# Mapping is derived from knowledge/test-smells.md:
#   Assertion Roulette      → result-verification (Expected Object / Custom Assertion)
#   Mystery Guest           → fixture-construction (Creation Method / Minimal Fixture)
#   Overspecified Mocks     → result-verification (state verification, not behavior)
#                             — plan originally proposed test-organization; Step 2.1
#                             confirmed the smell's remedy row in test-smells.md
#                             lives in result-verification.md's state-vs-behavior
#                             section, so we cite that family instead.
#   Clean Doubles (control) → no smell → no family cite added

EVALS="$BATS_TEST_DIRNAME/../../evals/expected"

require_must_mention() {
  local fixture="$1"; shift
  local kw
  for kw in "$@"; do
    run jq --arg kw "$kw" \
      '.agents["test-smell-review"].mustMention | index($kw) != null' \
      "$EVALS/$fixture"
    [ "$status" -eq 0 ]
    [ "$output" = "true" ]
  done
}

@test "Assertion Roulette fixture requires 'result-verification' in mustMention" {
  require_must_mention "test-assertion-roulette.test.json" "result-verification"
}

@test "Mystery Guest fixture requires 'fixture-construction' in mustMention" {
  require_must_mention "test-mystery-guest.test.json" "fixture-construction"
}

@test "Overspecified Mocks fixture requires 'result-verification' in mustMention" {
  require_must_mention "test-overspecified-mocks.test.json" "result-verification"
}

@test "Clean Doubles fixture must NOT add a remedy-family mustMention" {
  # Control fixture — expects no smell, so no family cite should be required.
  run jq '.agents["test-smell-review"].mustMention' "$EVALS/test-clean-doubles.test.json"
  [ "$status" -eq 0 ]
  # mustMention should not contain any of the four family slugs.
  local family
  for family in fixture-construction result-verification test-organization test-refactoring; do
    run jq --arg kw "$family" \
      '.agents["test-smell-review"].mustMention | index($kw) != null' \
      "$EVALS/test-clean-doubles.test.json"
    [ "$status" -eq 0 ]
    [ "$output" = "false" ]
  done
}
