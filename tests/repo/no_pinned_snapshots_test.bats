#!/usr/bin/env bats
# AC2 enforcement: no pinned claude-* snapshot IDs anywhere in the repo
# outside the three approved files (the single source of truth + its docs).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# The three plugin-source files allowed to contain a pinned snapshot ID:
#   knowledge/model-routing.json — single source of truth (the whole point)
#   docs/model-routing.md       — contract doc; illustrative examples
#   templates/agents/agent-template.md — commented documentation block
#
# Out-of-scope (legitimate references the AC does not police):
#   docs/specs/, plans/, docs/spikes/ — design artifacts that name the
#     values exactly because they describe the migration.
#   evals/ — semgrep fixtures for OTHER plugins' LLM model strings.
#   tests/  — bats fixtures that depend on the literal values.
ALLOWED_PATHS=(
  "plugins/dev-team/knowledge/model-routing.json"
  "plugins/dev-team/docs/model-routing.md"
  "plugins/dev-team/templates/agents/agent-template.md"
)

@test "AC2: no pinned snapshot IDs in plugin source outside approved files" {
  cd "$REPO_ROOT"
  local raw
  raw=$(git grep -nE 'claude-(haiku|sonnet|opus)-[0-9]' -- \
    'plugins/' \
    ':!plugins/dev-team/knowledge/model-routing.json' \
    ':!plugins/dev-team/docs/model-routing.md' \
    ':!plugins/dev-team/templates/agents/agent-template.md' \
    2>/dev/null || true)
  if [[ -n "$raw" ]]; then
    echo "Pinned snapshot IDs found in non-approved plugin source files:" >&2
    echo "$raw" >&2
    return 1
  fi
}
