#!/usr/bin/env bats
# #226 — /plan step 6 must gate GitHub issue creation on a GitHub origin:
# classify via git-origin-host.sh, prompt only on github, show the count, default
# No, consent-gate /issues-from-plan, and skip non-interactively. Doc gate.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/plan/SKILL.md"

@test "step 6 classifies the origin via git-origin-host.sh" {
  grep -q 'git-origin-host.sh' "$SKILL"
}

@test "prompts only on a github origin" {
  grep -qi 'github.*origin only\|GitHub origin only\|only.*offer issue creation on an actual GitHub host' "$SKILL"
}

@test "shows the issue count in the prompt" {
  grep -qi 'parent issue and N linked' "$SKILL"
}

@test "default is No" {
  grep -q '\[y/N\]' "$SKILL"
  grep -qi 'default is \*\*No\*\*\|default is No' "$SKILL"
}

@test "invokes /issues-from-plan only on explicit consent" {
  grep -qi 'only on explicit' "$SKILL"
  grep -q 'issues-from-plan' "$SKILL"
}

@test "other / none origins do not prompt" {
  grep -qi 'no prompt' "$SKILL"
}

@test "non-interactive skips without blocking" {
  grep -qi 'non-interactive' "$SKILL"
  grep -qi 'skipping the GitHub issue prompt' "$SKILL"
}
