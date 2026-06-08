#!/usr/bin/env bats
# #222 — the /plan skill must render the parallelization structure: per-slice
# Depends-on, a ## Parallelization section (Mermaid DAG + wave table), and a
# wave-grouped Build Progress. Documentation gate for slice 1's rendering.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/plan/SKILL.md"

@test "plan skill exists" {
  [ -f "$SKILL" ]
}

@test "slice template declares a slice-level Depends-on field" {
  grep -q '\*\*Depends-on:\*\*' "$SKILL"
}

@test "slice template declares a slice-level Files surface" {
  grep -q '\*\*Files:\*\*' "$SKILL"
}

@test "plan renders a ## Parallelization section" {
  grep -q '^## Parallelization' "$SKILL"
}

@test "Parallelization section references the wave computer (plan-waves.sh)" {
  grep -q 'plan-waves.sh' "$SKILL"
}

@test "Parallelization section contains a Mermaid DAG and a wave table" {
  grep -q 'mermaid' "$SKILL"
  grep -q '| Wave | Slices' "$SKILL"
}

@test "Build Progress groups slices by wave" {
  grep -q 'grouped by wave' "$SKILL"
  grep -q '#### Wave 1' "$SKILL"
}

@test "plan flow tells the author to fix same-wave collisions before the gate" {
  grep -qi 'collision' "$SKILL"
}
