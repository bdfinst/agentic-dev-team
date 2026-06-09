#!/usr/bin/env bats
# Shipped-script / hook reference sensor — security-assessment plugin.
#
# Companion to shipped_script_refs_test.bats (which guards plugins/dev-team).
# Same bug class: a shipped skill, agent, or command references a helper script
# or tool by a path that resolves in THIS dev monorepo but not inside the
# INSTALLED plugin. Skills/agents/commands are executed by the agent from the
# USER's working directory, not the plugin root, so any script they invoke must
# be addressed as ${CLAUDE_PLUGIN_ROOT}/<path> to be discoverable once installed.
# (settings.json hook commands are the exception — the harness runs those from
# the plugin root, so the bare `hooks/<name>` form is correct and is checked to
# resolve under the plugin in the last test.)
#
# Four invariants, each model-free and deterministic:
#   1. every ${CLAUDE_PLUGIN_ROOT}/(scripts|hooks|tools|harness)/<path> reference
#      in a shipped file resolves to a real file under plugins/security-assessment/;
#   2. no shipped file uses the plugin-escaping ${CLAUDE_PLUGIN_ROOT}/../../ form;
#   3. every hook command registered in settings.json resolves to a shipped file;
#   4. no build/test tooling is shipped inside the plugin (the test suite lives
#      at tests/security-assessment/, the semgrep audit at repo-root scripts/).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLUGIN="$REPO_ROOT/plugins/security-assessment"
SHIPPED_DIRS=("$PLUGIN/skills" "$PLUGIN/agents" "$PLUGIN/commands" "$PLUGIN/hooks" "$PLUGIN/harness")

@test "every \${CLAUDE_PLUGIN_ROOT}/(scripts|hooks|tools|harness)/ reference resolves to a shipped file" {
  local missing=""
  while IFS= read -r ref; do
    [ -n "$ref" ] || continue
    local rel="${ref#\$\{CLAUDE_PLUGIN_ROOT\}/}"
    if [ ! -e "$PLUGIN/$rel" ]; then
      missing="${missing}\n  $rel  (referenced but not present under plugins/security-assessment/)"
    fi
  done < <(grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/(scripts|hooks|tools|harness)/[a-zA-Z0-9_./-]+\.(sh|py|md)' "${SHIPPED_DIRS[@]}" 2>/dev/null | sort -u)

  if [ -n "$missing" ]; then
    echo "Unresolvable shipped script/tool reference(s):" >&2
    echo -e "$missing" >&2
    echo "Add the file under plugins/security-assessment/ or correct the reference." >&2
    return 1
  fi
}

@test "no shipped file escapes the plugin via \${CLAUDE_PLUGIN_ROOT}/../.." {
  local offenders=""
  while IFS= read -r line; do
    local file="${line%%:*}"
    local relpath="${file#"$PLUGIN"/}"
    offenders="${offenders}\n  ${relpath}: ${line#*:}"
  done < <(grep -rnE '\$\{CLAUDE_PLUGIN_ROOT\}/\.\./' "${SHIPPED_DIRS[@]}" 2>/dev/null)

  if [ -n "$offenders" ]; then
    echo "Plugin-escaping reference(s) — won't resolve in an installed plugin:" >&2
    echo -e "$offenders" >&2
    echo "Move the helper under plugins/security-assessment/ and use \${CLAUDE_PLUGIN_ROOT}/<path>." >&2
    return 1
  fi
}

@test "every hook command in settings.json resolves to a shipped file" {
  local settings="$PLUGIN/settings.json"
  [ -f "$settings" ] || skip "no settings.json"
  local missing=""
  while IFS= read -r cmd; do
    [ -n "$cmd" ] || continue
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

@test "no build/test scripts are shipped inside the plugin" {
  # Test runners, test cases, and CI/audit tooling must live outside the plugin
  # tree (the plugin ships wholesale via its git-subdir source). The shell test
  # suite lives at tests/security-assessment/; the semgrep-fixtures audit at
  # repo-root scripts/audit-semgrep-fixtures.py.
  local offenders
  offenders="$(find "$PLUGIN" -type f \( -name '*.test.sh' -o -name '*_test.sh' -o -name '*.bats' -o -name 'run-all.sh' -o -name 'audit-semgrep-fixtures.py' \) 2>/dev/null)"
  if [ -n "$offenders" ]; then
    echo "Build/test script(s) shipped inside the plugin:" >&2
    echo "$offenders" >&2
    echo "Relocate them outside plugins/security-assessment/ (tests/ or repo-root scripts/)." >&2
    return 1
  fi
}
