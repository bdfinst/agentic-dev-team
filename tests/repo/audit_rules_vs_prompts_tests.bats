#!/usr/bin/env bats
# Tests for scripts/audit-rules-vs-prompts.sh — the rules-vs-prompts
# enforcement sensor (issue #118). Exercises the pass case on the real tree
# and each failure mode via synthetic manifests injected through the env seams
# (RULE_MAP, OWASP_DOC, PLUGIN_ROOT).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
AUDIT="$REPO_ROOT/scripts/audit-rules-vs-prompts.sh"

@test "audit: passes on the real repository tree" {
  run bash "$AUDIT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"audit OK"* ]]
}

# Build a synthetic plugin root with a manifest, owasp doc, and fixtures.
_setup_synthetic() {
  P="$BATS_TEST_TMPDIR/plugin"
  mkdir -p "$P/knowledge/rule-fixtures/A03.sql-injection"
  echo 'q(`${x}`)' > "$P/knowledge/rule-fixtures/A03.sql-injection/positive.js"
  echo 'q("?", [x])' > "$P/knowledge/rule-fixtures/A03.sql-injection/negative.js"
  echo "# OWASP" > "$P/knowledge/owasp-detection.md"
  export PLUGIN_ROOT="$P"
  export RULE_MAP="$P/knowledge/security-review-rule-map.yaml"
  export OWASP_DOC="$P/knowledge/owasp-detection.md"
}

@test "audit: a correct synthetic manifest passes" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings:
  A03.sql-injection: semgrep.generic.sql-injection
  A01.idor: security-review.a01.idor
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.05
    fixtures: knowledge/rule-fixtures/A03.sql-injection
  A01.idor: { surface: prompt }
YAML
  run bash "$AUDIT"
  [ "$status" -eq 0 ]
}

@test "audit: FAILS when a rule-surface class fp_rate exceeds 10%" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings: { A03.sql-injection: semgrep.generic.sql-injection }
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.25
    fixtures: knowledge/rule-fixtures/A03.sql-injection
YAML
  run bash "$AUDIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"DEMOTION CANDIDATE"* ]]
}

@test "audit: FAILS on cross-surface duplication (prompt class with semgrep rule_id)" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings: { A01.idor: semgrep.generic.idor }
classes:
  A01.idor: { surface: prompt }
YAML
  run bash "$AUDIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"two surfaces"* ]]
}

@test "audit: FAILS when a rule-surface class lacks fixtures" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings: { A05.cors-wildcard: semgrep.generic.cors-wildcard }
classes:
  A05.cors-wildcard:
    surface: rule
    fp_rate: 0.0
    fixtures: knowledge/rule-fixtures/does-not-exist
YAML
  run bash "$AUDIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"positive.*"* ]]
}

@test "audit: FAILS when a rule-surface class is an agent detection row in owasp doc" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings: { A03.sql-injection: semgrep.generic.sql-injection }
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.0
    fixtures: knowledge/rule-fixtures/A03.sql-injection
YAML
  cat > "$OWASP_DOC" <<'MD'
# OWASP
| Pattern | Language | Grep Signal | Category |
| SQL concat | All | string concat in query | `A03.sql-injection` |
MD
  run bash "$AUDIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"detection row"* ]]
}

@test "audit: FAILS on an invalid surface value" {
  _setup_synthetic
  cat > "$RULE_MAP" <<'YAML'
version: 1.1.0
mappings: { A01.idor: security-review.a01.idor }
classes:
  A01.idor: { surface: maybe }
YAML
  run bash "$AUDIT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"invalid surface"* ]]
}
