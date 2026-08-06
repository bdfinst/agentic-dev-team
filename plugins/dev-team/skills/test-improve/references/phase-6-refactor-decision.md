With Phase 5 closed, present the **REFACTOR_REQUIRED** list deferred at
Phase 4. Each item is shown with three columns:

- **seam-needed** — the production-code seam the test would need (e.g.
  interface extraction, dependency injection, virtual method).
- **behavior-gained** — the untested behavior a Phase-7 refactor would
  unlock coverage for.
- **estimated-risk** — a qualitative risk marker (low / medium / high) for
  the specific refactor.

**Phase 6 branches on the Phase-0 `refactor-mode`.** Read `refactor-mode`
from `.claude/memory/test-improve/<slug>/phase-0.md` **before** rendering any prompt.
Entering Phase 7 *is* refactoring, so the choice made at Phase 0 governs
whether Phase 6 is a branch point at all.

**`refactor-mode: no-refactor` (the default) — informational, not a branch
point.** The operator declined refactoring at Phase 0, so the **`[y] enter
Phase 7` option does not exist** in this mode. Present the REFACTOR_REQUIRED
list as *"the following require refactoring and are out of scope in
no-refactor mode"* — the seam-needed / behavior-gained / estimated-risk
columns still render, so the operator sees the coverage and behavior left on
the table. Then **auto-backlog** every item to
`.dev-team-reports/test-improve/<slug>/refactor-backlog.md` (or update the parent
tracker when `--parent` was passed) and **continue to Phase 8** with the
current Phase-5 test suite as the target. The prompt collapses to a single
**acknowledge/continue** step (equivalent to today's `[b]`); when no operator
is attached, run it **non-interactively** — no keystroke is required and none
enters Phase 7. The sanctioned way to actually perform these refactors is the
Phase-8 coverage-below-90% re-run prompt, which offers a fresh
`refactor-allowed` invocation the operator explicitly opts into.

**`refactor-mode: refactor-allowed` — full decision prompt.** Prompt the
operator with **`[y] enter Phase 7 / [b] backlog and skip to Phase 8 /
[q] quit`** (shape `[y/b/q]`). The letter `y` was chosen deliberately
over `r` — `[r]` is already claimed by mutation-kill's `[c/r/w/q]` (retry) and
the review-loop's `[r/w/q]` (revise); a third `[r]` at the
highest-consequence prompt would confuse operators.

- **`[y]`** — advances to **Phase 7** (refactor-for-testability).
- **`[b]`** — writes the REFACTOR_REQUIRED items to
  `.dev-team-reports/test-improve/<slug>/refactor-backlog.md` (or updates the parent
  tracker when `--parent` was passed); **skips Phase 7** and runs **Phase 8**
  directly with the current Phase-5 test suite as the target.
- **`[q]`** — **quits** before Phase 8. No further phase runs; the final
  report reflects Phase-5 state only.
