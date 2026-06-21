#!/usr/bin/env bats
# Stale-reference guard for the effort-band routing migration. The canonical
# routing docs must describe the effort/ladder model and must NOT:
#   - use `complexity:` as the frontmatter band key (the spec's old wording),
#   - present `model: <tier>` as the frontmatter contract (a frontmatter-style
#     line; legitimate inline prose about the deprecated form is allowed),
#   - mention any file removed by this migration (the probe, the overrides
#     cache, the retired SessionStart banner, the /v1/models endpoint).
#
# ADR 0004 and the CHANGELOG are intentionally NOT scanned: they are immutable
# historical records (ADR 0004 carries an "Amended by 0008" banner).
# AC8.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# Canonical, current-facing routing docs.
FILES=(
  "CLAUDE.md"
  "plugins/dev-team/CLAUDE.md"
  "plugins/dev-team/docs/model-routing.md"
  "plugins/dev-team/docs/model-routing-overrides.md"
  "plugins/dev-team/docs/agent-architecture.md"
  "plugins/dev-team/docs/concurrent-use.md"
  "plugins/dev-team/docs/session-review.md"
  "plugins/dev-team/agents/orchestrator.md"
  "plugins/dev-team/skills/model-routing-check/SKILL.md"
  "plugins/dev-team/skills/session-review/SKILL.md"
  "plugins/dev-team/skills/init-dev-team/SKILL.md"
  "docs/specs/model-complexity-routing.md"
  "docs/adr/0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md"
)

@test "no canonical routing doc mentions a removed file" {
  local f hit fails=""
  for f in "${FILES[@]}"; do
    [ -f "$REPO_ROOT/$f" ] || continue
    hit=$(grep -nE 'model-probe|overrides-banner\.sh|model-overrides|/v1/models' "$REPO_ROOT/$f" || true)
    [ -z "$hit" ] || fails="$fails"$'\n'"$f:"$'\n'"$hit"
  done
  [ -z "$fails" ] || { echo "Removed-file references found:$fails"; false; }
}

@test "no canonical routing doc uses complexity: as the band key" {
  local f hit fails=""
  for f in "${FILES[@]}"; do
    [ -f "$REPO_ROOT/$f" ] || continue
    hit=$(grep -nE 'complexity:[[:space:]]*(low|medium|high)' "$REPO_ROOT/$f" || true)
    [ -z "$hit" ] || fails="$fails"$'\n'"$f:"$'\n'"$hit"
  done
  [ -z "$fails" ] || { echo "Stale complexity: band key found:$fails"; false; }
}

@test "no canonical routing doc presents model: <tier> as the frontmatter contract" {
  # Frontmatter-style line (optional leading whitespace, then `model:`); inline
  # prose mentioning the deprecated form mid-line is allowed.
  local f hit fails=""
  for f in "${FILES[@]}"; do
    [ -f "$REPO_ROOT/$f" ] || continue
    hit=$(grep -nE '^[[:space:]]*model:[[:space:]]*(haiku|sonnet|opus)\b' "$REPO_ROOT/$f" || true)
    [ -z "$hit" ] || fails="$fails"$'\n'"$f:"$'\n'"$hit"
  done
  [ -z "$fails" ] || { echo "model: <tier> presented as the contract:$fails"; false; }
}

@test "the routing contract doc and override guide describe the effort/ladder model" {
  grep -qi 'effort' "$REPO_ROOT/plugins/dev-team/docs/model-routing.md"
  grep -qi 'ladder' "$REPO_ROOT/plugins/dev-team/docs/model-routing.md"
}
