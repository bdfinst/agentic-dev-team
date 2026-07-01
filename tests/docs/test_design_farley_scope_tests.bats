#!/usr/bin/env bats
# Regression guard for #533: Farley Score in /test-design must honor
# --path / --since scope and label the score with the scope it was
# computed over.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design/SKILL.md"

@test "test-design SKILL declares the unscoped Farley Score label" {
  run grep -c "Farley Score (all tests)" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL declares the --path Farley Score label" {
  run grep -c "Farley Score (under" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL declares the --since Farley Score label" {
  run grep -c "Farley Score (changed since" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL declares the combined --path + --since label" {
  # e.g. "Farley Score (under <dir>, changed since <ref>)"
  run grep -Ec "Farley Score \(under [^,)]+, changed since" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL documents intersection semantics for combined scope" {
  # Match specific phrases, not the bare word 'both' or 'and' which
  # appear in ordinary prose all over the SKILL.
  run grep -Ec "\\bintersection\\b|the intersection of both sets" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL declares the empty-scope branch" {
  run grep -c "no in-scope test files" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL directs Step 3 to reuse Step 1's resolved file set" {
  run grep -Eci "set (already )?resolved in Step 1|reuse Step 1|already-resolved" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL names Step 1 as the single scope-resolution authority" {
  # Collapse newlines before matching so a soft-wrapped phrase still hits.
  run bash -c "tr '\n' ' ' < \"$SKILL\" | grep -Eci 'single[[:space:]]+scope-resolution authority|one[[:space:]]+scope-resolution authority'"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design SKILL no longer claims Farley is independent of --path / --since" {
  run grep -c "This headline score is independent of" "$SKILL"
  [ "$output" -eq 0 ]
}

@test "test-design SKILL no longer carries the whole-suite stale phrases" {
  run grep -Ec "score always reflects the full suite|Farley Score \\(all existing tests\\)" "$SKILL"
  [ "$output" -eq 0 ]
}
