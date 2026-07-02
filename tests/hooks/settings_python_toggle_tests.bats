#!/usr/bin/env bats
# #574 — settings.json dispatches the mutation-testing-smoke-gate hook via
# the DEV_TEAM_PY_HOOK_MUTATION_TESTING_SMOKE_GATE env-var toggle. Default
# off (bash); "1" routes to the .py port. See
# plugins/dev-team/hooks/settings-toggle.md.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SETTINGS="$REPO_ROOT/plugins/dev-team/settings.json"

@test "settings.json is valid JSON" {
  jq empty "$SETTINGS"
}

@test "settings.json contains a smoke-gate hook entry" {
  jq -e '.hooks.PreToolUse[] | select(.hooks[]?.command | tostring | test("mutation-testing-smoke-gate|mutation_testing_smoke_gate"))' "$SETTINGS" >/dev/null
}

@test "smoke-gate hook uses DEV_TEAM_PY_HOOK_MUTATION_TESTING_SMOKE_GATE toggle" {
  local cmd
  cmd=$(jq -r '.hooks.PreToolUse[].hooks[]?.command // empty | select(test("mutation-testing-smoke-gate|mutation_testing_smoke_gate"))' "$SETTINGS" | head -1)
  [[ "$cmd" == *"DEV_TEAM_PY_HOOK_MUTATION_TESTING_SMOKE_GATE"* ]]
}

@test "smoke-gate hook references both .sh and .py implementations" {
  local cmd
  cmd=$(jq -r '.hooks.PreToolUse[].hooks[]?.command // empty | select(test("mutation-testing-smoke-gate|mutation_testing_smoke_gate"))' "$SETTINGS" | head -1)
  [[ "$cmd" == *"mutation-testing-smoke-gate.sh"* ]]
  [[ "$cmd" == *"mutation_testing_smoke_gate.py"* ]]
}

@test "smoke-gate hook defaults to bash (flag treated as 0 when unset)" {
  local cmd
  cmd=$(jq -r '.hooks.PreToolUse[].hooks[]?.command // empty | select(test("mutation-testing-smoke-gate|mutation_testing_smoke_gate"))' "$SETTINGS" | head -1)
  # The :- default and equality against "1" together imply "unset = bash"
  [[ "$cmd" == *":-0"* || "$cmd" == *':-'* ]]
  [[ "$cmd" == *'= "1"'* || "$cmd" == *'="1"'* || "$cmd" == *'= '\'1\'* ]]
}
