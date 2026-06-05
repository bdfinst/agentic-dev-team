#!/usr/bin/env bats
# #85: the test-layer-gates eval corpus (tlg-*) is structurally well-formed —
# 1:1 fixture<->expected pairing, valid skill schema, valid gate/layer vocab.
# Deterministic structural guard; behavioral gate-firing is graded by
# /agent-eval --skill test-design-advisor (model-judged).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
FIXTURES="$REPO_ROOT/evals/fixtures"
EXPECTED="$REPO_ROOT/evals/expected"

@test "tlg: there are 11 fixtures (one per #80 gate row)" {
  run bash -c "ls \"$FIXTURES\"/tlg-*.md | wc -l | tr -d ' '"
  [ "$status" -eq 0 ]
  [ "$output" -eq 11 ]
}

@test "tlg: every fixture has a matching expected JSON" {
  for f in "$FIXTURES"/tlg-*.md; do
    stem=$(basename "$f" .md)
    [ -f "$EXPECTED/$stem.json" ] || { echo "missing expected: $stem.json" >&2; return 1; }
  done
}

@test "tlg: every expected JSON has a matching fixture" {
  for e in "$EXPECTED"/tlg-*.json; do
    stem=$(basename "$e" .json)
    [ -f "$FIXTURES/$stem.md" ] || { echo "missing fixture: $stem.md" >&2; return 1; }
  done
}

@test "tlg: every expected JSON parses and declares the advisor skill" {
  for e in "$EXPECTED"/tlg-*.json; do
    run jq -e '.applicableSkills | index("test-design-advisor")' "$e"
    [ "$status" -eq 0 ] || { echo "not a test-design-advisor skill fixture: $e" >&2; return 1; }
  done
}

@test "tlg: fixture field matches the file stem" {
  for e in "$EXPECTED"/tlg-*.json; do
    stem=$(basename "$e" .json)
    run jq -re '.fixture' "$e"
    [ "$status" -eq 0 ]
    [ "$output" = "$stem" ] || { echo "fixture field mismatch in $e: $output != $stem" >&2; return 1; }
  done
}

@test "tlg: skills block has the required array fields" {
  for e in "$EXPECTED"/tlg-*.json; do
    run jq -e '
      .skills["test-design-advisor"] as $s
      | ($s.expectedGates | type == "array")
        and ($s.expectedLayers | type == "array")
        and ($s.mustMention | type == "array")
        and ($s.mustNotMention | type == "array")
    ' "$e"
    [ "$status" -eq 0 ] || { echo "bad skills block: $e" >&2; return 1; }
  done
}

@test "tlg: expectedGates use the gate vocabulary" {
  for e in "$EXPECTED"/tlg-*.json; do
    run jq -e '
      .skills["test-design-advisor"].expectedGates
      | all(. as $g | ["A","B","C","D","redundancy","ambiguity"] | index($g))
    ' "$e"
    [ "$status" -eq 0 ] || { echo "invalid gate value in $e" >&2; return 1; }
  done
}

@test "tlg: expectedLayers use the test-pyramid vocabulary" {
  for e in "$EXPECTED"/tlg-*.json; do
    run jq -e '
      .skills["test-design-advisor"].expectedLayers
      | all(. as $l | ["unit","integration","component","contract","E2E"] | index($l))
    ' "$e"
    [ "$status" -eq 0 ] || { echo "invalid layer value in $e" >&2; return 1; }
  done
}

@test "tlg: all four behavior gates (A,B,C,D) plus redundancy and ambiguity are represented" {
  run bash -c "cat \"$EXPECTED\"/tlg-*.json | jq -r '.skills[\"test-design-advisor\"].expectedGates[]' | sort -u | tr '\n' ' '"
  [ "$status" -eq 0 ]
  for g in A B C D redundancy ambiguity; do
    [[ "$output" == *"$g"* ]] || { echo "gate not represented in corpus: $g" >&2; return 1; }
  done
}
