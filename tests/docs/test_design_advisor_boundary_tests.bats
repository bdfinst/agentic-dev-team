#!/usr/bin/env bats
# Structural contract for the test-design-advisor SKILL (#534).
# Under /test-design, the smell agent has already named the smell and its
# family; Steps 3b and 3c supply the specific remedy pattern.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design-advisor/SKILL.md"

@test "advisor SKILL exists" {
  [ -f "$SKILL" ]
}

@test "Step 3b acknowledges the smell-review boundary under /test-design" {
  # A sentence within the fixture-remedy step stating that under /test-design
  # the smell agent has already named the smell and its family.
  # The check spans Step 3b's paragraph; both cues must appear in the file
  # and near each other (verified by doc-lint gate).
  awk '/### 3b\./,/### 3c\./' "$SKILL" > /tmp/step-3b.txt
  grep -Eqi 'under.*/test-design.*smell.*(named|already)|smell agent.*(already|has).*named' /tmp/step-3b.txt
  grep -Eqi 'family|remedyFamily' /tmp/step-3b.txt
}

@test "Step 3c acknowledges the smell-review boundary under /test-design" {
  awk '/### 3c\./,/### 4\./' "$SKILL" > /tmp/step-3c.txt
  grep -Eqi 'under.*/test-design.*smell.*(named|already)|smell agent.*(already|has).*named' /tmp/step-3c.txt
  grep -Eqi 'family|remedyFamily' /tmp/step-3c.txt
}
