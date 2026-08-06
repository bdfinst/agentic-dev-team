Gherkin derivation is **conditional on the Phase-0 BDD rubric answer**. It
runs only when the operator opted in to a binding mode other than `none`.

**Binding mode `none` — skipped entirely.** When `phase-0.md` recorded binding
mode `none`, Phase 3 is **skipped**: `/gherkin-derive` is **not invoked**, no
`.feature` files are written, no runner is added. **Phase 1 follows Phase 2
directly** in this case — the executed sequence becomes `0 → 2 → 1 → 4 → 5 →
6 → 7/8 → 9` (one fewer named phase; the banner's `<position>` counter still
advances 1-9 monotonically).

**Binding mode `xunit-with-annotations` — .feature files without a runner.**
Invoke `/gherkin-derive --workflow test-improve --mode xunit-with-annotations`.
The skill merges scenarios into `.feature` files under gherkin-derive's
resolved destination (recorded in `.claude/memory/test-improve/<slug>/gherkin.md` —
typically `features/test-improve/`, but dynamically resolved per the repo's
own BDD convention, not a fixed path — see `/gherkin-derive`'s Step 2)
— an existing file's prior content (hand-authored, or enriched by
`/feature-coverage-analyzer`) is preserved; only genuinely new scenarios are
appended (issue #1420) — and **no runner dependency** is added to the project.
The corresponding xUnit tests (authored in Phase 5) will carry the scenario
name plus Given/When/Then leading comments that cite the `.feature` file, but
they run through the existing xUnit runner.

**Binding mode `bdd-runner` — native parser wired.** Invoke
`/gherkin-derive --workflow test-improve --mode bdd-runner`. The stack profile
selects the native parser (`cucumber-js` for JS/TS, `SpecFlow` / `Reqnroll` for
.NET, `cucumber-jvm` for Java, `godog` for Go). `/gherkin-derive`:

- adds the parser as a project dependency,
- generates pending step-definition stubs,
- merges scenarios into `.feature` files under its resolved destination
  (same dynamic resolution as `xunit-with-annotations` mode, recorded in
  `.claude/memory/test-improve/<slug>/gherkin.md`), preserving any existing
  enrichment the same way that mode does (issue #1420).

**Persistence.** Record the surface inventory and (in `bdd-runner` mode) the
parser wiring to `.claude/memory/test-improve/<slug>/gherkin.md`.

**Human gate.** After Phase 3 produces `.feature` files (or parser wiring in
`bdd-runner` mode), present them to the operator for review — including
`gherkin_failure_path_gate.py`'s findings (issue #1420) as part of what's
being approved, the same reviewed-before-proceeding weight the
characterization-scenario call-out already carries, not an inert report
line. **Phase 1 does not run** until the operator approves.

**In `bdd-runner` mode with pending step definitions**, Phase 3's own
not-done statement (`../../gherkin-derive/SKILL.md` Step 6) and Phase 5's later
hard block on this same state (below) describe one fact at two checkpoints,
not two separate requirements — both name `/build` (Phase 5's own per-Story
build loop) as the remediation. Because Phase 5 already owns "what happens
next" for this state, `gherkin-derive`'s own proactive "continue into
`/build` now?" ask is suppressed here — it fires only for a genuinely
standalone invocation with no enclosing orchestrator.
