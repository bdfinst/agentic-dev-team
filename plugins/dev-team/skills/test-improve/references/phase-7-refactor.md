Phase 7 runs **only when the operator picked `[y]` at Phase 6**. If Phase 6
returned `[b]` (backlog) or `[q]` (quit), Phase 7 is **skipped**.

**Hard mode gate — Phase 7 refuses to run under `no-refactor`.** Before any
Phase-7 work begins, `/test-improve` re-reads `refactor-mode` from
`.claude/memory/test-improve/<slug>/phase-0.md`. When it records
`refactor-mode: no-refactor`, Phase 7 **refuses to run** and is skipped —
**even if `[y]` is somehow reached**. Phase 6 offers no `[y]` in this mode,
so this gate is a defense-in-depth backstop: Phase 7 executes production-code
refactors the `no-refactor` operator declined at Phase 0, and the mode — not
the keystroke — is the final authority. Only `refactor-mode: refactor-allowed`
permits Phase 7 to execute.

**Seam-only production code changes.** `/build` in Phase 7 accepts **seam
introductions only** — interface extractions, dependency injection points,
virtual method promotions, factory wrapping. Any change beyond a seam is
rejected. Behavior modifications, refactors that alter semantics, and
opportunistic clean-ups are all out of scope.

**Existing tests are immutable.** Phase 7 **may not modify or remove existing tests** — `/build` rejects deletions and edits to any file under the stack's test directory that existed before Phase 7 started. The pre-Phase-7 suite must stay green throughout; a red pre-Phase-7 test halts the phase.

**Phase-5 precondition-check.** Each Phase-7 Story is paired with the
corresponding Phase-5 baseline Story that could not close under no-refactor.
Before `/build` runs a Phase-7 Story, `/test-improve` **verifies the paired
Phase-5 Story is closed and green**. A missing or failing Phase-5 baseline
halts that Story until the operator resolves it.

**Phase 5's parallel-dispatch warning (issue #1571) applies equally here** —
Phase 7 runs the same per-Story `/build` loop against the same shared
working tree, so **never dispatch multiple Phase-7 Stories' build loops
concurrently without `isolation: "worktree"` on every dispatch**; see
`phase-5-improve.md` for why the race is unsafe.

**End-of-phase review loop.** After all Phase-7 Stories close, run the
**same review loop as Phase 5**, writing evidence to
`.claude/memory/test-improve/<slug>/phase-7-review.json` using the same
fixed schema:

<!-- include: references/review-loop.md -->
See `review-loop.md` for the parallel `/test-design` + `/code-review`
dispatch, the `/apply-fixes` step, the 2-iteration `[r/w/q]` escalation
cap, and the fixed evidence-schema fields.

**`/handoff` suggestion** (same rationale as Phase 5). Once the loop above closes, print: `Phase 7 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 8 (or --from-phase with no number to auto-detect the resume point)`
