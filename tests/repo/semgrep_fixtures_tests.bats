#!/usr/bin/env bats
# Structural tests for the per-rule semgrep fixtures (#124). Deterministic and
# semgrep-free (the semgrep-executing measurement runs as its own CI job): every
# custom rule must have a positive + negative fixture, and the known-broken list
# must reference only real rule ids.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
RULES_DIR="$REPO_ROOT/plugins/security-assessment/knowledge/semgrep-rules"
FIX_DIR="$REPO_ROOT/plugins/security-assessment/knowledge/rule-fixtures"
KNOWN_BROKEN="$FIX_DIR/known-broken-rules.txt"

_rule_ids() {
  grep -rhE "^  - id:" "$RULES_DIR"/*.yaml | sed 's/^  - id:[[:space:]]*//'
}

@test "fixtures: all 36 custom rules are present" {
  run bash -c "grep -rhE '^  - id:' '$RULES_DIR'/*.yaml | wc -l"
  [ "$output" -eq 36 ]
}

@test "fixtures: every rule has >=1 positive and >=1 negative fixture" {
  local missing=""
  while IFS= read -r rid; do
    [ -z "$rid" ] && continue
    local d="$FIX_DIR/$rid"
    if [ -z "$(find "$d" -maxdepth 1 -name 'positive.*' 2>/dev/null)" ] \
       || [ -z "$(find "$d" -maxdepth 1 -name 'negative.*' 2>/dev/null)" ]; then
      missing="$missing $rid"
    fi
  done < <(_rule_ids)
  [ -z "$missing" ] || { echo "missing fixtures for:$missing"; false; }
}

@test "fixtures: every rule records fp_rate OR semgrep_status in metadata" {
  # The measurement stamps fp_rate (working rules) or semgrep_status (broken).
  local n_fp n_status
  n_fp=$(grep -rhc "fp_rate:" "$RULES_DIR"/*.yaml | awk '{s+=$1} END{print s}')
  n_status=$(grep -rhc "semgrep_status:" "$RULES_DIR"/*.yaml | awk '{s+=$1} END{print s}')
  [ "$((n_fp + n_status))" -eq 36 ]
}

@test "known-broken: every listed id is a real rule id" {
  local ids; ids=$(_rule_ids)
  local bad=""
  while IFS= read -r line; do
    line="${line%%#*}"; line="$(echo "$line" | xargs)"
    [ -z "$line" ] && continue
    echo "$ids" | grep -qx "$line" || bad="$bad $line"
  done < "$KNOWN_BROKEN"
  [ -z "$bad" ] || { echo "unknown rule ids in known-broken-rules.txt:$bad"; false; }
}

@test "audit: the semgrep-fixtures audit script exists and is executable-ish" {
  [ -f "$REPO_ROOT/plugins/security-assessment/scripts/audit-semgrep-fixtures.py" ]
  run python3 -c "import ast; ast.parse(open('$REPO_ROOT/plugins/security-assessment/scripts/audit-semgrep-fixtures.py').read())"
  [ "$status" -eq 0 ]
}
