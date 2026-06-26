#!/usr/bin/env bats
# Content contract for the BDD value-decision guide (epic #443, issue #435).
# A reusable rubric for when BDD/Gherkin adds value vs. ceremony overhead.

GUIDE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/references/bdd-value-guide.md"

@test "bdd-value-guide.md exists" {
  [ -f "$GUIDE" ]
}

@test "rubric covers all five decision questions" {
  # Five yes/no signals: stakeholders, business-domain, collaborative authoring,
  # living-documentation, existing Gherkin.
  grep -qi 'stakeholder' "$GUIDE"
  grep -qi 'business domain' "$GUIDE"
  grep -Eqi 'three.amigos|collaborative' "$GUIDE"
  grep -qi 'living.documentation' "$GUIDE"
  grep -qi 'existing Gherkin' "$GUIDE"
}

@test "recommendation mapping defines all three binding modes" {
  grep -q 'bdd-runner' "$GUIDE"
  grep -q 'xunit-with-annotations' "$GUIDE"
  # the third mode is plain xunit / none
  grep -Eq '`none`|\bnone\b' "$GUIDE"
}

@test "recommendation mapping is score-banded (>=3 / 1-2 / 0)" {
  grep -Eq '≥ ?3|>= ?3|3\+ yes' "$GUIDE"
  grep -Eq '1.2 yes|1.{0,3}2' "$GUIDE"
  grep -Eq '0 yes' "$GUIDE"
}

@test "guide has both 'overkill' and 'worth it' guidance sections" {
  grep -Eqi 'overkill|almost always overkill' "$GUIDE"
  grep -Eqi 'worth it|almost always worth' "$GUIDE"
}

@test "overkill guidance names concrete cases (technical layers, small team, spike)" {
  grep -Eqi 'utilit|data mapper|infrastructure adapter' "$GUIDE"
  grep -Eqi 'spike|prototype|short-lived' "$GUIDE"
}

@test "worth-it guidance names concrete cases (regulated domain, shared-language gap)" {
  grep -Eqi 'regulated|payments|healthcare|compliance' "$GUIDE"
  grep -Eqi 'shared.language|misaligned' "$GUIDE"
}
