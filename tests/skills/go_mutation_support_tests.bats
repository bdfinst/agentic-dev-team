#!/usr/bin/env bats
# Doc-shape contract for Go mutation testing support (epic #443, issue #434).
# A Go project must get an actionable path — go-mutesting in advisory mode plus
# the go test -fuzz complement — never a bare "no tool installed".

PLUGIN="$BATS_TEST_DIRNAME/../../plugins/dev-team"
SETUP="$PLUGIN/skills/mutation-testing/references/tool-setup.md"
SKILL="$PLUGIN/skills/mutation-testing/SKILL.md"

# --- tool-setup.md: Go detection / install / run / advisory -----------------

@test "tool-setup: detection table has a Go row naming go-mutesting" {
  grep -qi 'go-mutesting' "$SETUP"
  grep -Eq '\| *Go *\|' "$SETUP"
}

@test "tool-setup: Go detection keys on go.mod" {
  run grep -E 'go\.mod' "$SETUP"
  [ "$status" -eq 0 ]
}

@test "tool-setup: documents the go-mutesting install command" {
  run grep -E 'go install .*go-mutesting' "$SETUP"
  [ "$status" -eq 0 ]
}

@test "tool-setup: documents the go-mutesting run command" {
  run grep -E 'go-mutesting \./\.\.\.' "$SETUP"
  [ "$status" -eq 0 ]
}

@test "tool-setup: marks go-mutesting advisory-only" {
  run grep -Eqi 'advisory' "$SETUP"
  [ "$status" -eq 0 ]
}

@test "tool-setup: documents the go test -fuzz complement" {
  run grep -E 'go test -fuzz' "$SETUP"
  [ "$status" -eq 0 ]
}

@test "tool-setup: Go machine-readable example carries advisory: true" {
  # The schema mapping section must show the Go envelope with advisory true so
  # downstream callers warn rather than halt.
  run grep -Eq '"advisory": *true' "$SETUP"
  [ "$status" -eq 0 ]
}

# --- SKILL.md: Step 1 detection + advisory mode -----------------------------

@test "mutation-testing SKILL: Step 1 detection names go.mod -> go-mutesting" {
  body=$(awk '/^## Step 1: Detect/{f=1;next} /^## Step 1b/{f=0} f' "$SKILL")
  echo "$body" | grep -qi 'go-mutesting'
  echo "$body" | grep -qi 'go\.mod'
}

@test "mutation-testing SKILL: advisory mode is documented as non-blocking" {
  run grep -Eqi 'advisory' "$SKILL"
  [ "$status" -eq 0 ]
  # advisory: true must appear so orchestrated workflows know not to halt.
  run grep -Eq '"advisory": *true|advisory.*does not block|does not block.*advisory|warn, do not block' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "mutation-testing SKILL: documents the fuzz complement for Go" {
  run grep -E 'go test -fuzz' "$SKILL"
  [ "$status" -eq 0 ]
}
