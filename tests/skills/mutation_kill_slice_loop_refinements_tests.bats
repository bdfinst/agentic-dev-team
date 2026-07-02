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

# --- Slice 3 · convergence-derived glob negation example (#682) ------------

@test "csharp-stryker-net.md infra-exclusion glob template shows a convergence-derived negation example" {
  run awk '
    /^## Infrastructure exclusion `mutate` glob template/ { f=1 }
    /^## / && !/^## Infrastructure exclusion/ && f { if (NR > 1) exit }
    f { print }
  ' "$CSHARP"
  [ "$status" -eq 0 ]
  section="$output"

  # A convergence-derived negation example, distinguished from the
  # permanent infra-exclusion negations already in the template.
  echo "$section" | grep -qi "convergence"
  echo "$section" | grep -q -- "!"
  echo "$section" | grep -qi "re-checked\|drop out\|permanent"
}

# --- Slice 4 · tiered mutation-level example commands (#683) ----------------

@test "csharp-stryker-net.md shows both a Basic baseline and a Standard escalation example command" {
  run cat "$CSHARP"
  [ "$status" -eq 0 ]
  content="$output"

  # Basic baseline command.
  echo "$content" | grep -q -- "--mutation-level Basic"

  # Standard escalation command, scoped via --mutate to one file.
  echo "$content" | grep -q -- "--mutation-level Standard"
  echo "$content" | grep -q -- "--mutate"
}
