#!/usr/bin/env bats
# Structural contract for /test-design constraint 3 and its report template (#534).
# Constraint 3 no longer proposes report-time de-duplication of smell/advisor
# remedies; findings join structurally on remedyFamily. The report template
# gains a Suppressed duplicates section for any drops constraint 3 still
# performs (mechanics overlap between test-review and test-smell-review).

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design/SKILL.md"

@test "/test-design SKILL exists" {
  [ -f "$SKILL" ]
}

@test "constraint 3 states the structural join on remedyFamily" {
  # Find constraint 3 (via '3.' heading in Orchestrator constraints), scan it.
  grep -Eqi 'join.*(structurally )?on.*remedyFamily|structural join on remedyFamily|join.*rows.*(on|via).*remedyFamily' "$SKILL"
}

@test "constraint 3 no longer proposes report-time de-duplication of advisor remedies" {
  # The removed language: "preferring the advisor's forward-looking sequence
  # when it subsumes the smell-review note". Must not survive.
  run grep -Eic 'preferring the advisor.*forward-looking sequence|advisor.*subsumes.*smell-review' "$SKILL"
  [ "$output" = "0" ]
}

@test "constraint 3 still keeps the test-review/test-smell-review mechanics rule" {
  grep -Eqi 'test-review.*test-smell-review|test-smell-review.*test-review' "$SKILL"
}

@test "report template includes a Suppressed duplicates section" {
  grep -Fq '### Suppressed duplicates' "$SKILL"
}

@test "Suppressed duplicates section documents the None default" {
  # Reads '_None._' (italic) by default when nothing was dropped.
  grep -Fq '_None._' "$SKILL"
}

@test "Suppressed duplicates section documents the entry format (file:line, what, why)" {
  # Extract the report-template Suppressed-duplicates block. The heading occurs
  # in two places (once inside constraint 3's backtick prose, once as the
  # template heading); we grab lines from every ### Suppressed duplicates
  # occurrence onward to end of file, which is sufficient — the entry-format
  # documentation must live in at least one of them.
  awk '/^### Suppressed duplicates/,/^### Next steps/' "$SKILL" > /tmp/suppressed.txt
  grep -Eqi 'file:line' /tmp/suppressed.txt
  grep -Eqi 'dropped' /tmp/suppressed.txt
  grep -Eqi 'reason|why' /tmp/suppressed.txt
}
