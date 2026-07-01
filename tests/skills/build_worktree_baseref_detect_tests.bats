#!/usr/bin/env bats
# Issue #553 — plans/build-worktree-inherits-caller-head.md Slice 1.
#
# Step 1.1: plugins/dev-team/scripts/build-worktree-baseref.sh `detect`
# subcommand. Prints exactly one of head|fresh|unset|unknown and exits 0
# (degrade-never-abort — mirrors hooks/lib/model-resolve.sh's precedent).
#
# Env var seam (test-only injection, mirrors MODEL_ROUTING_JSON/
# MODEL_LADDER_JSON in model-resolve.sh):
#   BASEREF_SETTINGS_PATHS — colon-separated list of settings files,
#   highest precedence first. When unset, the script falls back to its
#   real default order (.claude/settings.json → ~/.claude/settings.json).
#
# Step 1.2: SKILL.md Step 4 documents the pre-dispatch detect-and-warn
# wire-up. Doc-grep tests only — no subagent dispatch from bats.

load '../lib/hermetic'

SCRIPT="$BATS_TEST_DIRNAME/../../plugins/dev-team/scripts/build-worktree-baseref.sh"
BUILD_SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/build/SKILL.md"

setup() {
  hermetic_setup
}

teardown() {
  hermetic_teardown
}

# ---------------------------------------------------------------------------
# Step 1.1 — detect subcommand
# ---------------------------------------------------------------------------

@test "detect: explicit head in the highest-precedence file prints head" {
  cat > "$HERMETIC_ROOT/settings.json" <<'EOF'
{"worktree": {"baseRef": "head"}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/settings.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "head" ]
}

@test "detect: explicit fresh in the highest-precedence file prints fresh" {
  cat > "$HERMETIC_ROOT/settings.json" <<'EOF'
{"worktree": {"baseRef": "fresh"}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/settings.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "fresh" ]
}

@test "detect: key absent from every file prints unset (not unknown)" {
  cat > "$HERMETIC_ROOT/settings.json" <<'EOF'
{"permissions": {}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/settings.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "unset" ]
}

@test "detect: no settings files exist at all prints unset" {
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/does-not-exist.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "unset" ]
}

@test "detect: malformed JSON in the highest-precedence file falls back to a lower valid file" {
  cat > "$HERMETIC_ROOT/broken.json" <<'EOF'
{not valid json
EOF
  cat > "$HERMETIC_ROOT/valid.json" <<'EOF'
{"worktree": {"baseRef": "head"}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/broken.json:$HERMETIC_ROOT/valid.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "head" ]
}

@test "detect: jq unavailable prints unknown and exits 0" {
  # Build a minimal PATH of shim dirs containing every binary the script
  # and bash itself need (bash, cat, echo, printf, test, ...) EXCEPT jq —
  # symlinking individual tools avoids /bin and /usr/bin, both of which
  # ship a real jq on stock macOS.
  shim_dir="$HERMETIC_ROOT/shims"
  mkdir -p "$shim_dir"
  for tool in bash sh cat echo printf test "[" true false grep sed awk mktemp env; do
    src="$(command -v "$tool" 2>/dev/null)" || continue
    ln -sf "$src" "$shim_dir/$tool"
  done
  cat > "$HERMETIC_ROOT/settings.json" <<'EOF'
{"worktree": {"baseRef": "head"}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/settings.json" PATH="$shim_dir" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  [ "$output" = "unknown" ]
}

@test "detect: prints exactly one line" {
  cat > "$HERMETIC_ROOT/settings.json" <<'EOF'
{"worktree": {"baseRef": "fresh"}}
EOF
  BASEREF_SETTINGS_PATHS="$HERMETIC_ROOT/settings.json" run bash "$SCRIPT" detect
  [ "$status" -eq 0 ]
  line_count="$(printf '%s' "$output" | wc -l | tr -d ' ')"
  # `wc -l` counts newlines; a single line with no trailing newline in
  # $output (bats strips it) counts as 0 newlines — accept 0 or 1.
  [ "$line_count" -le 1 ]
}

@test "detect: unknown subcommand exits non-zero with usage" {
  run bash "$SCRIPT" bogus
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# Step 1.2 — /build Step 4 wire-up (doc-grep — no subagent dispatch)
# ---------------------------------------------------------------------------

@test "SKILL.md Step 4 documents a pre-dispatch base-ref check" {
  grep -qi 'build-worktree-baseref.sh' "$BUILD_SKILL"
  grep -qi 'base-ref check' "$BUILD_SKILL"
}

@test "SKILL.md Step 4 base-ref check mentions the settings file, the setting, head, and the opt-out env var" {
  section=$(awk '/^### 4\. /{f=1} f{print} /^### 5\. /{f=0}' "$BUILD_SKILL")
  echo "$section" | grep -qF '.claude/settings.json'
  echo "$section" | grep -qF 'worktree.baseRef'
  echo "$section" | grep -qF 'head'
  echo "$section" | grep -qF 'DEV_TEAM_WORKTREE_BASE_FRESH'
}

@test "SKILL.md Step 4 base-ref check includes a paste-ready JSON snippet" {
  section=$(awk '/^### 4\. /{f=1} f{print} /^### 5\. /{f=0}' "$BUILD_SKILL")
  echo "$section" | grep -qF '"worktree"'
  echo "$section" | grep -qF '"baseRef"'
}

@test "SKILL.md Step 4 states the check runs in the top-level session before any subagent dispatch" {
  section=$(awk '/^### 4\. /{f=1} f{print} /^### 5\. /{f=0}' "$BUILD_SKILL")
  echo "$section" | grep -qi 'before any subagent dispatch\|before dispatch'
  echo "$section" | grep -qi 'top-level'
}

@test "SKILL.md Step 4 states /build never mutates a settings file" {
  section=$(awk '/^### 4\. /{f=1} f{print} /^### 5\. /{f=0}' "$BUILD_SKILL")
  echo "$section" | grep -qi 'never mutat\|no.*mutation\|does not mutate\|no settings mutation'
}
