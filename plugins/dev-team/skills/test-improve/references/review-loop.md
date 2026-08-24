Shared end-of-phase review loop: dispatch the `/code-review` panel once
against the phase's diff, score the in-scope tests, apply fixes, confirm
them, and iterate to a capped round count before escalating to the operator.
Phase 5 and Phase 7 both invoke this loop verbatim against their own diff and
write their own phase-numbered evidence file using the fixed schema below.

1. **Dispatch the review panel — one panel per round (#1959).** Run
   `/code-review --since <base-sha> --internal` against the diff between the
   phase's base commit and HEAD. `--internal` (not `--json`) mirrors
   `/build`'s Step 6 backstop-review flag choice: it suppresses the
   `.dev-team-reports/code-review.md` write (this is a diff-scoped,
   phase-internal review, not a human-invoked top-level run —
   `knowledge/report-output-location.md`) while keeping the prose/
   `corrections/` output sub-step 3 depends on — `--json` would skip that
   output entirely.

   **This loop no longer dispatches `/test-design` alongside the panel.**
   `/test-design`'s two review agents — `test-review` and
   `test-smell-review` — both declare `Scope: always`, so
   `scripts/select_lenses.py` already returns them in `/code-review`'s own
   roster for any non-empty changeset. Dispatching both skills against one
   diff paid for the same two agents, over the same files, twice per round.
   The panel still runs them; only the duplicate dispatch (and
   `/test-design`'s own orchestration/aggregation layer) is gone.

   **Confirm the two test lenses actually ran — do not assume the roster
   kept them.** `/code-review`'s change-size gate (#1339) drops every
   `Scope: always` agent outside its `keepAgents` floor on a small diff, and
   `test-review`/`test-smell-review` are not in that floor. Read the panel's
   reported roster (it names every gate-driven drop). If either lens was
   dropped by a gate, dispatch it directly —
   `/review-agent test-review --internal` and/or
   `/review-agent test-smell-review --internal` — before proceeding. A
   test-improvement phase whose review skipped both test lenses has reviewed
   the wrong thing; this is the one lens pair this loop guarantees.

   `/test-design`'s forward-design worker (`test-design-advisor`) is not lost
   here either: it auto-fires only for untested production code or a
   single-production-file target, and a Phase-5/7 diff under this loop is
   test-and-seam-scoped, so it would not have fired. Reach for `/test-design`
   directly when you want forward design for a specific module — it is
   unchanged as a standalone skill and still runs inside `/test-health`.
2. **Score the in-scope tests.** Invoke `Skill(farley-score ...)` scoped to
   the phase diff's test files (indicators in
   `knowledge/test-file-indicators.md`). This is the one input the evidence
   schema needs that the panel does not produce; it is a direct worker call,
   not an orchestrator dispatch.
3. **Apply fixes, then confirm them narrowly (#1960).** Run
   `/apply-fixes corrections/`. To confirm the fixes landed, **do not re-run
   the full panel** — a whole-roster re-dispatch re-pays discovery cost to
   answer a confirmation question. Confirm the way `/code-review` step 6a
   and `/build`'s checkpoints already do:

   - **Deterministic-first triage (#1610).** When a fix is mechanical and the
     claim is deterministically checkable, close it with the project's own
     stack tooling — its linter/type-checker (`ruff`/`mypy`, ESLint/`tsc`,
     `pmd`, `dotnet format`/`dotnet build`, …), its test suite, or `grep` —
     never an agent.
   - **Verification-mode re-dispatch for the rest.** Re-dispatch **only the
     agents whose findings were fixed**, with the narrowed payload and the
     mandatory `insufficient-context` escape, resolving each agent's tier via
     `python3 "$CLAUDE_PLUGIN_ROOT/scripts/verify_tier.py" --agent <name>`.
     The payload contract, the escape's escalation path (an
     `insufficient-context` reply earns a **full-context** re-dispatch of
     that same agent at its discovery tier — never a shrug), and the
     declared-never-inferred tier-down rule are stated once in
     [`../../../knowledge/verification-mode.md`](../../../knowledge/verification-mode.md)
     and are not restated here.

   Discovery of *new* problems remains the initial panel's job (sub-step 1),
   which is unchanged — this sub-step only cheapens confirming what was just
   fixed.
4. **Iterate at most 2 rounds.** After **2 iterations** without clean
   `/code-review`, prompt the operator with **`[r]evise / [w]aive / [q]uit`**
   (shape `[r/w/q]`).
   - `[r]` triggers one more revise pass (may exceed the cap by operator
     consent).
   - `[w]` writes the outstanding finding set to
     `.claude/memory/test-improve/<slug>/waivers.json`, **tagged** with the
     finding list, and closes the phase.
   - `[q]` quits the phase with the loop unresolved.
5. **Evidence.** Write the calling phase's own review-evidence file with the
   fixed schema — fields: `base_sha`, `head_sha`, `farley_score`, `smells`,
   `code_review`, `iterations`, `escalated`. `farley_score` comes from
   sub-step 2. `smells` comes from the panel's own `test-smell-review`
   findings (sub-step 1) — the same agent's findings the removed
   `/test-design` dispatch used to aggregate, read from the panel result
   instead of from a second dispatch of it.
