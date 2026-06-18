#!/usr/bin/env bats
# Vocabulary, pyramid-framing, and E2E-justification guards for the
# test-design-advisor / test-design / cd-test-architecture skills.
# Source: reports/improve-test-design-skills.md

ADVISOR="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design-advisor/SKILL.md"
DESIGN="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design/SKILL.md"
CDARCH="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/cd-test-architecture/SKILL.md"
SMELL="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/test-smell-review.md"
DOTNET_EXAMPLE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-matrix-examples/dotnet-grpc-fronting-api.md"

@test "test-design-advisor: 'narrow integration' only appears with the contract-test gloss" {
  # Any line that mentions "narrow integration" must, on the same line,
  # also mention "contract test" — the MinimumCD primary term.
  run awk 'BEGIN{bad=0}
    /narrow integration/ {
      if ($0 !~ /contract test/) { print NR": "$0; bad=1 }
    }
    END{ exit(bad) }' "$ADVISOR"
  [ "$status" -eq 0 ]
}

@test "test-design SKILL: 'narrow integration' only appears with the contract-test gloss" {
  run awk 'BEGIN{bad=0}
    /narrow integration/ {
      if ($0 !~ /contract test/) { print NR": "$0; bad=1 }
    }
    END{ exit(bad) }' "$DESIGN"
  [ "$status" -eq 0 ]
}

@test "cd-test-architecture: 'narrow integration' only appears with the contract-test gloss" {
  run awk 'BEGIN{bad=0}
    /narrow integration/ {
      if ($0 !~ /contract test/) { print NR": "$0; bad=1 }
    }
    END{ exit(bad) }' "$CDARCH"
  [ "$status" -eq 0 ]
}

@test "test-smell-review: 'narrow integration' only appears with the contract-test gloss" {
  run awk 'BEGIN{bad=0}
    /narrow integration/ {
      if ($0 !~ /contract test/) { print NR": "$0; bad=1 }
    }
    END{ exit(bad) }' "$SMELL"
  [ "$status" -eq 0 ]
}

@test "test-design-advisor: 'target shape' only appears in prohibiting context" {
  # The pyramid-is-a-cost-heuristic constraint mentions "target shape" only
  # to forbid it. Any other usage (a coaching recommendation toward a
  # silhouette) is a regression.
  run awk 'BEGIN{bad=0}
    /target shape/ {
      # allow lines that negate the term: "not a target shape" /
      # "rather than ... target shape" / "no target shape" / "do not ... target shape"
      if ($0 !~ /not a target shape|not target shape|no target shape|NOT.*target shape|do not.*target shape|never.*target shape|cost heuristic.*not.*target shape|drop.*target shape|forbid.*target shape|No target-shape|no target-shape/) {
        print NR": "$0; bad=1
      }
    }
    END{ exit(bad) }' "$ADVISOR"
  [ "$status" -eq 0 ]
}

@test "test-design-advisor: any 'target ... count' phrase only appears in prohibiting context" {
  # Catches phrases like 'target test count(s) per layer', 'per-layer target
  # count', 'target count per layer'. The pyramid-is-a-cost-heuristic
  # constraint mentions them only to forbid them — a prohibiting verb
  # ("not", "no", "never", "do not", "Do not", "DO NOT", "forbid", "drop")
  # must appear on the same line as the trigger phrase.
  run awk 'BEGIN{bad=0; IGNORECASE=1}
    /target test \*?counts?\*? per layer|target count per layer|per-layer target count|target counts per layer/ {
      if (tolower($0) !~ /not|never|forbid|drop/) {
        print NR": "$0; bad=1
      }
    }
    END{ exit(bad) }' "$ADVISOR"
  [ "$status" -eq 0 ]
}

@test "test-design-advisor: encodes the pyramid-is-a-cost-heuristic constraint" {
  run grep -c "cost heuristic" "$ADVISOR"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design-advisor: encodes the E2E justification gate" {
  run grep -c "E2E justification" "$ADVISOR"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design-advisor: encodes the MinimumCD vocabulary constraint" {
  run grep -c "MinimumCD" "$ADVISOR"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design-advisor: placement table uses two-direction 'Why this layer (not the one above or below)'" {
  run grep -c "Why this layer (not the one above or below)" "$ADVISOR"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL: forwards the E2E justification gate" {
  run grep -ci "E2E justification" "$DESIGN"
  [ "$output" -gt 0 ]
}

@test "test-design SKILL: forbids target-shape rollups" {
  run grep -ci "target shape" "$DESIGN"
  [ "$output" -eq 0 ]
}

@test "cd-test-architecture: encodes the E2E justification gate" {
  run grep -ci "E2E justification" "$CDARCH"
  [ "$output" -gt 0 ]
}

@test "cd-test-architecture: encodes the pyramid-is-a-cost-heuristic constraint" {
  run grep -ci "cost heuristic" "$CDARCH"
  [ "$output" -gt 0 ]
}

@test ".NET-gRPC worked example exists for test-design-advisor" {
  [ -f "$DOTNET_EXAMPLE" ]
}

@test ".NET-gRPC worked example uses MinimumCD layer names and gates E2E" {
  run grep -ci "contract" "$DOTNET_EXAMPLE"
  [ "$output" -gt 0 ]
  run grep -ci "E2E justification" "$DOTNET_EXAMPLE"
  [ "$output" -gt 0 ]
}
