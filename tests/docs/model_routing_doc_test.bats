#!/usr/bin/env bats
# AC12: docs/model-routing.md contains the eight required H2 sections
# with at least one paragraph each, links to the ADR, and documents the
# env-var classification (test-only seams vs. user-facing knobs).

DOC="$BATS_TEST_DIRNAME/../../plugins/dev-team/docs/model-routing.md"

@test "AC12: doc file exists" {
  [ -f "$DOC" ]
}

@test "AC12: section 'Contract' is present" {
  grep -qE "^## Contract" "$DOC"
}

@test "AC12: section 'When the fallback fires' is present" {
  grep -qE "^## When the fallback fires" "$DOC"
}

@test "AC12: section 'Interpreting the override file' is present" {
  grep -qE "^## Interpreting the override file" "$DOC"
}

@test "AC12: section 'Adding a new tier' is present" {
  grep -qE "^## Adding a new tier" "$DOC"
}

@test "AC12: section 'Troubleshooting: Bedrock' is present" {
  grep -qE "^## Troubleshooting: Bedrock" "$DOC"
}

@test "AC12: section 'Troubleshooting: Vertex' is present" {
  grep -qE "^## Troubleshooting: Vertex" "$DOC"
}

@test "AC12: section 'Troubleshooting: corporate proxy' is present" {
  grep -qE "^## Troubleshooting: corporate proxy" "$DOC"
}

@test "AC12: section 'Hand-writing the override file' is present" {
  grep -qE "^## Hand-writing the override file" "$DOC"
}

@test "AC12: doc links to ADR 0004" {
  grep -q "0004-pre-dispatch-model-resolution" "$DOC"
}

@test "AC12: doc documents user-facing env vars" {
  grep -q "ANTHROPIC_BASE_URL" "$DOC"
  grep -q "MODEL_PROBE_TIMEOUT" "$DOC"
  grep -q "MODEL_BUMP_TAIL" "$DOC"
  grep -q "MODEL_PROBE_FORCE" "$DOC"
}

@test "AC12: doc marks test-only env vars as test-only" {
  # Should mention MODEL_ROUTING_JSON, MODEL_OVERRIDES_JSON, MODEL_BUMP_LOG
  # and identify them as test-only seams (not user-facing).
  grep -q "MODEL_ROUTING_JSON" "$DOC"
  grep -q "MODEL_OVERRIDES_JSON" "$DOC"
  grep -q "MODEL_BUMP_LOG" "$DOC"
  grep -qi "test-only" "$DOC"
}
