Convert Phase 1's ordered improvement plan into actionable work items.
Delegate the write to
`/issues-from-assessment --workflow test-improve --refactor-mode <value>`
(`phase-0.md`'s `no-refactor` or `refactor-allowed`); the skill routes the
memory + plan paths under `test-improve/` (per Slice 11). Threading
`--refactor-mode` lets the written plan mark refactor-requiring items
explicitly: in `no-refactor` mode the Phase-7 `[Refactor-for-testability]`
work surfaces labeled **out-of-scope / skipped-in-no-refactor**, never as
actionable Phase-5 Stories.

Every finding lands in exactly one of three actionable **gap classes**, plus
one non-actionable class:

- **`NO_REFACTOR`** — fixable by test edits alone. Written as **Phase-5
  Stories** to `.claude/plans/test-improve/` (or the configured parent tracker
  when `--parent` was supplied at Phase 0).
- **`REFACTOR_REQUIRED`** — needs a production-code seam before a test can reach the behavior. REFACTOR_REQUIRED items are **deferred to Phase 7** and are **not written as Phase-5 Stories**; they surface with rationale for the operator, who decides at Phase 6 whether to enter Phase 7. Under `refactor-mode: no-refactor` they are labeled **out-of-scope (skipped-in-no-refactor)** in the plan — informational context, never an actionable Story this run will execute.
- **`LOW_VALUE`** — tests that are cheap to have but not worth fixing (e.g. duplicate coverage, trivial getters, dead-code assertions). LOW_VALUE findings are **advisory-only**: enumerated in the report, no PR is opened to delete a test flagged this way.
- **`NOT_IMPLEMENTED`** (`/test-health`'s gherkin-gap classification only) — the scenario's behavior doesn't exist in production code at all. Not a test-improve target in **any** mode: it is **not** written as a Phase-5 Story and **not** deferred to Phase 7 — Phase 7 accepts seam introductions only, and there is no seam to introduce for behavior that hasn't been written yet. It surfaces only as a feature-gap call-out in the report, same as `LOW_VALUE`'s advisory-only treatment.

**Story order follows the coverage-gap ranking (issue #1786).** When a
coverage percentage is a stated goal, the NO_REFACTOR Story set is written in
`coverage-gap-ranking.json` **rank order** — highest uncovered-line bucket
first — so Phase 5 spends its budget on the layer that actually holds the
missing coverage. Pass that order to `/issues-from-assessment` as the order to
preserve; it **does not re-derive an order of its own**, and neither a mutation
survivor count nor a finding's position in `/test-health`'s prose reorders the
set.

**Persistence.** Persist the classified finding set to
`.claude/memory/test-improve/<slug>/phase-4.md`.

**Human gate.** Present the Phase-5 Story set (NO_REFACTOR only) to the
operator. **Phase 5 does not run** until the operator approves the set.
