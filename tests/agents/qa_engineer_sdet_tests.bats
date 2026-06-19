#!/usr/bin/env bats
# Senior SDET identity, routing, and behavior guards for qa-engineer.md.
# Source: reports/improve-qa-agent.md

QA="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/qa-engineer.md"
ORCH="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/orchestrator.md"

@test "qa-engineer: frontmatter description names SDET and non-gatekeeping framing" {
  run grep -E "^description:.*SDET" "$QA"
  [ "$status" -eq 0 ]
  run grep -E "^description:.*non-gatekeeping" "$QA"
  [ "$status" -eq 0 ]
}

@test "qa-engineer: identity opens as Senior Software Engineer in Test" {
  run grep -c "Senior Software Engineer in Test" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: contains the Request routing table" {
  run grep -c "^## Request routing" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: routing table references the four primary test skills" {
  for skill in 'test-health' 'cd-test-architecture' 'test-design-advisor' '/test-design'; do
    grep -q -- "$skill" "$QA" || { echo "missing: $skill" >&2; return 1; }
  done
}

@test "qa-engineer: encodes the MinimumCD vocabulary constraint" {
  run grep -c "MinimumCD" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: encodes the four-condition E2E discipline" {
  run grep -ci "E2E discipline" "$QA"
  [ "$output" -gt 0 ]
}

@test "qa-engineer: drops the 'Release sign-off' gatekeeper language" {
  run grep -ci "Release sign-off" "$QA"
  [ "$output" -eq 0 ]
}

@test "qa-engineer: drops the 'Quality is non-negotiable' gatekeeper language" {
  run grep -ci "Quality is non-negotiable" "$QA"
  [ "$output" -eq 0 ]
}

@test "qa-engineer: encodes the pyramid-is-a-cost-heuristic framing" {
  run grep -ci "cost heuristic" "$QA"
  [ "$output" -gt 0 ]
}

@test "qa-engineer: references DORA metrics" {
  run grep -c "DORA" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: states that automation code is production code" {
  run grep -c "Automation code is production code" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: contains three-amigos / example mapping shift-left language" {
  run grep -c "three-amigos" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
  run grep -c "example mapping" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "qa-engineer: includes the Example dispatch section" {
  run grep -c "## Example dispatch" "$QA"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "orchestrator: routes strategic test-design requests via qa-engineer to test-health" {
  run grep -c "Test-review request routing" "$ORCH"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
  run grep -c "qa-engineer" "$ORCH"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
  # The strategic row mentions test-health under qa-engineer dispatch.
  run grep -E "qa-engineer.+test-health|test-health.+qa-engineer" "$ORCH"
  [ "$status" -eq 0 ]
}
