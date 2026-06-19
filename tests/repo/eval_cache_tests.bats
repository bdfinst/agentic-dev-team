#!/usr/bin/env bats
# Tests for scripts/eval_cache.py — the per-pair fingerprint replay cache that
# lets the live eval gate skip unchanged pairs (issue #311). Hermetic: every
# test builds a tiny self-contained corpus + plugin tree under a tmp repo root,
# so no model and no real corpus is touched.

CACHE="$BATS_TEST_DIRNAME/../../scripts/eval_cache.py"

setup() {
  T="$(mktemp -d)"
  mkdir -p "$T/plugins/dev-team/agents" "$T/plugins/dev-team/knowledge" \
           "$T/plugins/dev-team/skills" "$T/evals/expected" "$T/evals/fixtures"
  cat > "$T/plugins/dev-team/agents/demo-review.md" <<'EOF'
# Demo Review
Read `knowledge/demo-knowledge.md` before starting.
EOF
  echo "rule: flag layer violations" > "$T/plugins/dev-team/knowledge/demo-knowledge.md"
  cat > "$T/evals/expected/demo.json" <<'EOF'
{ "fixture": "demo.ts", "applicableAgents": ["demo-review"],
  "agents": { "demo-review": { "expectedStatus": "fail", "mustMention": ["layer"] } } }
EOF
  echo "const x = 1" > "$T/evals/fixtures/demo.ts"
}
teardown() { rm -rf "$T"; }

fp() { python3 "$CACHE" --repo-root "$T" --fingerprint "demo::demo-review" \
         | sed -n 's/^fingerprint: //p'; }

@test "fingerprint: stable across runs for an unchanged pair" {
  a="$(fp)"; b="$(fp)"
  [ -n "$a" ]
  [ "$a" = "$b" ]
}

@test "fingerprint: editing the fixture busts the SHA" {
  a="$(fp)"
  echo "const x = 2" > "$T/evals/fixtures/demo.ts"
  b="$(fp)"
  [ "$a" != "$b" ]
}

@test "fingerprint: editing the agent definition busts the SHA" {
  a="$(fp)"
  echo "extra rule" >> "$T/plugins/dev-team/agents/demo-review.md"
  b="$(fp)"
  [ "$a" != "$b" ]
}

@test "fingerprint: editing a TRANSITIVE knowledge dep busts the SHA" {
  a="$(fp)"
  echo "new transitive rule" >> "$T/plugins/dev-team/knowledge/demo-knowledge.md"
  b="$(fp)"
  [ "$a" != "$b" ]
}

@test "fingerprint: lists the transitive knowledge file among contributors" {
  run python3 "$CACHE" --repo-root "$T" --fingerprint "demo::demo-review"
  [ "$status" -eq 0 ]
  [[ "$output" == *"knowledge/demo-knowledge.md"* ]]
  [[ "$output" == *"agents/demo-review.md"* ]]
  [[ "$output" == *"fixtures/demo.ts"* ]]
}

passing_actuals() {
  cat > "$T/actuals.json" <<'EOF'
{ "demo": { "agents": { "demo-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
  "summary": "" } } } }
EOF
}

@test "store + plan: a stored PASS with unchanged SHA replays as a cache hit" {
  passing_actuals
  run python3 "$CACHE" --repo-root "$T" --store --actuals "$T/actuals.json"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stored 1 passing pair"* ]]
  # Plan now: the pair should be a hit (replayable), not a miss.
  run python3 "$CACHE" --repo-root "$T" --plan --replay-out "$T/replay.json"
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 cache hit"* ]]
  [[ "$output" != *"miss demo::demo-review"* ]]
  # The replay actuals reproduce the stored output for the hit.
  run jq -r '.demo.agents."demo-review".status' "$T/replay.json"
  [ "$output" = "fail" ]
}

@test "plan: changing an input after a store busts the cache (miss again)" {
  passing_actuals
  python3 "$CACHE" --repo-root "$T" --store --actuals "$T/actuals.json"
  echo "const x = 999" > "$T/evals/fixtures/demo.ts"   # bust the SHA
  run python3 "$CACHE" --repo-root "$T" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"miss demo::demo-review"* ]]
}

@test "resilience: a corrupt cache is silently ignored (every pair a miss)" {
  passing_actuals
  python3 "$CACHE" --repo-root "$T" --store --actuals "$T/actuals.json"
  echo 'not json {' > "$T/evals/.eval-cache.json"   # corrupt it
  run python3 "$CACHE" --repo-root "$T" --plan
  [ "$status" -eq 0 ]                                # no crash
  [[ "$output" == *"miss demo::demo-review"* ]]      # degrades to dispatch
}

@test "store: a FAILING pair is NOT cached (only PASSes replay)" {
  cat > "$T/actuals.json" <<'EOF'
{ "demo": { "agents": { "demo-review": {
  "status": "pass", "issues": [], "summary": "looks clean" } } } }
EOF
  run python3 "$CACHE" --repo-root "$T" --store --actuals "$T/actuals.json"
  [ "$status" -eq 0 ]
  [[ "$output" == *"stored 0 passing pair"* ]]
  run python3 "$CACHE" --repo-root "$T" --plan
  [[ "$output" == *"miss demo::demo-review"* ]]
}

@test "cache file lives at evals/.eval-cache.json (gitignored path)" {
  passing_actuals
  python3 "$CACHE" --repo-root "$T" --store --actuals "$T/actuals.json"
  [ -f "$T/evals/.eval-cache.json" ]
}
