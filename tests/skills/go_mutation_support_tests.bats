#!/usr/bin/env bats
# Doc-shape contract for Go mutation testing support (epic #443, issue #434).
# A Go project must get an actionable path — go-mutesting in advisory mode plus
# the go test -fuzz complement — never a bare "no tool installed".

PLUGIN="$BATS_TEST_DIRNAME/../../plugins/dev-team"
DETECTION="$PLUGIN/skills/mutation-testing/references/tool-detection.md"
GO_KB="$PLUGIN/skills/mutation-testing/references/languages/go-go-mutesting.md"
SKILL="$PLUGIN/skills/mutation-testing/SKILL.md"

# --- tool-detection.md: Go row in the ecosystem router ----------------------

@test "tool-detection: row has a Go entry naming go-mutesting" {
  grep -qi 'go-mutesting' "$DETECTION"
  grep -Eq '\| *Go *\|' "$DETECTION"
}

@test "tool-detection: Go detection keys on go.mod" {
  run grep -E 'go\.mod' "$DETECTION"
  [ "$status" -eq 0 ]
}

# --- languages/go-go-mutesting.md: install / run / advisory / fuzz ----------

@test "go-go-mutesting: documents the go-mutesting install command" {
  run grep -E 'go install .*go-mutesting' "$GO_KB"
  [ "$status" -eq 0 ]
}

@test "go-go-mutesting: documents the go-mutesting run command" {
  run grep -E 'go-mutesting \./\.\.\.' "$GO_KB"
  [ "$status" -eq 0 ]
}

@test "go-go-mutesting: marks go-mutesting advisory-only" {
  run grep -Eqi 'advisory' "$GO_KB"
  [ "$status" -eq 0 ]
}

@test "go-go-mutesting: documents the go test -fuzz complement" {
  run grep -E 'go test -fuzz' "$GO_KB"
  [ "$status" -eq 0 ]
}

@test "go-go-mutesting: machine-readable example carries advisory: true" {
  # The schema mapping section must show the Go envelope with advisory true so
  # downstream callers warn rather than halt.
  run grep -Eq '"advisory": *true' "$GO_KB"
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
