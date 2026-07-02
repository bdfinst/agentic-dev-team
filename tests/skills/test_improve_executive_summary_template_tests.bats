#!/usr/bin/env bats
# Contract for the /test-improve executive-summary template shipped with
# the skill. Issue #536, Slice 10 Step 10.1.

TEMPLATE="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/templates/executive-summary.md"

@test "executive-summary template exists" {
  [ -f "$TEMPLATE" ]
}

@test "template contains all 10 numbered section headers" {
  grep -Eq '^## 1\. Bottom line'                                          "$TEMPLATE"
  grep -Eq '^## 2\. What was done this run'                               "$TEMPLATE"
  grep -Eq '^## 3\. What was measured'                                    "$TEMPLATE"
  grep -Eq '^## 4\. Findings from'                                        "$TEMPLATE"
  grep -Eq '^## 5\. Work completed \(Phase 4 — no refactoring\)'         "$TEMPLATE"
  grep -Eq '^## 6\. Work completed \(Phase 5 — refactor-for-testability\)' "$TEMPLATE"
  grep -Eq '^## 7\. Deferred work'                                        "$TEMPLATE"
  grep -Eq '^## 8\. Waivers'                                              "$TEMPLATE"
  grep -Eq '^## 9\. Next actions'                                         "$TEMPLATE"
  grep -Eq '^## 10\. Provenance'                                          "$TEMPLATE"
}

@test "template § 1 carries the baseline / achieved / delta metric table shape" {
  grep -Eqi 'baseline' "$TEMPLATE"
  grep -Eqi 'achieved|current' "$TEMPLATE"
  grep -Eqi 'delta|Δ|change' "$TEMPLATE"
  grep -Eq '\|' "$TEMPLATE"
}

@test "template carries the Go advisory footnote" {
  grep -Eqi 'go-mutesting.*alpha|alpha.*go-mutesting' "$TEMPLATE"
  grep -Eqi 'advisory' "$TEMPLATE"
}

@test "template carries the mutation-disabled placeholder text" {
  grep -Eqi 'mutation[[:space:]]+disabled|not[[:space:]]+applicable.*mutation' "$TEMPLATE"
}

@test "template carries the 'Not applicable' placeholder for empty sections" {
  grep -Eqi 'not[[:space:]]+applicable' "$TEMPLATE"
}
