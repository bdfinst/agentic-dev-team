Verify the improved suite meets the Phase-0 quality targets. Delegate to
`/quality-targets-converge --workflow test-improve --refactor-mode <value>`
(`phase-0.md`'s `no-refactor` or `refactor-allowed`) — the skill routes
memory and plan paths under `test-improve/` (per Slice 11), and threading
the flag keeps the operator's no-refactor choice enforced past Phase 6 via
its own dispatch-table gating.

**Mutation target per mode.** The mutation target reads differently for each
Phase-0 mutation mode:

- **`off` — skipped (not waived).** The mutation target is **skipped** and marked
  "not enabled for this run" — it is **not waived**. Skipping and waiving are
  distinct outcomes: a waiver signals a target failed and the operator accepted
  the gap; a skip signals the target was never in scope for this run.
- **`kill-loop` — final-survivor-only.** No Phase-2 baseline was taken, so there is
  no before/after delta; the target reports the **final surviving-mutant count**
  from the Phase-5 kill loop.
- **`baseline+kill-loop` — baseline-delta.** The target reports the
  **baseline-to-achieved mutation delta** against `baseline-mutation.json`.

**Go mutation advisory.** When the resolved stack is Go and mutation is not `off`,
the mutation target is **advisory-only** (survivor count is not a gate). The
target reads with the "advisory only — go-mutesting is alpha" footnote and
the run may pass regardless of mutation numbers.

**Branch-scoped mutation validation (issue #1208).** `/quality-targets-converge`
scopes its Phase-8 mutation measurement to the **branch-vs-base cumulative
changed set** — the production source exercised by the tests this branch
changed across all its sessions — never the whole repo. It still reports a
whole-repo score by splicing the freshly-measured changed files over the
**persisted** Phase-2 baseline (`baseline-mutation.json`), and reports any
module it could not measure (OOM/timeout) as **held at baseline** rather than
omitting it. No extra flag is threaded through the delegation above — the
worker resolves the branch base itself using the same idiom as `/build`'s
Farley-Score step. The whole-repo splice relies on the
`.dev-team-reports/test-improve/<slug>/data/baseline-mutation.json` that
Phase 2 persisted directly and unconditionally (see
`phase-2-baseline.md`) — always
available for this same run; there is no separate copy to fall back on or
diverge from.

**Coverage < 90% in no-refactor mode.** When Phase 8 closes with coverage
below 90% and Phase 0 recorded `refactor-mode: no-refactor`,
`/test-improve` surfaces a **re-run prompt** shaped **`[y/n]`**: *"Coverage is
below 90% in no-refactor mode. Re-run in refactor-allowed mode to close the
gap? `[y/n]`"*. The prompt names the **backlogged REFACTOR_REQUIRED items**
that would close the gap (drawn from `.dev-team-reports/test-improve/<slug>/refactor-backlog.md`
when `[b]` was picked at Phase 6, or from the Phase-4 deferred list when
Phase 6 was not reached). Whenever shown, `phase-8.md` records `coverage_reprompt_fired: true` plus the answer — the durable source Phase 9's close-out prompt reads to avoid re-asking (see `phase-9-close-out-prompt.md`).

**Evidence.** Persist target outcomes to
`.claude/memory/test-improve/<slug>/phase-8.md`.

**Test-count-by-type recount.** Alongside the target-outcome persistence
above, perform the **identical** classification pass Phase 1's
"Test-count-by-type snapshot" defined — same six-type criteria, same
tie-break rule, same repo-path scope Phase 1 used (not a re-scoped or
differently-scoped recount) — and persist
`.dev-team-reports/test-improve/<slug>/data/test-counts-after.json` — written
directly to the same git-tracked `data/` sibling as `test-counts-before.json`
(same no-other-consumer rationale) — in the identical shape as
`test-counts-before.json` (same six keys, same order, zero-count keys
present). See Phase 1's own instruction for the full classification
mechanism; this pass does not restate it.

**`/handoff` suggestion** (context-heavy re-measurement). Once the recount above is persisted, print: `Phase 8 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 9 (or --from-phase with no number to auto-detect the resume point)`
