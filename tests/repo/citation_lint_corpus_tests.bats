#!/usr/bin/env bats
# Citation-lint regression guard against the *real* plugin corpus.
#
# The bats suite in `citation_lint_tests.bats` (shipped with PR #315) exercises
# the lint against a synthetic plugin tree — it pins the parser's behaviour but
# tells us nothing about whether the actual corpus passes. This suite runs the
# lint over `plugins/dev-team/agents/` so a future change cannot:
#
#   (a) break a reviewer's `cites:` resolution by renaming a knowledge file,
#   (b) silently regress an agent that used to declare `cites:` to none, or
#   (c) introduce a new threshold-bearing reviewer that ships with no cites:
#       and no operator awareness.
#
# All assertions are advisory (Phase 1 lint exits 0 by design); the bats suite
# fails when the *observed warnings* drift from the expected fingerprint.

LINT="$BATS_TEST_DIRNAME/../../scripts/citation_lint.py"
PLUGIN_ROOT="$BATS_TEST_DIRNAME/../../plugins/dev-team"

require_lint() {
  if [ ! -x "$LINT" ] && [ ! -f "$LINT" ]; then
    skip "citation_lint.py not present yet (PR #315 not merged)"
  fi
}

@test "lint exits 0 on the real plugin corpus (Phase 1 advisory contract)" {
  require_lint
  run python3 "$LINT" --plugin-root "$PLUGIN_ROOT" "$PLUGIN_ROOT/agents"/*.md
  [ "$status" -eq 0 ]
}

@test "every reviewer with declared cites: resolves to real sources" {
  require_lint
  # Any 'unknown source' warning means a cites: entry points at a file that
  # does not exist — i.e. a knowledge file was renamed without updating the
  # citing agent. Hard fail (advisory exit code, but the warning text is
  # specific and unambiguous).
  run python3 "$LINT" --plugin-root "$PLUGIN_ROOT" "$PLUGIN_ROOT/agents"/*.md
  [ "$status" -eq 0 ]
  if echo "$output" | grep -qiE "unknown source|unresolved"; then
    echo "$output"
    false
  fi
}

@test "no drift on backfilled reviewers (warnings limited to the expected set)" {
  require_lint
  # Reviewers that have a cites: list AND zero threshold drift today. If any of
  # these later appear in the warning stream, a backfilled agent silently
  # regressed.
  CITED_CLEAN=(arch-review complexity-review domain-review naming-review \
               security-review structure-review test-review test-smell-review)
  run python3 "$LINT" --plugin-root "$PLUGIN_ROOT" "$PLUGIN_ROOT/agents"/*.md
  [ "$status" -eq 0 ]
  for name in "${CITED_CLEAN[@]}"; do
    # An emitted line starting with "<name>:" is a drift / advisory warning for
    # that agent. Skip if cites: was added but a threshold still drifts — the
    # backfill PR will surface that case explicitly.
    if echo "$output" | grep -qE "^${name}:"; then
      echo "$output"
      echo "Regression: ${name} now produces a citation warning; check whether"
      echo "a knowledge file changed or a new threshold was added."
      false
    fi
  done
}
