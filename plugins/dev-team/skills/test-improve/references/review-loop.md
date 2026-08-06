Shared end-of-phase review loop: dispatch `/test-design` and `/code-review`
in parallel against the phase's diff, apply fixes, and iterate to a capped
round count before escalating to the operator. Phase 5 and Phase 7 both
invoke this loop verbatim against their own diff and write their own
phase-numbered evidence file using the fixed schema below.

1. **Dispatch in parallel** — `/test-design --since <base-sha>` and
   `/code-review --since <base-sha> --internal` run **concurrently** against
   the diff between the phase's base commit and HEAD. `--internal`
   (not `--json`) mirrors `/build`'s Step 6 backstop-review flag choice: it
   suppresses the `.dev-team-reports/code-review.md` write (this is a
   diff-scoped, phase-internal review, not a human-invoked top-level run —
   `knowledge/report-output-location.md`) while keeping the prose/
   `corrections/` output sub-step 2 depends on — `--json` would skip that
   output entirely.
2. **Apply fixes.** Run `/apply-fixes corrections/`, then **re-run
   `/code-review --internal`** to confirm.
3. **Iterate at most 2 rounds.** After **2 iterations** without clean
   `/code-review`, prompt the operator with **`[r]evise / [w]aive / [q]uit`**
   (shape `[r/w/q]`).
   - `[r]` triggers one more revise pass (may exceed the cap by operator
     consent).
   - `[w]` writes the outstanding finding set to
     `.claude/memory/test-improve/<slug>/waivers.json`, **tagged** with the
     finding list, and closes the phase.
   - `[q]` quits the phase with the loop unresolved.
4. **Evidence.** Write the calling phase's own review-evidence file with the
   fixed schema — fields: `base_sha`, `head_sha`, `farley_score`, `smells`,
   `code_review`, `iterations`, `escalated`.
