#!/usr/bin/env bats
# Integration validation: all 7 agent-audit items fixed after wave 1 merges.

AGENTS="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents"
HOOKS="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks"

# session-analysis: JSON output block present (fenced block after "Output JSON:")
@test "session-analysis has Output JSON: header" {
  grep -q "Output JSON:" "$AGENTS/session-analysis.md"
}

@test "session-analysis JSON block contains status pass|warn|fail|skip" {
  # Check for the fenced JSON block content, not just the header
  grep -q '"status": "pass|warn|fail|skip"' "$AGENTS/session-analysis.md"
}

@test "session-analysis has severity definitions" {
  grep -q "Severity:" "$AGENTS/session-analysis.md"
}

@test "session-analysis has Skip section" {
  grep -q "## Skip" "$AGENTS/session-analysis.md"
}

@test "session-analysis has Context needs: full-file" {
  grep -q "Context needs: full-file" "$AGENTS/session-analysis.md"
}

@test "claude-setup-review has Context needs: project-structure" {
  grep -q "Context needs: project-structure" "$AGENTS/claude-setup-review.md"
}

@test "orchestrator declares enforcement: script and an Implemented-by pointer" {
  # Script-enforced prose spec (PR #462): declares its implementation rather
  # than a "You are" persona.
  grep -qE '^enforcement:[[:space:]]*script' "$AGENTS/orchestrator.md"
  grep -qE '^> \*\*Implemented by:\*\*' "$AGENTS/orchestrator.md"
}

@test "mutation_gate hook does not use sys.exit(non-zero) on advisory paths" {
  # #572 Python port: the .sh's `set -uo pipefail` idiom retired with bash.
  # The .py must still be import-clean.
  run python3 -c "import importlib.util, pathlib; p = pathlib.Path('$HOOKS/mutation_gate.py'); s = importlib.util.spec_from_file_location('mutation_gate', p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print('ok')"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "eval_compliance_check hook is import-clean" {
  # #572 Python port: replaces the printf-variable audit that used to run on .sh.
  run python3 -c "import importlib.util, pathlib; p = pathlib.Path('$HOOKS/eval_compliance_check.py'); s = importlib.util.spec_from_file_location('eval_compliance_check', p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print('ok')"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "both hooks parse cleanly under python3 -m py_compile" {
  # Replaces the shellcheck gate that ran on the .sh siblings pre-#572.
  run python3 -m py_compile "$HOOKS/mutation_gate.py" "$HOOKS/eval_compliance_check.py"
  [ "$status" -eq 0 ]
}
