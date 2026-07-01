#!/usr/bin/env bats
# Contract: /quality-targets-converge accepts --workflow <name> and templates
# memory + plan paths on it. The [Phase-2 amendment] gherkin-bindings escape
# hatch is removed from BOTH the SKILL body AND docs/agent-architecture.md so
# operators only see one route (the standard Phase-2 sign-off).
#
# Plan: plans/test-improve-orchestrator.md — Slice 11 (Step 11.2).

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/quality-targets-converge/SKILL.md"
ARCH="$BATS_TEST_DIRNAME/../../plugins/dev-team/docs/agent-architecture.md"

# --- --workflow surface -------------------------------------------------------

@test "SKILL: ## Parse Arguments documents --workflow <name>" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--workflow/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: ## Parse Arguments documents the --workflow default value" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE 'default.*test-modernize|Defaults to.*test-modernize'
}

@test "argument-hint frontmatter names --workflow" {
  run grep -E '^argument-hint:.*--workflow' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- paths templated on <workflow> --------------------------------------------

@test "SKILL: memory paths use <workflow> template (no literal memory/test-modernize/)" {
  ! grep -qE 'memory/test-modernize/' "$SKILL"
}

@test "SKILL: plan paths use <workflow> template (no literal ./plans/test-modernize/)" {
  ! grep -qE '\./plans/test-modernize/' "$SKILL"
}

@test "SKILL: memory paths reference memory/<workflow>/" {
  run grep -E 'memory/<workflow>/' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: plan paths reference ./plans/<workflow>/phase-5/" {
  run grep -E '\./plans/<workflow>/phase-5/' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- test-improve example -----------------------------------------------------

@test "SKILL: names test-improve as a supported --workflow value" {
  run grep -F 'test-improve' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- [Phase-2 amendment] escape hatch removed from BOTH locations -------------

@test "SKILL: [Phase-2 amendment] escape hatch is absent" {
  ! grep -qE '\[Phase-2 amendment\]' "$SKILL"
}

@test "agent-architecture.md: [Phase-2 amendment] paragraph is absent" {
  ! grep -qE '\[Phase-2 amendment\]' "$ARCH"
}
