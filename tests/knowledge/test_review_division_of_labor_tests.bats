#!/usr/bin/env bats
# Content contract for knowledge/test-review-division-of-labor.md, covering
# BOTH agent pairs:
#   1. test-review ↔ test-smell-review (pre-existing)
#   2. test-smell-review ↔ test-design-advisor (added for #534)
#
# Owner-assignment correctness (which agent owns which column) is a semantic
# property; the assertions below verify structural presence only. Semantic
# correctness is verified by plan-review reading, not by grep.

DOC="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-review-division-of-labor.md"

@test "test-review-division-of-labor.md exists" {
  [ -f "$DOC" ]
}

# --- Pre-existing pair (regression guards) ---

@test "pre-existing 'The two roles' section survives" {
  grep -Fq '## The two roles' "$DOC"
}

@test "pre-existing 'Shared signals' section survives" {
  grep -Fq '## Shared signals — who reports when both run' "$DOC"
}

@test "pre-existing 'The rule in one line' section survives" {
  grep -Fq '## The rule in one line' "$DOC"
}

# --- New pair: test-smell-review ↔ test-design-advisor (#534) ---

@test "smell-review ↔ advisor remedy-division section heading exists" {
  grep -Fq '## test-smell-review ↔ test-design-advisor — remedy division' "$DOC"
}

@test "remedy-division section documents the Smell name+location column" {
  grep -Eq '\| *Smell name.*location' "$DOC"
}

@test "remedy-division section documents the Severity+confidence column" {
  grep -Eqi '\| *Severity.*confidence' "$DOC"
}

@test "remedy-division section documents the Remedy family column" {
  grep -Eqi '\| *Remedy family' "$DOC"
}

@test "remedy-division section documents the Specific remedy pattern column" {
  grep -Eqi '\| *Specific remedy pattern' "$DOC"
}

@test "remedy-division section documents the Refactor sequence column" {
  grep -Eqi '\| *Refactor sequence' "$DOC"
}

@test "remedy-division section documents the Forward-design placement column" {
  grep -Eqi '\| *Forward-design placement' "$DOC"
}

@test "remedy-division section states the under-/test-design rule" {
  grep -Eqi 'under.*/test-design.*advisor.*owns|advisor.*owns.*remedy.*pattern' "$DOC"
}

@test "remedy-division section states the solo-invocation rule" {
  # The rule spans several lines: "runs solo... it fills the whole row" — check
  # both phrases exist in the file (the doc-lint gate suffices for adjacency).
  grep -Eqi '\bruns solo\b' "$DOC"
  grep -Eqi 'fills the whole row' "$DOC"
}
