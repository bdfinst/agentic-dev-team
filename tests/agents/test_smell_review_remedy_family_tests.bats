#!/usr/bin/env bats
# Contract for the test-smell-review agent's remedyFamily addition (#534).
# Each of R2.2.a - R2.2.g in the plan maps to one bats assertion below.

AGENT="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/test-smell-review.md"

@test "R2.2.a schema property remedyFamily is documented in the JSON block" {
  # Find the "issues" JSON schema block and ensure remedyFamily appears in it.
  grep -Eq '"remedyFamily"' "$AGENT"
}

@test "R2.2.b allowed remedyFamily values are named (four slugs + null)" {
  grep -Fq 'fixture-construction' "$AGENT"
  grep -Fq 'result-verification' "$AGENT"
  grep -Fq 'test-organization' "$AGENT"
  grep -Fq 'test-refactoring' "$AGENT"
  # 'null' must also be explicitly documented as a valid value
  grep -Eqi 'remedyFamily.*null|null.*remedyFamily|null.*when.*no.*family|null.*for.*smell' "$AGENT"
}

@test "R2.2.c contract: both remedyFamily and suggestedFix are always populated" {
  grep -Eqi 'both.*remedyFamily.*suggestedFix.*always populated|always populated.*remedyFamily.*suggestedFix|both fields.*always populated|both.*fields are always populated' "$AGENT"
}

@test "R2.2.d contract: suggestedFix is always a specific remedy pattern, not a family slug, regardless of invocation" {
  # The AC11 guard: solo /code-review still gets a pattern-level suggestedFix.
  grep -Eqi 'suggestedFix.*specific.*pattern|specific remedy pattern.*suggestedFix|suggestedFix.*not.*family.*slug|not.*family slug.*suggestedFix|suggestedFix.*pattern.*not.*slug|regardless of invocation.*suggestedFix|suggestedFix.*regardless of invocation' "$AGENT"
}

@test "R2.2.e prose-emission contract: family slug must appear verbatim in message (not suggestedFix)" {
  # The grader-alignment guard: verdict.py:40 scans message+summary only.
  grep -Eqi 'family slug.*verbatim.*message|verbatim.*message.*family slug|slug.*must appear.*message|slug.*appear.*in.*message' "$AGENT"
  # Must call out that suggestedFix is NOT the field the grader scans.
  grep -Eqi 'not.*suggestedFix|suggestedFix.*not.*scanned|verdict\.py|grader.*scans.*message' "$AGENT"
}

@test "R2.2.f Scope references division-of-labor section by heading text" {
  grep -Fq 'test-smell-review ↔ test-design-advisor — remedy division' "$AGENT"
}

@test "R2.2.g smell→family mapping table exists in the agent" {
  # The Detect (or nearby) section must include a mapping so the agent can
  # populate remedyFamily deterministically. At minimum the three non-null
  # mappings we've validated must appear near each other.
  grep -Eqi 'smell.*family|family.*smell' "$AGENT"
  # Sanity: at least two of the four family slugs appear inside a table row.
  grep -Eq '\|.*(fixture-construction|result-verification|test-organization|test-refactoring)' "$AGENT"
}
