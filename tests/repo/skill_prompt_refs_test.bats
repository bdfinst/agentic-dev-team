#!/usr/bin/env bats
# Skill → prompt-template reference sensor (issue #173).
#
# Shipped SKILL.md files dispatch sub-agents seeded from prompt templates that
# live at the PLUGIN ROOT (plugins/dev-team/prompts/). A bare `prompts/X.md`
# reference is ambiguous — at runtime the model resolved it skill-relative,
# found nothing, and fell back to inline persona briefs (#173). This sensor
# keeps every such reference (a) resolvable to a real file and (b) written in
# the explicit `${CLAUDE_PLUGIN_ROOT}/prompts/...` form so it can't regress.
#
# Scope: shipped skills only — plugins/dev-team/skills/**/SKILL.md.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SKILLS_DIR="$REPO_ROOT/plugins/dev-team/skills"
PROMPTS_DIR="$REPO_ROOT/plugins/dev-team/prompts"

@test "every prompts/<name>.md reference in a SKILL.md resolves to a real template" {
  local missing=""
  while IFS= read -r line; do
    local file="${line%%:*}"
    local name
    name="$(printf '%s' "$line" | grep -oE 'prompts/[a-zA-Z0-9_-]+\.md' | head -1 | sed 's#prompts/##')"
    [ -n "$name" ] || continue
    if [ ! -f "$PROMPTS_DIR/$name" ]; then
      missing="${missing}\n  ${file#"$REPO_ROOT"/}: prompts/$name (not found at plugins/dev-team/prompts/)"
    fi
  done < <(grep -rn "prompts/[a-zA-Z0-9_-]*\.md" "$SKILLS_DIR" --include='SKILL.md')

  if [ -n "$missing" ]; then
    echo "Unresolvable prompt-template reference(s):" >&2
    echo -e "$missing" >&2
    echo "Move the template under plugins/dev-team/prompts/ or fix the reference." >&2
    return 1
  fi
}

@test "prompt-template references use the explicit \${CLAUDE_PLUGIN_ROOT}/prompts/ form" {
  # A bare `prompts/X.md` (not preceded by CLAUDE_PLUGIN_ROOT/) is the ambiguous
  # form that caused #173. Require the plugin-root-explicit prefix.
  local bare=""
  while IFS= read -r line; do
    # Strip the CLAUDE_PLUGIN_ROOT-prefixed occurrences, then see if a bare
    # `prompts/X.md` still remains on the line.
    local stripped="${line//\$\{CLAUDE_PLUGIN_ROOT\}\/prompts\//__OK__}"
    if printf '%s' "$stripped" | grep -qE 'prompts/[a-zA-Z0-9_-]+\.md'; then
      bare="${bare}\n  ${line}"
    fi
  done < <(grep -rn "prompts/[a-zA-Z0-9_-]*\.md" "$SKILLS_DIR" --include='SKILL.md')

  if [ -n "$bare" ]; then
    echo "Ambiguous bare prompts/ reference(s) — use \${CLAUDE_PLUGIN_ROOT}/prompts/<name>.md:" >&2
    echo -e "$bare" >&2
    return 1
  fi
}
