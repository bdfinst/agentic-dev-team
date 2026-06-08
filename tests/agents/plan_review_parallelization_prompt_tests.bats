#!/usr/bin/env bats
# #223 — the parallelization-review persona prompt. Follows the plan-review
# convention: a `# Plan Review:` H1, NO frontmatter, and a JSON verdict block.
# Asserts it covers the three required signals: same-wave file overlap, disjoint-
# file behavioral coupling, and residual cycles/mis-layering.

PROMPT="$BATS_TEST_DIRNAME/../../plugins/dev-team/prompts/plan-review-parallelization.md"

@test "prompt file exists" {
  [ -f "$PROMPT" ]
}

@test "no YAML frontmatter (plan-review prompt convention)" {
  [ "$(head -1 "$PROMPT")" != "---" ]
}

@test "uses the '# Plan Review:' H1 convention" {
  head -1 "$PROMPT" | grep -q '^# Plan Review:'
}

@test "declares its reviewer id in the JSON verdict block" {
  grep -q '"reviewer": "plan-review-parallelization"' "$PROMPT"
}

@test "emits an approve | needs-revision verdict" {
  grep -q '"verdict": "approve | needs-revision"' "$PROMPT"
}

@test "covers same-wave file-overlap collisions (from plan-waves.sh)" {
  grep -qi 'collision' "$PROMPT"
  grep -q 'plan-waves.sh' "$PROMPT"
}

@test "covers disjoint-file behavioral coupling" {
  grep -qi 'behavioral coupling' "$PROMPT"
  grep -qi 'disjoint' "$PROMPT"
}

@test "covers residual cycles / mis-layering" {
  grep -qi 'cycle' "$PROMPT"
}

@test "is referenced from the plan skill's review-persona set" {
  grep -q 'plan-review-parallelization.md' "$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/plan/SKILL.md"
}
