#!/usr/bin/env bats
# Doc-shape contract for /coverage-delta's scoped mutation step (Slice 2 of
# plans/mutation-testing-every-phase.md, issue #285).
#
# The worker measures and reports; it never halts on net-new survivors.
# These tests guard the doc-only invariants: the gating flags, the four
# status values, the policy-free assertion, and atomic-write semantics for
# mutation-history.json.
#
# Note on the concurrent-write Gherkin scenario: it is asserted at the
# documentation level only (SKILL.md prescribes temp-file-then-rename and
# forbids direct overwrite). Behavioral atomicity is verified by code
# review, not by this RED gate. See Slice 2 RED notes in the plan.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/coverage-delta/SKILL.md"

# --- Flag surface -----------------------------------------------------------

@test "SKILL: ## Parse Arguments names --story-files" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--story-files/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: ## Parse Arguments names --story (pre-existing)" {
  run awk '/^## Parse Arguments/{f=1;next} /^## /{f=0} f && /--story/{found=1} END{exit !found}' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 2b gating: both --story AND --story-files must be present --------

@test "SKILL: has a Step 2b 'measure scoped mutation' heading" {
  # The literal "Step 2b" appears in body prose as well; tighten to the
  # actual heading line so we regress when someone removes the section
  # but leaves a dangling reference.
  run grep -E '^### 2b\.' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: Step 2b body names both --story and --story-files as gating conditions" {
  # Extract Step 2b through the next sibling step (### Step or ## )
  run awk '/^### 2b\./{f=1;next} /^### [0-9]+\b|^## /{ if(f==1){f=2} } f==1' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q -- '--story-files'
  echo "$output" | grep -q -- '--story\b'
}

@test "SKILL: Step 2b invokes /mutation-testing with --workflow-managed-approval" {
  run awk '/^### 2b\./{f=1;next} /^### [0-9]+\b|^## /{ if(f==1){f=2} } f==1' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q -- '--workflow-managed-approval'
}

# --- Worker policy: measurement only, never halts ---------------------------

@test "SKILL: explicit statement — worker measures, does NOT halt on net-new survivors" {
  # The plan pins this literal sentence (or substring-equivalent) as the
  # worker/policy boundary. Drift here means a reviewer can't tell whether
  # the worker or orchestrator owns the gate.
  run grep -E 'measures.+reports.+(NOT|does not).+halt' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents exit code 0 on net_new_survivors (non-zero only on tool failure)" {
  run grep -iE 'exit (code )?0.*net.new|net.new.*exit (code )?0|non-zero.*tool (execution )?failure' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Status enum -----------------------------------------------------------

@test "SKILL: documents status enum: ok | net_new_survivors | first_measurement | tool_unavailable" {
  for val in ok net_new_survivors first_measurement tool_unavailable; do
    grep -qE "\"?$val\"?" "$SKILL" || {
      echo "missing status value: $val"
      return 1
    }
  done
}

@test "SKILL: documents skipped_empty_scope as an additional worker-only state" {
  run grep -E 'skipped_empty_scope' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Baseline-of-record rule -----------------------------------------------

@test "SKILL: documents 'most recent mutation-history entry per file is the baseline-of-record'" {
  run grep -iE 'most recent.+(history|entry).+(file|baseline)|baseline.of.record' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents first_measurement: survivors_before=null, delta=null" {
  run grep -iE 'first.measurement|survivors_before.+null|first measurement' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Equivalent-mutant filter ----------------------------------------------

@test "SKILL: documents filtering status='equivalent' before computing delta" {
  run grep -iE 'filter.+equivalent|equivalent.+(filter|exclude)|exclude.+equivalent' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Atomic-write semantics for mutation-history.json ----------------------

@test "SKILL: documents mutation-history.json as the per-file history file" {
  run grep -E 'mutation-history\.json' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents temp-file-then-rename idiom for mutation-history.json" {
  # Concurrent-write Gherkin scenario asserted at doc level only.
  run grep -iE 'temp(-| )file.+rename|rename.+temp(-| )file|atomic.+(write|rename)' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Tool-unavailable degradation surfaces /init-dev-team ------------------

@test "SKILL: tool_unavailable result block names /init-dev-team as install path" {
  run grep -E '/init-dev-team' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents tool-disappears-mid-run scenario records prior_tool" {
  run grep -E 'prior_tool' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Result block schema on stdout -----------------------------------------

@test "SKILL: documents JSON result block with status + mutation + story + story_files" {
  # Scan for the worker's stdout result-block contract.
  for k in status mutation story story_files; do
    grep -qE "\"?$k\"?" "$SKILL" || {
      echo "missing result-block key: $k"
      return 1
    }
  done
}

# --- Convergence-loop reuse: --story alone (no --story-files) is a no-op ---

@test "SKILL: --story without --story-files triggers no mutation run (convergence-loop callable)" {
  # The Slice 2 contract: without --story-files, no scoped mutation, no
  # mutation-history.json write. This preserves the existing
  # /quality-targets-converge call path.
  run grep -iE '(without|no).+--story-files.+(no|skip).+(mutation|history)|--story alone' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- --story-files glob matches zero files ----------------------------------

@test "SKILL: documents skipped_empty_scope for empty --story-files glob" {
  run grep -iE 'empty.+(--story-files|scope)|skipped_empty_scope' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "SKILL: documents history-entry write on empty --story-files scope" {
  # Gherkin 'Then' for the empty-scope scenario: mutation-history GETS an
  # entry with status:'skipped_empty_scope'. The doc must say so or
  # operators can't tell whether the worker silently dropped the Story.
  run grep -iE 'one history entry|history entry recorded' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Markdown row template gains a Mutants column --------------------------

@test "SKILL: parent-issue markdown row template includes a Mutants column" {
  run grep -E '[Mm]utants.*Δ|Δ.*[Mm]utants|Mutants <count>' "$SKILL"
  [ "$status" -eq 0 ]
}
