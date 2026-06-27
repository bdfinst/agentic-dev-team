#!/usr/bin/env bats
# PostToolUse hook that keeps docs/skills.md current: when an Edit/Write touches a
# skills/<name>/SKILL.md, it regenerates the catalog by shelling out to the
# builder. Fail-open — it must never block an Edit. A stub builder is injected via
# SKILLS_INDEX_BUILDER so these tests never write the real catalog.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/skills-index.sh"

setup() {
  WORK="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/work"
  rm -rf "$WORK"; mkdir -p "$WORK"
  # A stub builder that records it ran and exits 0.
  STUB_OK="$WORK/builder-ok.sh"
  printf '#!/usr/bin/env bash\ntouch "%s/ran"\nexit 0\n' "$WORK" > "$STUB_OK"
  chmod +x "$STUB_OK"
  # A stub builder that fails.
  STUB_FAIL="$WORK/builder-fail.sh"
  printf '#!/usr/bin/env bash\necho "boom" >&2\nexit 1\n' > "$STUB_FAIL"
  chmod +x "$STUB_FAIL"
}

run_hook() { SKILLS_INDEX_BUILDER="$1" run bash "$HOOK" <<<"$2"; }

@test "Edit on a SKILL.md triggers the builder and says 'rebuilt'" {
  run_hook "$STUB_OK" '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"[skills-index] rebuilt"* ]]
  [ -f "$WORK/ran" ]
}

@test "Edit on a non-SKILL file is a silent no-op" {
  run_hook "$STUB_OK" '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/agents/orchestrator.md"}}'
  [ "$status" -eq 0 ]
  [[ "$output" != *"[skills-index]"* ]]
  [ ! -f "$WORK/ran" ]
}

@test "a non-Edit/Write tool is a silent no-op" {
  run_hook "$STUB_OK" '{"tool_name":"Read","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}'
  [ "$status" -eq 0 ]
  [[ "$output" != *"[skills-index]"* ]]
  [ ! -f "$WORK/ran" ]
}

@test "builder failure is reported but the hook still exits 0 (fail-open)" {
  run_hook "$STUB_FAIL" '{"tool_name":"Write","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"[skills-index] rebuild failed"* ]]
}

@test "malformed stdin is a silent no-op (fail-open)" {
  run_hook "$STUB_OK" 'not json'
  [ "$status" -eq 0 ]
  [[ "$output" != *"[skills-index]"* ]]
}
