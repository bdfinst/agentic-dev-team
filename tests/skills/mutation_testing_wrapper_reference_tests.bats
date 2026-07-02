#!/usr/bin/env bats
# Doc-shape contract for the Slice 5 additions to csharp-stryker-net.md
# (issues #558, #559 — shipped wrapper + status loop + copy-both instruction).
#
# Split from mutation_testing_silent_failure_doc_tests.bats so PR1 can land
# without PR2's reference content. This file ships with PR2 (Slice 5).
#
# Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slice 5.

CSHARP="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md"

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
    /csharp-stryker-net-wrapper\.sh/     { got_wrapper_line=NR }
    /csharp-stryker-net-status-loop\.sh/ { got_loop_line=NR }
    /(both|together)/                    { got_both_line=NR }
    END { exit !(got_wrapper_line && got_loop_line && got_both_line) }
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
    /STATUS_INTERVAL/          { f=1 }
    f && /600/                 { got_default=1 }
    f && /STATUS_INTERVAL=0/   { got_disable=1 }
    END                        { exit !(got_default && got_disable) }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
}
