#!/usr/bin/env bats
# Contract for /test-improve Phase 4 — improve tests without refactoring,
# then end-of-phase review loop. Issue #536, Slice 6 (Steps 6.1 + 6.2).

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_4_section() {
  awk '
    /^### Phase 4( —|$| \()/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 4 section header" {
  grep -Eq '^### Phase 4( —|$| \()' "$SKILL"
}

# Step 6.1 assertions — build + mutation-kill loop

@test "Phase 4 invokes /build" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '/build'
}

@test "Phase 4 inherits no-refactor mode from Phase 0" {
  section=$(phase_4_section)
  echo "$section" | grep -Eqi 'no-refactor.*(Phase[[:space:]]+0|inherit)|inherit.*no-refactor|Phase[[:space:]]+0.*no-refactor'
}

@test "Phase 4 measures per-Story coverage via /coverage-delta --workflow test-improve --story <id>" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '/coverage-delta.*--workflow[[:space:]]+test-improve.*--story|--story.*--workflow[[:space:]]+test-improve.*coverage-delta'
}

@test "Phase 4 invokes the mutation-kill agent per Story with --file and --max-rounds 3" {
  section=$(phase_4_section)
  echo "$section" | grep -Eqi 'mutation-kill'
  echo "$section" | grep -Eq -- '--file'
  echo "$section" | grep -Eq -- '--max-rounds 3'
}

@test "Phase 4 documents the [c/r/w/q] mutation-kill prompt" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '\[c/r/w/q\]|\[c\].*\[r\].*\[w\].*\[q\]'
}

@test "Phase 4 mutation-kill is advisory on Go (no commit)" {
  section=$(phase_4_section)
  echo "$section" | grep -Eqi 'Go.*(advisory|no[[:space:]]+commit|logged)|advisory.*Go'
}

@test "Phase 4 applies binding-mode annotations per Phase 0" {
  section=$(phase_4_section)
  echo "$section" | grep -Eqi 'Given/When/Then|leading[[:space:]]+comment|scenario[[:space:]]+name'
}

# Step 6.2 assertions — end-of-phase review loop

@test "Phase 4 review loop dispatches /test-design --since and /code-review --since in parallel" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '/test-design[[:space:]]+--since'
  echo "$section" | grep -Eq '/code-review[[:space:]]+--since'
  echo "$section" | grep -Eqi 'parallel|concurrent|dispatch'
}

@test "Phase 4 review loop runs /apply-fixes corrections/ then re-runs /code-review" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '/apply-fixes[[:space:]]+corrections/'
}

@test "Phase 4 review loop caps at 2 iterations before escalation" {
  section=$(phase_4_section)
  echo "$section" | grep -Eqi '2[[:space:]]+iteration|max[[:space:]]+2|at[[:space:]]+most[[:space:]]+2'
}

@test "Phase 4 review loop uses [r/w/q] escalation prompt" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq '\[r/w/q\]|\[r\].*\[w\].*\[q\]'
}

@test "Phase 4 review loop writes phase-4-review.json with fixed schema" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/phase-4-review\.json'
  echo "$section" | grep -Eq 'base_sha'
  echo "$section" | grep -Eq 'head_sha'
  echo "$section" | grep -Eq 'farley_score'
  echo "$section" | grep -Eq 'smells'
  echo "$section" | grep -Eq 'code_review'
  echo "$section" | grep -Eq 'iterations'
  echo "$section" | grep -Eq 'escalated'
}

@test "Phase 4 review loop writes waivers.json tagged with findings" {
  section=$(phase_4_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/waivers\.json'
  echo "$section" | grep -Eqi 'tag'
}
