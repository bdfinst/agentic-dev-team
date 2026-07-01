#!/usr/bin/env bats
# Doc-shape contract for issue #521 additions to the /mutation-testing skill:
# honest score, claimed score, timeout warning, NoCoverage-first triage,
# mutation-type-aware guidance, and probe-file selection.
#
# Plan: plans/mutation-testing-honest-score-and-triage.md — Slice 1 (SKILL.md)
# and Slice 2 (csharp-stryker-net.md).
#
# Pattern mirrors tests/skills/mutation_testing_scoping_tests.bats — awk/grep
# section guards against the SKILL.md / language-reference prose. The prose is
# the deliverable; these guards regress when the contract drifts.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/SKILL.md"
CSHARP="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md"

# --- Slice 1 · AC-1: honest score above claimed score in Output format -------
#
# awk section-scanning here must ignore ## headings INSIDE fenced code blocks
# (the ```markdown example contains "## Mutation Testing Results" etc.).
# `code` toggles on ``` and suppresses the ## section-boundary while inside.

@test "SKILL: Output format shows Honest score line" {
  run awk '
    /^```/                   { code = !code; next }
    !code && /^## Output format/ { f=1; next }
    !code && /^## /          { f=0 }
    f && /Honest score/      { found=1 }
    END                      { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Output format shows Claimed score line" {
  run awk '
    /^```/                   { code = !code; next }
    !code && /^## Output format/ { f=1; next }
    !code && /^## /          { f=0 }
    f && /Claimed score/     { found=1 }
    END                      { exit !found }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Honest score line appears above Claimed score line in Output format" {
  honest_line=$(awk '
    /^```/                   { code = !code; next }
    !code && /^## Output format/ { f=1; next }
    !code && /^## /          { f=0 }
    f && /Honest score/      { print NR; exit }
  ' "$SKILL")
  claimed_line=$(awk '
    /^```/                   { code = !code; next }
    !code && /^## Output format/ { f=1; next }
    !code && /^## /          { f=0 }
    f && /Claimed score/     { print NR; exit }
  ' "$SKILL")
  [ -n "$honest_line" ]
  [ -n "$claimed_line" ]
  [ "$honest_line" -lt "$claimed_line" ]
}

# --- Slice 1 · AC-2: schema example carries the five new fields --------------

@test "SKILL: Machine-readable output schema names honest_score" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /"honest_score"/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Machine-readable output schema names claimed_score" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /"claimed_score"/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Machine-readable output schema names timeout_pct" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /"timeout_pct"/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Machine-readable output schema names no_coverage" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /"no_coverage"/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Machine-readable output schema names timeout_warning" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /"timeout_warning"/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 1 · AC-3: formulas documented next to the schema ------------------

@test "SKILL: schema section shows the honest_score formula" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /honest_score[[:space:]]*=[[:space:]]*Killed[[:space:]]*\/[[:space:]]*\(Killed[[:space:]]*\+[[:space:]]*Survived[[:space:]]*\+[[:space:]]*NoCoverage\)/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema section shows the claimed_score formula" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /claimed_score[[:space:]]*=[[:space:]]*\(Killed[[:space:]]*\+[[:space:]]*Timeout\)[[:space:]]*\/[[:space:]]*\(Killed[[:space:]]*\+[[:space:]]*Survived[[:space:]]*\+[[:space:]]*Timeout[[:space:]]*\+[[:space:]]*NoCoverage\)/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 1 · AC-4: schema_version stays at 1 -------------------------------

@test "SKILL: schema_version stays at 1 (no bump to 2 anywhere)" {
  run grep -E '"schema_version"[[:space:]]*:[[:space:]]*2' "$SKILL"
  [ "$status" -ne 0 ]
}

# --- Slice 1 · AC-5: timeout warning defined and remediation named ----------

@test "SKILL: schema section names the timeout_warning threshold (0.05 / 5%)" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /timeout_pct[[:space:]]*>[[:space:]]*0\.05/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: timeout warning names additional-timeout as the fix" {
  run grep -E 'additional-timeout' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 1 · AC-6: emitting-adapters list ---------------------------------

@test "SKILL: schema section names Stryker.NET as an emitting adapter" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /Stryker\.NET/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema section names pitest as an emitting adapter" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /pitest/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema section names mutmut as an emitting adapter" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /mutmut/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: schema section notes go-mutesting omits the new fields (advisory-only)" {
  run awk '/^## Machine-readable output/{f=1;next} /^## /{f=0} f && /go-mutesting/ && /omit/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 1 · AC-7: NoCoverage is a first-class triage category ------------

@test "SKILL: Step 4 triage table has a NoCoverage row" {
  run awk '/^## Step 4/{f=1;next} /^## /{f=0} f && /\| \*\*NoCoverage\*\* \|/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: NoCoverage row's Action tells operator to add a test that reaches the path" {
  run awk '/^## Step 4/{f=1;next} /^## /{f=0} f && /NoCoverage/ && /reaches/ && /path/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 4 recommended work order lists NoCoverage before Survived" {
  # Find the "Recommended work order" prose in Step 4 and check ordering by line number.
  nocov_line=$(awk '/^## Step 4/{f=1;next} /^## /{f=0} f && /Recommended work order/{g=1} g && /NoCoverage/{print NR;exit}' "$SKILL")
  surv_line=$(awk '/^## Step 4/{f=1;next} /^## /{f=0} f && /Recommended work order/{g=1} g && /Survived/{print NR;exit}' "$SKILL")
  [ -n "$nocov_line" ]
  [ -n "$surv_line" ]
  [ "$nocov_line" -lt "$surv_line" ]
}

# --- Slice 1 · AC-8: mutation-type-aware sub-section ------------------------

@test "SKILL: Step 4 has a Mutation-type-aware sub-section" {
  run awk '/^## Step 4/{f=1;next} /^## /{f=0} f && /^### .*[Mm]utation-type-aware/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: type-aware guidance covers String / ObjectInitializer / Equality → specific assertion" {
  run awk '/^### .*[Mm]utation-type-aware/{f=1;next} /^### /{f=0} f && /String/ && /ObjectInitializer/ && /Equality/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: type-aware guidance names Statement/Block and states a stronger assertion cannot kill them" {
  run awk '/^### .*[Mm]utation-type-aware/{f=1;next} /^### /{f=0} f && /Statement/ && /Block/ && /cannot kill/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: type-aware guidance names Guard and directs to unit test invoking the guarded method directly" {
  run awk '/^### .*[Mm]utation-type-aware/{f=1;next} /^### /{f=0} f && /Guard/ && /directly/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 1 · AC-9: language-agnostic probe file selection in Step 2 -------

@test "SKILL: Step 2 has a probe file selection sub-section" {
  run awk '/^## Step 2/{f=1;next} /^## /{f=0} f && /^### .*[Pp]robe file selection/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: probe selection names the >= 50 mutants rule" {
  run awk '/^### .*[Pp]robe file selection/{f=1;next} /^### /{f=0} /^## /{f=0} f && /50/ && /mutants/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: probe selection names the highest-existing-score rule" {
  run awk '/^### .*[Pp]robe file selection/{f=1;next} /^### /{f=0} /^## /{f=0} f && /highest/ && /score/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: probe selection lists generated code, DTOs, and near-zero-coverage as anti-patterns" {
  run awk '/^### .*[Pp]robe file selection/{f=1;next} /^### /{f=0} /^## /{f=0} f && /[Gg]enerated/{a=1} f && /DTO/{b=1} f && /[Cc]overage/{c=1} END{exit !(a && b && c)}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Slice 2 tests appended in Step 2.1 (C#-specific probe avoidance) -------
