#!/usr/bin/env bats
# Registry-completeness sensor. knowledge/agent-registry.md (agents + agent-loaded
# skills) and the plugin CLAUDE.md slash-command table (user-invocable skills)
# must stay in sync with the agents/ and skills/ on disk. This is the drift class
# that silently desynced the routing tables (unregistered agents/skills, orphaned
# rows). The check fails loudly so /agent-create, /agent-remove, or a hand-edit
# cannot leave the catalog stale.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK="$REPO_ROOT/scripts/check_registry_sync.py"

# A minimal synthetic plugin tree the script can scan in isolation.
setup() {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/fixture"
  rm -rf "$FIX"
  mkdir -p "$FIX/plugins/dev-team/agents"
  mkdir -p "$FIX/plugins/dev-team/skills/bar"
  mkdir -p "$FIX/plugins/dev-team/knowledge"
  printf -- '---\nname: foo\n---\n' > "$FIX/plugins/dev-team/agents/foo.md"
  printf -- '---\nname: bar\n---\n' > "$FIX/plugins/dev-team/skills/bar/SKILL.md"
  cat > "$FIX/plugins/dev-team/knowledge/agent-registry.md" <<'EOF'
## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Bar | `skills/bar/SKILL.md` | 100 | Orchestrator |
EOF
  printf '# Plugin CLAUDE.md\n' > "$FIX/plugins/dev-team/CLAUDE.md"
}

@test "check passes on the real repository tree" {
  run python3 "$CHECK" --root "$REPO_ROOT"
  [ "$status" -eq 0 ]
}

@test "a fully-registered fixture is in sync" {
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "an agent file with no registry row fails (MISSING)" {
  printf -- '---\nname: extra\n---\n' > "$FIX/plugins/dev-team/agents/extra.md"
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 1 ]
  [[ "$output" == *"MISSING"*"agents/extra.md"* ]]
}

@test "a registry row pointing at a missing file fails (ORPHAN)" {
  # The orphan row must live inside the Review Agents section — agent extraction
  # is scoped there so prose mentions elsewhere are not mistaken for rows.
  cat > "$FIX/plugins/dev-team/knowledge/agent-registry.md" <<'EOF'
## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |
| gone | `agents/gone.md` | orphan row, no file on disk |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Bar | `skills/bar/SKILL.md` | 100 | Orchestrator |
EOF
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ORPHAN"*"agents/gone.md"* ]]
}

@test "a skill with no catalog row fails (MISSING)" {
  mkdir -p "$FIX/plugins/dev-team/skills/baz"
  printf -- '---\nname: baz\n---\n' > "$FIX/plugins/dev-team/skills/baz/SKILL.md"
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 1 ]
  [[ "$output" == *"MISSING"*"skills/baz/SKILL.md"* ]]
}

@test "a slash-command skill catalogued only in CLAUDE.md is in sync" {
  mkdir -p "$FIX/plugins/dev-team/skills/cmd"
  printf -- '---\nname: cmd\n---\n' > "$FIX/plugins/dev-team/skills/cmd/SKILL.md"
  printf '| `/cmd` | `skills/cmd/SKILL.md` | worker | does a thing |\n' \
    >> "$FIX/plugins/dev-team/CLAUDE.md"
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a slash-command skill catalogued only in knowledge/skills-registry.md is in sync" {
  # After the CLAUDE.md size reduction, user-invocable skill paths move from the
  # CLAUDE.md table to knowledge/skills-registry.md. The script must scan that
  # file as a third source so no skills are reported MISSING.
  # Fixture: agent-registry.md has NO skill paths, CLAUDE.md has no skill paths;
  # skills-registry.md has bar/SKILL.md. The script should exit 0 (bar is found
  # via the knowledge file).
  mkdir -p "$FIX/plugins/dev-team/skills/baz"
  printf -- '---\nname: baz\n---\n' > "$FIX/plugins/dev-team/skills/baz/SKILL.md"
  # Overwrite agent-registry to remove bar from Skills Registry
  cat > "$FIX/plugins/dev-team/knowledge/agent-registry.md" <<'EOF'
## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Baz | `skills/baz/SKILL.md` | 100 | Orchestrator |
EOF
  # bar is registered only via knowledge/skills-registry.md, not CLAUDE.md or agent-registry.md
  printf '| `/bar` | `skills/bar/SKILL.md` | worker | does a thing |\n' \
    > "$FIX/plugins/dev-team/knowledge/skills-registry.md"
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}
