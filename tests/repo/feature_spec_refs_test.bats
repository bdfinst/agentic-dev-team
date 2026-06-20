#!/usr/bin/env bats
# Behavior-spec / bats-contract reference sensor.
#
# The mutation-probe slice ACs (#284-#287) named Gherkin `.feature` specs under
# evals/skills/. Those specs are not eval-grader fixtures — their executable
# enforcement is a bats suite under tests/skills/ (see evals/skills/README.md).
# This guard keeps the two from drifting apart:
#
#   1. every evals/skills/**/*.feature carries an "# Enforced by:" header naming
#      a tests/skills/<name>.bats file that exists;
#   2. that referenced bats file is non-empty (i.e. a real suite, not a stub).
#
# Model-free and deterministic. If a spec's enforcing suite is renamed or
# removed, this fails loudly instead of leaving an orphaned spec on disk.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SPEC_DIR="$REPO_ROOT/evals/skills"

@test "every .feature spec names an existing, non-empty bats contract via '# Enforced by:'" {
  [ -d "$SPEC_DIR" ] || skip "no evals/skills specs present"

  local problems=""
  local feature
  while IFS= read -r feature; do
    [ -n "$feature" ] || continue

    local ref
    ref="$(grep -oE '# Enforced by: tests/skills/[a-zA-Z0-9_./-]+\.bats' "$feature" | head -n1 | sed 's/^# Enforced by: //')"

    if [ -z "$ref" ]; then
      problems="${problems}\n  ${feature#$REPO_ROOT/}  (missing '# Enforced by: tests/skills/<name>.bats' header)"
      continue
    fi
    if [ ! -s "$REPO_ROOT/$ref" ]; then
      problems="${problems}\n  ${feature#$REPO_ROOT/}  ->  $ref  (referenced bats contract missing or empty)"
    fi
  done < <(find "$SPEC_DIR" -name '*.feature' | sort)

  if [ -n "$problems" ]; then
    printf 'Behavior spec(s) not backed by a bats contract:%b\n' "$problems" >&2
    return 1
  fi
}
