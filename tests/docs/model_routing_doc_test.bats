#!/usr/bin/env bats
# docs/model-routing.md documents the effort-band + ladder model: the core
# sections, links to the ADRs, and the env-var classification (test-only seams
# vs. user-facing knobs). The retired probe/overrides knobs must be gone.

DOC="$BATS_TEST_DIRNAME/../../plugins/dev-team/docs/model-routing.md"

@test "doc file exists" {
  [ -f "$DOC" ]
}

@test "section 'Contract' is present" {
  grep -qE "^## Contract" "$DOC"
}

@test "documents the resolution precedence" {
  grep -qiE "^###? Resolution precedence" "$DOC"
}

@test "documents the exit-code taxonomy" {
  grep -qiE "exit.code" "$DOC"
}

@test "documents legacy tier acceptance (deprecation window)" {
  grep -qiE "^## Legacy tier acceptance" "$DOC"
}

@test "documents the bump log" {
  grep -qiE "^## The bump log" "$DOC"
}

@test "documents authoring a ladder for restricted endpoints" {
  grep -qiE "^## Authoring a ladder" "$DOC"
  grep -qiE "bedrock|vertex|proxy" "$DOC"
}

@test "links to ADR 0008 and ADR 0004" {
  grep -q "0008-use-effort-bands" "$DOC"
  grep -q "0004-pre-dispatch-model-resolution" "$DOC"
}

@test "links to the override authoring guide" {
  grep -q "model-routing-overrides.md" "$DOC"
}

@test "documents user-facing env vars" {
  grep -q "ANTHROPIC_BASE_URL" "$DOC"
  grep -q "MODEL_BUMP_TAIL" "$DOC"
}

@test "marks the routing seams as test-only" {
  grep -q "MODEL_ROUTING_JSON" "$DOC"
  grep -q "MODEL_LADDER_JSON" "$DOC"
  grep -q "SESSION_MODEL_FILE" "$DOC"
  grep -q "MODEL_BUMP_LOG" "$DOC"
  grep -qi "test-only" "$DOC"
}

@test "no retired probe/overrides env vars remain" {
  ! grep -qE "MODEL_PROBE_TIMEOUT|MODEL_PROBE_FORCE|MODEL_OVERRIDES_JSON" "$DOC"
}
