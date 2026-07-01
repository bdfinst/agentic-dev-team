#!/usr/bin/env bats
# Doc-shape contract for issues #554, #557, #558, #559 additions to the
# /mutation-testing skill:
#
#   #554/#557 — Step 1c smoke gate (workflow-enforced; halts on Killed=0 with
#               Survived>0; parses mutation-report.json, not stdout)
#   #557      — SolutionPath trap warning + xunit.v3 -> Step 1c link
#   #558      — Long-run inspection section (progress, health, error inspection)
#              + dots reporter recommendation
#   #558/#559 — Shipped wrapper + status-loop pointers, copy-both instruction
#
# Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slices 1, 2, 5.
#
# Pattern mirrors tests/skills/mutation_testing_skill_doc_tests.bats — awk
# section-scanning ignoring fenced code blocks. Prose is the deliverable; these
# guards regress when the contract drifts.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/SKILL.md"
CSHARP="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md"

# =============================================================================
# Slice 1 — SKILL.md · Step 1c smoke gate (#554, #557)
# =============================================================================

@test "SKILL: Step 1c smoke gate section exists between Step 1b and Step 2" {
  # Step 1c must live between Step 1b and Step 2 — otherwise it isn't the
  # workflow-enforced gate the plan promises; it's just prose floating anywhere.
  step1b_line=$(awk '
    /^```/                   { code = !code; next }
    !code && /^## Step 1b/   { print NR; exit }
  ' "$SKILL")
  step1c_line=$(awk '
    /^```/                   { code = !code; next }
    !code && /^## Step 1c/   { print NR; exit }
  ' "$SKILL")
  step2_line=$(awk '
    /^```/                   { code = !code; next }
    !code && /^## Step 2/    { print NR; exit }
  ' "$SKILL")
  [ -n "$step1b_line" ]
  [ -n "$step1c_line" ]
  [ -n "$step2_line" ]
  [ "$step1b_line" -lt "$step1c_line" ]
  [ "$step1c_line" -lt "$step2_line" ]
}

@test "SKILL: Step 1c names Killed==0 Survived>0 failure signature" {
  run awk '
    /^```/                     { code = !code; next }
    !code && /^## Step 1c/     { f=1; next }
    !code && /^## /            { f=0 }
    f && /Killed/ && /Survived/ && /0/ { found=1 }
    END                        { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c names mutation-report.json as the parse source" {
  run awk '
    /^```/                     { code = !code; next }
    !code && /^## Step 1c/     { f=1; next }
    !code && /^## /            { f=0 }
    f && /mutation-report\.json/ { found=1 }
    END                        { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c warns against parsing stdout / ANSI progress reporter" {
  # The whole point of the gate is deterministic parsing — must call out that
  # stdout / ANSI progress reporter is NOT the source.
  run awk '
    /^```/                     { code = !code; next }
    !code && /^## Step 1c/     { f=1; next }
    !code && /^## /            { f=0 }
    f && /(stdout|progress reporter|ANSI)/ { found=1 }
    END                        { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c halt message references #554 and #557" {
  run awk '
    /^```/                     { code = !code; next }
    !code && /^## Step 1c/     { f=1; next }
    !code && /^## /            { f=0 }
    f && /#554/                { got_554=1 }
    f && /#557/                { got_557=1 }
    END                        { exit !(got_554 && got_557) }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c halt message enumerates diagnostic checklist" {
  # Checklist must name at least the three things the plan calls out: manual
  # mutation-kills-the-test check, SolutionPath review, unintended-project
  # enumeration. tolower() gives us case-insensitive matching without the /i
  # flag (BSD awk doesn't support it).
  run awk '
    /^```/                                                   { code = !code; next }
    !code && /^## Step 1c/                                   { f=1; next }
    !code && /^## /                                          { f=0 }
    f && tolower($0) ~ /manual/                              { got_manual=1 }
    f && /SolutionPath/                                      { got_sp=1 }
    f && tolower($0) ~ /(test.?project|enumerat)/            { got_enum=1 }
    END                                                      { exit !(got_manual && got_sp && got_enum) }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c defines behavior for Killed==0 Survived==0 (no-signal probe)" {
  # The Killed==0 && Survived==0 case must be explicitly addressed — otherwise
  # a no-mutants-generated probe silently authorizes the full run.
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## Step 1c/             { f=1; next }
    !code && /^## /                    { f=0 }
    f && tolower($0) ~ /(no.?signal|no.?scored.?mutants|zero.?mutants|killed.*0.*survived.*0|survived.*0.*killed.*0|pick a different probe|different probe file)/ { found=1 }
    END                                { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 1c authorizes proceeding when Killed>0" {
  run awk '
    /^```/                                                 { code = !code; next }
    !code && /^## Step 1c/                                 { f=1; next }
    !code && /^## /                                        { f=0 }
    f && tolower($0) ~ /(proceed|authoriz|continue)/       { found=1 }
    END                                                    { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

# =============================================================================
# Slice 1 — SKILL.md · Long-run inspection section (#558)
# =============================================================================

@test "SKILL: Long-run inspection section exists between Step 2 and Step 3" {
  # The section anchors between Step 2 (Run) and Step 3 (Parse) — that's where
  # a long-running Stryker/pitest/mutmut invocation lives. Section title fixed
  # as "Long-run inspection" (case-sensitive; BSD awk has no /i regex flag).
  step2_line=$(awk '
    /^```/                             { code = !code; next }
    !code && /^## Step 2/              { print NR; exit }
  ' "$SKILL")
  longrun_line=$(awk '
    /^```/                             { code = !code; next }
    !code && /^## Long-run inspection/ { print NR; exit }
  ' "$SKILL")
  step3_line=$(awk '
    /^```/                             { code = !code; next }
    !code && /^## Step 3/              { print NR; exit }
  ' "$SKILL")
  [ -n "$step2_line" ]
  [ -n "$longrun_line" ]
  [ -n "$step3_line" ]
  [ "$step2_line" -lt "$longrun_line" ]
  [ "$longrun_line" -lt "$step3_line" ]
}

@test "SKILL: Long-run inspection names progress, health, error inspection signals" {
  run awk '
    /^```/                                        { code = !code; next }
    !code && /^## Long-run inspection/            { f=1; next }
    !code && /^## /                               { f=0 }
    !code && f && tolower($0) ~ /progress/        { got_p=1 }
    !code && f && tolower($0) ~ /health/          { got_h=1 }
    !code && f && tolower($0) ~ /error inspection/ { got_e=1 }
    END                                           { exit !(got_p && got_h && got_e) }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Long-run inspection documents 10-minute default cadence" {
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## Long-run inspection/ { f=1; next }
    !code && /^## /                    { f=0 }
    !code && f && /(10[- ]?minute|10 min|600 ?s|10-min)/ { found=1 }
    END                                { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Long-run inspection notes language files may add signatures" {
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## Long-run inspection/ { f=1; next }
    !code && /^## /                    { f=0 }
    !code && f && /(language.?file|per-language|references\/languages|tool-specific)/ { found=1 }
    END                                { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Long-run inspection names portable bash wrapper as an example" {
  # Section must name concrete implementations (per plan-review Acceptance
  # Critic's phrasing fix) — not just describe an abstract contract.
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## Long-run inspection/ { f=1; next }
    !code && /^## /                    { f=0 }
    !code && f && /wrapper/            { found=1 }
    END                                { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Long-run inspection names in-session Monitor as an alternative" {
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## Long-run inspection/ { f=1; next }
    !code && /^## /                    { f=0 }
    !code && f && /Monitor/            { found=1 }
    END                                { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

# =============================================================================
# Slice 2 — csharp-stryker-net.md (#557: SolutionPath trap + Step 1c link
#                                 + dots reporter)
# =============================================================================

@test "csharp-stryker-net: SolutionPath trap warning exists" {
  run grep -E "SolutionPath.*trap|trap.*SolutionPath" "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: SolutionPath warning enumerates three remediation paths" {
  # Three paths: remove SolutionPath; exclude the main test project; downgrade
  # to xunit.v2. Match any reasonable phrasing (case-sensitive; BSD awk).
  run awk '
    /^```/                                                { code = !code; next }
    /SolutionPath/                                        { f=1 }
    f && /(remove|omit).*(SolutionPath|solution.?path)/   { got_remove=1 }
    f && /(exclude|omit).*(test.?project|main test)/      { got_exclude=1 }
    f && /(downgrade|xunit\.?v2)/                         { got_downgrade=1 }
    END                                                   { exit !(got_remove && got_exclude && got_downgrade) }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: xunit.v3 section links to Step 1c" {
  # The xunit.v3 section must point at SKILL.md's Step 1c rather than duplicate
  # the smoke procedure. Existing section heading is "## xunit.v3 detection"
  # (case-sensitive; the reference already uses it).
  run awk '
    /^```/                             { code = !code; next }
    !code && /^## xunit\.v3/           { f=1; next }
    !code && /^## /                    { f=0 }
    f && /Step 1c/                     { found=1 }
    END                                { exit !found }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: reporters guidance names \"dots\"" {
  # The reporters recommendation must include "dots" — that's the
  # survives-redirection reporter the status loop parses.
  run grep -E '"dots"' "$CSHARP"
  [ "$status" -eq 0 ]
}

# =============================================================================
# Slice 5 — csharp-stryker-net.md (#558, #559: shipped wrapper + status loop
#                                  + copy-both instruction)
# =============================================================================

@test "csharp-stryker-net: names both shipped scripts" {
  run grep -c "csharp-stryker-net-wrapper\.sh" "$CSHARP"
  [ "$status" -eq 0 ]
  run grep -c "csharp-stryker-net-status-loop\.sh" "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: instructs copying both scripts together" {
  # Must clearly instruct copying both files together — copying only the
  # wrapper hard-fails at set -e on the missing source.
  run awk '
    /csharp-stryker-net-wrapper\.sh/ { got_wrapper_line=NR }
    /csharp-stryker-net-status-loop\.sh/ { got_loop_line=NR }
    /(both|together)/ { got_both_line=NR }
    END {
      exit !(got_wrapper_line && got_loop_line && got_both_line)
    }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: warns about set -e abort on missing source" {
  # The reference must document the failure mode of copying only the wrapper.
  run grep -E "(set -e|missing source|\. .*status-loop|source .*status-loop)" "$CSHARP"
  [ "$status" -eq 0 ]
}

@test "csharp-stryker-net: documents STATUS_INTERVAL default 600 and disable=0" {
  run grep -E "STATUS_INTERVAL" "$CSHARP"
  [ "$status" -eq 0 ]
  run awk '
    /STATUS_INTERVAL/                    { f=1 }
    f && /600/                           { got_default=1 }
    f && /STATUS_INTERVAL=0/             { got_disable=1 }
    END                                  { exit !(got_default && got_disable) }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
}
