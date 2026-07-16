# `--workflow-managed-approval` — approved caller registry

The `--workflow-managed-approval` flag on `/mutation-testing` bypasses the Step 0 confirmation prompt because the calling workflow captured operator approval at a higher boundary. The flag is **not** general-purpose; it is a narrow carve-out for orchestrated workflows whose Phase 0 (or equivalent) already obtained explicit operator consent for the run as a whole.

This file is the source of truth for the allowlist. `/mutation-testing` `## Constraints` references this file by path so a new caller only has to update one place.

## Allowed callers

| Caller skill | Workflow it belongs to | Where its approval is captured | Why the carve-out applies |
| --- | --- | --- | --- |
| [`/coverage-delta`](../../coverage-delta/SKILL.md) | `/test-improve` Phase 4 (per-Story coverage delta + optional mutation gate) | `/test-improve` Phase 0 ("Approach contract" — the mutation-mode knob (`off` / `kill-loop` / `baseline+kill-loop`) is the workflow-level approval point) | Phase 4 measures mutation per Story automatically when the mutation mode is not `off`; per-invocation prompts would block the workflow on every Story close. |
| [`/test-improve`](../../test-improve/SKILL.md) | `/test-improve` Phase 2 (baseline mutation, in `baseline+kill-loop` mode) | `/test-improve` Phase 0 (same mutation-mode knob) | Phase 2 measures the mutation baseline across the in-scope files once before any test change so later phases have a floor; a per-invocation prompt at that boundary would break the workflow-level-approval contract. |
| [`/quality-targets-converge`](../../quality-targets-converge/SKILL.md) | `/test-improve` Phase 6 (Validate convergence loop) | `/test-improve` Phase 0 (same mutation-mode knob) | Phase 6 runs the convergence loop under the `/test-improve` orchestrator; approval was captured once at Phase 0. `/test-improve` Phase 4 drives mutation via the `mutation-kill` agent (which wraps the tool directly and never sets this flag), so the flag enters only through this Phase-6 caller. |

## Adding a new caller

Any new caller must:

1. Document where its workflow-level operator approval is captured (a named Phase, gate, or skill that prompts once for the entire run).
2. Add a row to the table above naming the caller, the workflow, the approval-capture point, and why the carve-out is justified.
3. Land all three changes (the new caller, this row, and any cross-skill cross-reference) in the same PR so the auditor can see the full intent.

`/mutation-testing` `## Constraints` is the enforcement surface: it asserts the carve-out invariant but **does not enumerate callers inline**. Reviewers verify allowlist membership by reading this file. Bats tests in `tests/skills/mutation_testing_scoping_tests.bats` assert (a) the carve-out paragraph exists in `## Constraints`, (b) the named callers (`/coverage-delta`, `/quality-targets-converge`) appear in `## Constraints` for human-readable discoverability — once a third caller lands, that test can either be widened or replaced with an assertion that the constraint references this registry.
