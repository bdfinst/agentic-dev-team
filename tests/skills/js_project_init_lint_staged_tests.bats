#!/usr/bin/env bats
# #250 — js-project-init must scaffold lint-staged with a pre-commit auto-fix hook
# and simplify the pre-push hook to the test suite only. Documentation gate over
# the skill prose and its config templates.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/js-project-init/SKILL.md"
CFG="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/js-project-init/references/configs.md"

@test "package.json template declares a lint-staged block with per-extension fix commands" {
  grep -q '"lint-staged"' "$SKILL"
  grep -q '"\*.{js,mjs,cjs}": \["prettier --write", "eslint --fix"\]' "$SKILL"
  grep -q '"\*.{json,md,yaml,yml}": \["prettier --write"\]' "$SKILL"
}

@test "lint-staged is added to the dev dependency install" {
  grep -q 'npm install -D .*lint-staged' "$SKILL"
}

@test "pre-commit hook runs lint-staged" {
  grep -q "echo 'npx lint-staged' > .husky/pre-commit" "$SKILL"
}

@test "pre-push hook runs npm test" {
  grep -q "echo 'npm test' > .husky/pre-push" "$SKILL"
}

@test "frontend pre-push retains the e2e suite" {
  grep -q 'npm run test:e2e' "$SKILL"
}

@test "step 8 summary lists both git hooks" {
  grep -qi 'pre-commit.*lint-staged' "$SKILL"
  grep -qi 'pre-push.*test' "$SKILL"
}

@test "configs.md pre-commit template contains npx lint-staged" {
  grep -q 'npx lint-staged' "$CFG"
}

@test "configs.md pre-push template contains npm test and no lint/format:check" {
  # Extract the '## .husky/pre-push' section up to the next level-2 heading.
  section=$(awk '/^## \.husky\/pre-push/{f=1;next} /^## /{f=0} f' "$CFG")
  echo "$section" | grep -q 'npm test'
  ! echo "$section" | grep -q 'format:check'
  ! echo "$section" | grep -qw 'npm run lint'
}
