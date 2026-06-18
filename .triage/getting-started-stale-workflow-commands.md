---
id: getting-started-stale-workflow-commands
created: 2026-06-08T00:00:00Z
status: closed
---

# GETTING-STARTED.md: stale workflow commands and misplaced "Invoke a skill directly" section

## Problem

- **Actual behavior**: The `### Use the workflow commands` section listed only 5 commands (`/plan`, `/build`, `/pr`, `/code-review`, `/triage`) and omitted `/specs` — the mandatory first step of the ATDD workflow described elsewhere in the same document. The `### Invoke a skill directly` section appeared before the workflow commands section despite being a secondary entry point, and its examples (`/threat-modeling`, `/api-design`, `/specs`) duplicated the Common Workflows section that follows.
- **Expected behavior**: The workflow commands section reflects the current primary lifecycle commands (at minimum adding `/specs`). The "Invoke a skill directly" section is positioned after the common workflow or merged into it, not before the primary lifecycle commands.
- **Reproduction**: Read GETTING-STARTED.md lines 32–54. The `### Invoke a skill directly` block at line 33 precedes the `### Use the workflow commands` block at line 43. The workflow commands block omits `/specs`, which is called out as the starting point in the `## Rules to Know` section (line 114) and the `### New Feature` workflow (line 60).

## Root Cause Analysis

The document was authored before `/specs` was elevated to a mandatory first lifecycle step, and the "Invoke a skill directly" section was never repositioned when "Common Workflows" was added. The two changes are independent: (1) the workflow commands list is stale — it predates the specs→plan→build→pr ATDD contract; (2) the section ordering puts a secondary usage pattern (direct skill invocation) ahead of the primary lifecycle entry point.

## Resolution

All three acceptance criteria addressed:

1. `/specs` added as the first entry in `### Use the workflow commands` (with its ATDD role described) — PR #255 + this fix.
2. `### Invoke a skill directly` repositioned to appear after `### Use the workflow commands` — PR #255.
3. Examples in `### Invoke a skill directly` changed to `/ubiquitous-language`, `/design-doc`, `/hexagonal-architecture` — skills not already featured in `## Common Workflows` — eliminating the duplication.

Documentation gate tests added in `tests/docs/getting_started_workflow_commands_tests.bats` (PR #255) cover criteria 1 and 2. All tests pass.

## Acceptance Criteria

- [x] Root cause is addressed (not just symptom)
- [x] All new tests pass
- [x] Existing tests still pass
- [x] No regressions introduced
- [x] `/specs` appears in the workflow commands list
- [x] `### Invoke a skill directly` does not precede the primary lifecycle commands
- [x] No content is duplicated between the "Invoke a skill directly" material and `## Common Workflows`
