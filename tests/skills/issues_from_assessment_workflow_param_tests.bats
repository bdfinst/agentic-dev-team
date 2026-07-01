#!/usr/bin/env bats
# Contract: /issues-from-assessment accepts --workflow <name> and templates BOTH
# filesystem paths AND tracker-label strings so /test-improve runs don't leak
# `test-modernize` into operator-visible tags on GitHub/GitLab/ADO/Jira.
#
# Plan: plans/test-improve-orchestrator.md — Slice 11 (Step 11.1 + 11.4).

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/issues-from-assessment/SKILL.md"
COV_BASELINE="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/coverage-baseline/SKILL.md"
COV_DELTA="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/coverage-delta/SKILL.md"

# --- Step 11.1: --workflow surface -------------------------------------------

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

# --- Step 11.1: filesystem paths templated on <workflow> ---------------------

@test "SKILL: memory paths use <workflow> template" {
  run grep -E 'memory/<workflow>/' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: plan paths use <workflow> template" {
  run grep -E '\./plans/<workflow>/' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 11.1: tracker-label strings templated on <workflow> ----------------
# The Design Critic finding: operator-visible labels must not leak
# `test-modernize` from /test-improve runs. Every literal `test-modernize` inside
# --label / System.Tags= / labels[] must be replaced with <workflow>.

@test "SKILL: --label strings use <workflow> template (no literal test-modernize)" {
  # Look for --label lines and reject any that hard-code test-modernize.
  run grep -nE -- '--label' "$SKILL"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -qE -- '--label[^\n]*test-modernize'
}

@test "SKILL: System.Tags= strings use <workflow> template (no literal test-modernize)" {
  run grep -nE 'System\.Tags=' "$SKILL"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -qE 'System\.Tags=[^\n]*test-modernize'
}

@test "SKILL: --label snippet references <workflow>" {
  run grep -E -- '--label[^\n]*<workflow>' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: System.Tags snippet references <workflow>" {
  run grep -E 'System\.Tags=[^\n]*<workflow>' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 11.1: test-improve example ------------------------------------------

@test "SKILL: names test-improve as a supported --workflow value" {
  run grep -F 'test-improve' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 11.4: coverage-baseline + coverage-delta name test-improve ---------

@test "coverage-baseline SKILL.md references test-improve as a supported workflow" {
  run grep -F 'test-improve' "$COV_BASELINE"
  [ "$status" -eq 0 ]
}

@test "coverage-delta SKILL.md references test-improve as a supported workflow" {
  run grep -F 'test-improve' "$COV_DELTA"
  [ "$status" -eq 0 ]
}
