**No prompt** when: `.dev-team-reports/test-improve/<slug>/refactor-backlog.md` does not exist (no `REFACTOR_REQUIRED` items were ever backlogged), the file exists but has zero entries (treated the same as absent), `phase-8.md` records `coverage_reprompt_fired: true` (Phase 8's own coverage-driven `[y/n]` already fired this run — no repeating the same question twice), or `phase-0.md` recorded `refactor-mode: refactor-allowed` (a Phase-6 `[b]` backlog entry under `refactor-allowed` mode is the operator's deliberate deferral, not a no-refactor constraint to lift — re-asking "re-run with refactor-allowed mode now?" would be nonsensical when that's the mode already in use).

**Otherwise** (backlog file has ≥1 entry, Phase 8 never fired its prompt,
and `phase-0.md` recorded `refactor-mode: no-refactor`), prompt **`[y/n]`**
— distinct from Phase 8's coverage-driven, mid-run prompt, this one is
backlog-driven and fires at close-out: *"N REFACTOR_REQUIRED items remain
backlogged. Re-run with refactor-allowed mode now? `[y/n]`"* (N = entry
count). `[n]` leaves the backlog as-is. `[y]` — Phase-0 answers are
immutable per-run, so tell the operator to re-run `/test-improve
<repo-path>` fresh, choosing `refactor-allowed`; this is a new invocation,
not `--from-phase`.
