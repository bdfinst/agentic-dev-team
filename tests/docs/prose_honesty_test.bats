#!/usr/bin/env bats
# Prose-honesty gate (issue #100).
#
# "Prose a deterministic gate touches stays clean; prose no sensor reaches
# rots." This test IS that sensor for the flagship CLAUDE.md and sibling
# shipped docs: it fails loudly if metaphor-as-mechanism buzzwords or
# un-instrumented numeric targets reappear in shipped prose.
#
# Scope: shipped prose only — plugins/dev-team/**/*.md. Non-shipped docs
# (repo-level docs/, plans/, evals/) are out of scope.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLUGIN_DOCS="$REPO_ROOT/plugins/dev-team"
CLAUDE_MD="$PLUGIN_DOCS/CLAUDE.md"

# Metaphor-as-mechanism phrases: borrowed jargon describing a mechanism the
# code does not implement. Add to this list as new ones are caught.
BANNED_PHRASES=(
  "federated learning"
  "LSTM-inspired"
  "LSTM inspired"
)

@test "no metaphor-as-mechanism buzzwords in shipped plugin prose" {
  local hits=""
  while IFS= read -r -d '' file; do
    for phrase in "${BANNED_PHRASES[@]}"; do
      if grep -iqF "$phrase" "$file"; then
        hits="${hits}\n  ${file#"$REPO_ROOT"/}: \"$phrase\""
      fi
    done
  done < <(find "$PLUGIN_DOCS" -name '*.md' -print0)

  if [ -n "$hits" ]; then
    echo "Banned metaphor-as-mechanism prose found (replace with a literal" >&2
    echo "description of the mechanism, or delete):" >&2
    echo -e "$hits" >&2
    return 1
  fi
}

@test "no bare un-instrumented numeric targets in shipped plugin prose" {
  # These were the un-falsifiable Targets removed in #100 — originally from
  # CLAUDE.md, but they also lived in sibling shipped docs (performance-metrics
  # and governance-compliance skills). The sensor scans ALL shipped prose, not
  # just CLAUDE.md: a target with no instrument must not ship anywhere. If a
  # number is real, move it under "Claims discipline" naming its instrument.
  # Add to this list as new ones are caught.
  local banned_targets=(
    "10-15% overall efficiency gains"
    "< 5% hallucination rate"
    "95% accuracy on structured data extraction"
    "> 80% first-pass acceptance rate"
    "< 5% of tasks"
    "< 5% of total task tokens"
    "> 50% reduction"
    "within target (< 5%)"
  )
  local hits=""
  while IFS= read -r -d '' file; do
    for t in "${banned_targets[@]}"; do
      if grep -qF "$t" "$file"; then
        hits="${hits}\n  ${file#"$REPO_ROOT"/}: \"$t\""
      fi
    done
  done < <(find "$PLUGIN_DOCS" -name '*.md' -print0)

  if [ -n "$hits" ]; then
    echo "Un-instrumented numeric target(s) in shipped prose:" >&2
    echo -e "$hits" >&2
    echo "Either delete, or move under 'Claims discipline' naming the instrument." >&2
    return 1
  fi
}

@test "CLAUDE.md states the claims-discipline rule (every number names its instrument)" {
  run grep -iq "must name the instrument" "$CLAUDE_MD"
  [ "$status" -eq 0 ]
}
