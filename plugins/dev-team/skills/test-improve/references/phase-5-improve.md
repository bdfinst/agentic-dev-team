Iterate the approved Phase-5 Story set. For **each Story**:

**Never dispatch multiple Stories' build loops in parallel against one shared
working tree (issue #1571).** Each Story's step 1 runs `/build`, which
`git add`/`git commit`s as it goes — two or more concurrent dispatches
against the same checkout race on the index and working files, and that race
is real: it has produced observed data loss (reverted test files, deleted
`.feature` files) even when the assigned files looked disjoint, because git
index/commit operations aren't file-scoped the way file edits are. Process
Stories one at a time in this session, or — if you fan out multiple Stories
concurrently via the `Agent` tool — dispatch every one of them with
`isolation: "worktree"` so each gets its own git working tree; disjoint file
assignment alone is not a substitute for worktree isolation here.

1. **Build** — invoke `/build <story-id>`. `/build` inherits the **no-refactor**
   mode from Phase 0: production-code changes are **rejected**. A Story that
   would require a production-code change is surfaced as a REFACTOR_REQUIRED
   deferral candidate and re-classified for Phase 6.
2. **Apply the Phase-0 binding mode.** If Phase 0 selected
   `xunit-with-annotations`, the resulting test names mirror the source
   scenario name and Given/When/Then lines appear as **leading comments**
   citing the source `.feature` file. In `bdd-runner` mode, the step
   definitions are filled in against the parser wired at Phase 3. In `none`
   mode, the test is authored idiomatically for the stack without
   feature-file citations.
3. **Coverage delta** — after `/build` closes the Story, invoke
   `/coverage-delta --workflow test-improve --story <id>`. The delta is
   appended to `.dev-team-reports/test-improve/<slug>/data/coverage-history.json`.
4. **Coverage-delta steering check (issue #1790).** After the delta is
   appended — **every Story, not only at the end of the phase** — run the
   trailing-streak check. Do not eyeball the history:

   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_delta_steering.py" \
     --history .dev-team-reports/test-improve/<slug>/data/coverage-history.json \
     --json
   ```

   - **Exit 0** — continue to the mutation-kill step, but read *which* exit-0
     status came back: `ok` means the last Story actually moved line coverage;
     `insufficient_history` means too few Stories have closed (or the latest
     Story's movement could not be measured) to judge a streak;
     `flat_streak_forming` means the latest Story did **not** move coverage but
     the streak is still short of the threshold — echo that one to the operator
     as a watch signal rather than silently treating it as `ok`.
   - **Exit 3** (`flat_streak`) — three or more consecutive Stories (the
     default; `--consecutive` and `--min-line-delta` tune it) moved line
     coverage by less than the minimum expected per-Story delta.
     **Surface it now, mid-phase** — a run once spent its entire Phase-5
     budget on an already-covered layer because this signal was only read at
     the end; **never defer it to the Phase-9 report.** Print the script's
     flat-Story list and running average, name the top `seam: absent` modules
     from `coverage-gap-ranking.json`, and prompt **`[t] re-check Phase-1
     targeting / [c] continue`** (shape `[t/c]` — `t` is unused elsewhere in
     this flow, and `c` keeps the "accept and move on" meaning it already has
     in mutation-kill's `[c/r/w/q]`):
     - **`[t]`** — re-read `coverage-gap-ranking.json` and re-order the
       remaining Story set into its rank order (Phase 4's rule, applied to
       what is left) before the next Story's `/build`. A remaining Story whose
       target module reads `seam: absent` under `refactor-mode: no-refactor` is
       re-classified **REFACTOR_REQUIRED for Phase 6 rather than retried** —
       retrying it under no-refactor is what produced the flat streak.
     - **`[c]`** — continue, recording `coverage_flat_streak: <n> stories` in
       `.claude/memory/test-improve/<slug>/phase-5.md` so Phase 8 and the
       report read it from a durable record instead of re-deriving it.
     - **Non-interactive runs** record the streak and continue — the same
       **record-and-continue posture, never a silent pass**.
   - **Exit 2** — the history file is missing or unreadable. Resolve it (the
     Story's `/coverage-delta` did not append) rather than treating the
     unknown as `ok`.
5. **Mutation-kill (`kill-loop` and `baseline+kill-loop`; skipped when `off`).**
   Invoke the **`mutation-kill` agent**
   with `--file <story-file> --max-rounds 3`. Residual survivors trigger the
   **`[c]ontinue / [r]etry / [w]aive / [q]uit`** prompt — the shape is
   `[c/r/w/q]`. `[c]` accepts the residual and moves on; `[r]` re-runs one
   more mutation-kill round; `[w]` waives the residual to `waivers.json`;
   `[q]` quits Phase 5.
6. **Go mutation-kill is advisory.** On Go stacks, `mutation-kill` logs
   survivors but makes **no commit** — the operator is instructed to apply
   changes manually. Advisory-only handling matches the Phase-0 Go advisory.

#### Pending-stub gate (`bdd-runner` mode only, issue #1391)

After **all Phase-5 Stories have closed**, and only when Phase 0 selected
`bdd-runner` binding mode, run the completion gate before Phase 5 may be
reported closed — a hard gate, not prose:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_stub_gate.py" --dir <step-definitions-dir>
```

(`<step-definitions-dir>` is wherever test-improve's own Phase 3 —
`/gherkin-derive`'s Step 4 (stub generation) / Step 5 (output paths) — wrote
step-definition files, recorded in `.claude/memory/test-improve/<slug>/gherkin.md`.)

- **Exit 0 (no pending stubs)** — Phase 5 proceeds to the end-of-phase review
  loop below.
- **Non-zero (pending stubs remain)** — Phase 5 is **not done**. Surface the
  gate's listed `file:line` pending step definitions to the operator; do not
  report the phase closed. Route each remaining stub back into the per-Story
  build loop (step 2 above — fill in the step definition against the parser
  wired at Phase 3) rather than silently leaving it pending.
- Skip entirely when binding mode is `none` or `xunit-with-annotations` (no
  step definitions exist to gate on).

#### End-of-phase review loop

After **all Phase-5 Stories have closed**, run the review loop over the
Phase-5 diff, writing evidence to
`.claude/memory/test-improve/<slug>/phase-5-review.json`:

<!-- include: references/review-loop.md -->
See `review-loop.md` for the parallel `/test-design` +
`/code-review` dispatch, the `/apply-fixes` step, the 2-iteration
`[r/w/q]` escalation cap, and the fixed evidence-schema fields.

**`/handoff` suggestion** (context-heavy review). Once the loop above closes, print: `Phase 5 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 6 (or --from-phase with no number to auto-detect the resume point)`
