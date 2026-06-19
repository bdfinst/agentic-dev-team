#!/usr/bin/env bats
# Doc-shape contract for /test-modernize Phase 4 + Phase 5 end-of-phase
# test review (Slice 5 of plans/mutation-testing-every-phase.md).
#
# At the end of Phase 4 AND Phase 5, the orchestrator must:
#   1. Capture the phase's base sha.
#   2. Dispatch /test-design --since <base-sha>.
#   3. Dispatch /code-review --since <base-sha>.
#   4. On error/warning findings, dispatch /apply-fixes <corrections-dir>.
#   5. Re-run /code-review. Loop body capped at 2 iterations.
#   6. After iteration 2, escalate to operator with [r] / [w] / [q].
#   7. Tool-unavailable triage names /init-dev-team.
#   8. Persist evidence to memory/test-modernize/<slug>/phase-<n>-review.json.
#
# This is additive — the Slice 3 + Slice 4 snapshot fixtures MUST stay green.
# Those checks live in the prior bats files; we don't re-test snapshots here.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-modernize/SKILL.md"

# Extract the "Review the phase" subsection. The shared loop body may live
# in a single subsection above Phase 4 with cross-references from both
# Phase 4 and Phase 5; either layout is acceptable as long as both phases
# clearly invoke the loop.

@test "SKILL: documents an end-of-phase 'Review the phase' (or equivalent) loop body once" {
  run grep -iE 'review the phase|end-of-phase review|review-the-phase loop' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Phase 4 invokes the review loop ----------------------------------------

@test "Phase 4: invokes /test-design --since <phase-base-sha>" {
  run awk '/^### 4\./{f=1} /^### 5\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE '/test-design.+--since'
}

@test "Phase 4: invokes /code-review --since <phase-base-sha>" {
  run awk '/^### 4\./{f=1} /^### 5\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE '/code-review.+--since'
}

@test "Phase 4: review evidence persisted to phase-4-review.json" {
  run awk '/^### 4\./{f=1} /^### 5\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'phase-4-review\.json'
}

# --- Phase 5 invokes the same loop -----------------------------------------

@test "Phase 5: invokes /test-design --since <phase-base-sha>" {
  run awk '/^### 5\./{f=1} /^### 6\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE '/test-design.+--since'
}

@test "Phase 5: invokes /code-review --since <phase-base-sha>" {
  run awk '/^### 5\./{f=1} /^### 6\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE '/code-review.+--since'
}

@test "Phase 5: review evidence persisted to phase-5-review.json" {
  run awk '/^### 5\./{f=1} /^### 6\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'phase-5-review\.json'
}

# --- Fix loop: /apply-fixes + max 2 iterations -----------------------------

@test "Review loop: documents /apply-fixes as the fix dispatch" {
  run grep -E '/apply-fixes' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "Review loop: documents 'max 2 iterations' (or equivalent) cap" {
  # Plan AC-8 pins this number explicitly. Drift to 5 or unbounded
  # silently changes the workflow's cost ceiling.
  run grep -iE 'max(imum)? 2 iterations|2 iterations max|cap.{0,30}2 iteration|2-iteration cap' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Escalation prompt on loop overflow ------------------------------------

@test "Review loop: escalation offers [r] revise manually then /continue" {
  run grep -iE '\[r\].+(revise|fix).+manual.+/continue|\[r\].+/continue' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "Review loop: escalation offers [w] waive (with recorded reason)" {
  # Waiver is the operator-controlled override path. Reason must be recorded
  # so it shows up in the same waivers.json the mutation halt uses.
  run grep -iE '\[w\].+waive' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "Review loop: escalation offers [q] quit" {
  run grep -iE '\[q\].+quit' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Tool-unavailable triage names /init-dev-team --------------------------

@test "Review loop: tool-unavailable triage names /init-dev-team" {
  run grep -iE '/test-design.+(unavailable|missing)|/code-review.+(unavailable|missing)|review.+(unavailable|missing).+/init-dev-team|/init-dev-team.+review' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Human gate references the review evidence ----------------------------

@test "Phase 4 human gate: references phase-4-review.json" {
  run awk '/^### 4\./{f=1} /^### 5\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -iE 'human gate' | grep -qiE 'phase-4-review|review evidence|review (results|findings)' || {
    # Fallback: the gate line follows a "Review the phase" sub-step and
    # the review-evidence file is named earlier in Phase 4.
    echo "$output" | grep -q 'phase-4-review\.json'
  }
}

@test "Phase 5 human gate: references phase-5-review.json" {
  run awk '/^### 5\./{f=1} /^### 6\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -iE 'human gate' | grep -qiE 'phase-5-review|review evidence|review (results|findings)' || {
    echo "$output" | grep -q 'phase-5-review\.json'
  }
}

# --- Schema for phase-<n>-review.json --------------------------------------

@test "SKILL: phase-<n>-review.json schema names farley_score, code_review, iterations, escalated" {
  for k in farley_score code_review iterations escalated; do
    grep -qE "$k" "$SKILL" || {
      echo "missing review-json key: $k"
      return 1
    }
  done
}

# --- Out-of-scope guard: Slice 3 + Slice 4 snapshots still pass -----------
# Those checks live in the prior bats files. We don't duplicate them here,
# but if this slice's edits ever bleed into Phase 1-3 of test-modernize or
# Steps 4-5 of quality-targets-converge, the prior bats files will catch it
# (snapshot byte-identity).
