#!/usr/bin/env bats
# Shipped-script / hook reference sensor.
#
# The bug this prevents: a shipped skill, agent, or prompt references a helper
# script or hook by a path that resolves in THIS dev monorepo but not inside the
# INSTALLED plugin. The classic form is `${CLAUDE_PLUGIN_ROOT}/../../scripts/x.sh`
# — at dev time CLAUDE_PLUGIN_ROOT is plugins/dev-team/, so `../../scripts/`
# lands on repo-root scripts/; once installed, CLAUDE_PLUGIN_ROOT is the cache
# dir and `../../scripts/` points at a nonexistent sibling. The skill then fails
# silently on the user's machine (plan-waves.sh / git-origin-host.sh, this PR).
#
# Three invariants, each model-free and deterministic:
#   1. every ${CLAUDE_PLUGIN_ROOT}/(scripts|hooks)/<path> reference in a shipped
#      file resolves to a real file under plugins/dev-team/;
#   2. no shipped skill uses the plugin-escaping ${CLAUDE_PLUGIN_ROOT}/../../
#      form — except a documented allowlist of maintainer-only skills;
#   3. every hook command registered in settings.json resolves to a shipped file.
#
# Allowlist (invariant 2): /agent-eval and /session-review are maintainer tools
# that operate on THIS repo's own infrastructure (eval fixtures, session
# transcripts). They only ever run from the dev checkout, where ../../scripts/
# resolves, and their helpers (session_extract.py et al.) are coupled repo-root
# tooling that is intentionally not shipped. A NEW ../../ reference in ANY OTHER
# skill is a shipping bug — add the helper under plugins/dev-team/scripts/ and
# reference it as ${CLAUDE_PLUGIN_ROOT}/scripts/<name> instead of exempting it.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLUGIN="$REPO_ROOT/plugins/dev-team"
SHIPPED_DIRS=("$PLUGIN/skills" "$PLUGIN/agents" "$PLUGIN/prompts")

# Skills permitted to reference repo-root tooling via ../../ (see header).
ESCAPE_ALLOWLIST="skills/agent-eval/ skills/session-review/"

@test "every \${CLAUDE_PLUGIN_ROOT}/(scripts|hooks)/ reference resolves to a shipped file" {
  local missing=""
  while IFS= read -r ref; do
    [ -n "$ref" ] || continue
    local rel="${ref#\$\{CLAUDE_PLUGIN_ROOT\}/}"
    if [ ! -f "$PLUGIN/$rel" ]; then
      missing="${missing}\n  $rel  (referenced but not present under plugins/dev-team/)"
    fi
  done < <(grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/(scripts|hooks)/[a-zA-Z0-9_./-]+\.(sh|py)' "${SHIPPED_DIRS[@]}" 2>/dev/null | sort -u)

  if [ -n "$missing" ]; then
    echo "Unresolvable shipped script/hook reference(s):" >&2
    echo -e "$missing" >&2
    echo "Add the file under plugins/dev-team/ or correct the reference." >&2
    return 1
  fi
}

@test "no shipped skill escapes the plugin via \${CLAUDE_PLUGIN_ROOT}/../.. (outside the allowlist)" {
  local offenders=""
  while IFS= read -r line; do
    local file="${line%%:*}"
    local relpath="${file#"$PLUGIN"/}"
    local allowed=0
    for ok in $ESCAPE_ALLOWLIST; do
      case "$relpath" in "$ok"*) allowed=1 ;; esac
    done
    [ "$allowed" -eq 1 ] && continue
    offenders="${offenders}\n  ${relpath}: ${line#*:}"
  done < <(grep -rnE '\$\{CLAUDE_PLUGIN_ROOT\}/\.\./' "$PLUGIN/skills" 2>/dev/null)

  if [ -n "$offenders" ]; then
    echo "Plugin-escaping reference(s) — won't resolve in an installed plugin:" >&2
    echo -e "$offenders" >&2
    echo "Move the helper under plugins/dev-team/scripts/ and use \${CLAUDE_PLUGIN_ROOT}/scripts/<name>." >&2
    return 1
  fi
}

@test "every hook command in settings.json resolves to a shipped file" {
  local settings="$PLUGIN/settings.json"
  [ -f "$settings" ] || skip "no settings.json"
  local missing=""
  while IFS= read -r cmd; do
    [ -n "$cmd" ] || continue
    # Extract the hooks/... (or scripts/...) path from the command string.
    local path
    path="$(printf '%s' "$cmd" | grep -oE '(\$\{CLAUDE_PLUGIN_ROOT\}/)?(hooks|scripts)/[a-zA-Z0-9_./-]+\.(sh|py)' | head -1)"
    [ -n "$path" ] || continue
    local rel="${path#\$\{CLAUDE_PLUGIN_ROOT\}/}"
    if [ ! -f "$PLUGIN/$rel" ]; then
      missing="${missing}\n  $rel  (registered in settings.json but not present)"
    fi
  done < <(jq -r '.hooks // {} | to_entries[] | .value[] | .hooks[]? | .command' "$settings" 2>/dev/null)

  if [ -n "$missing" ]; then
    echo "Hook command(s) referencing a missing file:" >&2
    echo -e "$missing" >&2
    return 1
  fi
}
