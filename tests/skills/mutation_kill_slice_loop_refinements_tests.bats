#!/usr/bin/env bats
# Doc-shape contract for issue #667 / #681 (plan: Slice 2 — Concurrency
# default fix): plans/mutation-kill-slice-loop-refinements.md.
#
# Pattern mirrors tests/skills/mutation_testing_skill_doc_tests.bats — grep
# guards against csharp-stryker-net.md's "Shipped wrapper" section. The
# prose is the deliverable; these guards regress when the contract drifts.
#
# This file is the shared home for all four slices of the plan
# (mutation-kill-slice-loop-refinements). Slice 2 (this PR) adds only the
# concurrency-default doc-content test below; later slices append their own
# tests here as those slices land.

CSHARP="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md"

# --- Slice 2 · AC-5: concurrency default documented in the C# reference ----

@test "csharp-stryker-net.md documents the wrapper's concurrency default" {
  run awk '
    /^## Shipped wrapper/ { f=1 }
    /^## / && !/^## Shipped wrapper/ && f { if (NR > 1) exit }
    f { print }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
  section="$output"

  # Wording near the CLI-flag table naming cores / cpu_count.
  echo "$section" | grep -qE "cores|cpu_count"

  # The flag name itself.
  echo "$section" | grep -q -- "--stryker-concurrency"

  # The env-var equivalent.
  echo "$section" | grep -q "STRYKER_MUTANT_CONCURRENCY"

  # A sentence distinguishing it from mutation-kill's own --concurrency
  # (worktree fan-out).
  echo "$section" | grep -q -- "--concurrency"
  echo "$section" | grep -qi "worktree fan-out"

  # The CI/cgroup caveat for os.cpu_count().
  echo "$section" | grep -qi "cgroup"
}
