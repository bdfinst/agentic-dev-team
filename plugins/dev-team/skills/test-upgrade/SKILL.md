---
name: test-upgrade
description: >-
  General-purpose analyze-then-improve test workflow for any JS/TS, Go, Java, or
  C# codebase. A 4-phase orchestrator: analyze with /test-health, optionally
  derive Gherkin with /gherkin-derive, triage into work items, implement each
  Story with /build + /coverage-delta + the mutation-kill agent, and validate
  with /quality-targets-converge. Local-first, BDD optional, Go-aware. Use when
  the user says "upgrade our tests", "improve test quality", or runs
  /test-upgrade. Lighter and general-purpose where /test-modernize is a
  brownfield legacy rescue.
argument-hint: "<repo-path> [--parent <issue-url>] [--analyze-only] [--from-phase <n>]"
role: orchestrator
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill(test-health *), Skill(gherkin-derive *), Skill(issues-from-assessment *), Skill(build *), Skill(coverage-delta *), Skill(quality-targets-converge *)
---

# Test Upgrade

Role: orchestrator. This command sequences existing skills/agents through a
four-phase analyze-then-improve workflow; it does **not** implement, audit, or
write tests itself. Each phase is **delegated** to the worker skill or agent that
owns it, and per-phase progress is persisted to `memory/test-upgrade/<slug>/phase-<n>.md`
so `/continue` (and `--from-phase`) can resume.

You have been invoked with the `/test-upgrade` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill or agent (`/test-health`, `/gherkin-derive`, `/issues-from-assessment`, `/build`, `/coverage-delta`, `mutation-kill`, `/quality-targets-converge`); never re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit approval.
3. **Confirm the approach first.** Resolve every ambiguous input in one batch at Phase 0 before any work starts.
4. **Be concise.** Report each phase's outcome and the next gate, nothing more.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--parent <issue-url>` — optional tracker issue URL; the host selects the CLI (ADO / GitHub / GitLab / Jira). Omit for **local-files mode** (the default), which writes to `./reports/test-upgrade/`.
- `--analyze-only` — exit after Phase 1 (report only; no code changes).
- `--from-phase <n>` — resume from phase `n` when `memory/test-upgrade/<slug>/phase-<n>.md` exists.

## Phase 0 — Approach contract

Resolve everything in one batch, then persist it:

1. **Detect language(s)** from build manifests: `package.json` (JS/TS), `pom.xml` / `build.gradle*` (Java), `*.csproj` (C#), `go.mod` (Go). A repo may be polyglot — record each.
2. **Go advisory up front.** If `go.mod` is present, surface immediately that Go mutation testing is **advisory only** (go-mutesting is alpha-quality; the survivor count is not a gate) and recommend `go test -fuzz` as the production-quality complement (see `skills/mutation-testing/references/tool-setup.md`).
3. **Refactoring mode.** The coverage target is **≥ 90% line and branch**. Ask, defaulting to **no-refactor**:

   > Allow production-code refactoring to reach coverage targets? (default: **no**)
   >
   > - **no-refactor** (default) — add tests only at existing seams; reach as high as possible without changing production code. `REFACTOR_REQUIRED` gaps go to backlog. The 90% target is the goal, but whatever is achieved without refactoring is accepted.
   > - **refactor-allowed** — promote `REFACTOR_REQUIRED` gaps into the work queue; modify production code only to introduce a testable seam. **Constraint: only test *additions* are permitted — existing tests may not be modified or removed.**

   Record the chosen mode in `memory/test-upgrade/<slug>/phase-0.md`. Every later phase reads it.
4. **BDD binding mode.** Present the 5-question rubric from `knowledge/references/bdd-value-guide.md` and recommend a mode (`≥3 yes → bdd-runner`, `1–2 → xunit-with-annotations`, `0 → none`). The operator may **override** the recommendation.
5. **Quality targets** — defaults coverage ≥ 90%, surviving mutants = 0, determinism = 100%, pre-merge wall-clock = fastest achievable. `.dev-team/quality-targets.json` overrides per-repo; load it if present.
6. **Tracker or local files.** With `--parent`, map the host → CLI (`gh` / `az boards` / `glab` / `acli`) and probe it; if missing, fall back to local files. Without `--parent`, **local-files mode** is the default.

Print the resolved inputs (languages, Go advisory, refactoring mode, binding mode, targets, sink, `<slug>`) and proceed. If `--from-phase <n>` was given, jump to that phase.

## Phase 1 — Analyze (`/test-health`)

Delegate entirely to `/test-health`. Its output is the gap table classified
`NO_REFACTOR` / `REFACTOR_REQUIRED` / `LOW_VALUE` (from #431) plus the
**Recommended removals** table. Summarize; do not re-derive.

**Human gate.** If `--analyze-only` was passed, **exit here** with the report and
**no code changes**.

## Phase 1b — Derive Gherkin (optional; skip when binding mode is `none`)

When the binding mode chosen in Phase 0 is not `none`, delegate to
`/gherkin-derive <repo-path> --mode <mode> --repo-slug <slug>`. It writes
`.feature` files and (in `bdd-runner` mode) pending step-definition stubs, and
records the surface inventory to `memory/test-upgrade/<slug>/gherkin.md`.

**Human gate** — the operator reviews and edits the `.feature` files before any
test binds to them.

## Phase 2 — Triage (`/issues-from-assessment`)

Delegate to `/issues-from-assessment` to convert the health report into work
items. How each gap class is handled depends on the **mode** chosen in Phase 0:

| Gap classification | no-refactor mode | refactor-allowed mode |
|---|---|---|
| `NO_REFACTOR` | implement Stories | implement Stories |
| `REFACTOR_REQUIRED` | **backlog** (deferred) | **promoted** to implement Stories |
| `LOW_VALUE` | Skipped section with rationale | Skipped section with rationale |
| Recommended removals | removal PRs | **deferred** — documented, not executed; existing tests are the safety net for the production-code changes |

**Human gate** — the operator approves the work-item set.

## Phase 3 — Implement

For each Story in dependency order (`NO_REFACTOR` first; `REFACTOR_REQUIRED` only
in refactor-allowed mode):

1. **`/build`** (RED-GREEN-REFACTOR with inline `/code-review`).
   - **no-refactor mode** — `/build` adds tests only; production code is **read-only**.
   - **refactor-allowed mode** — `/build` is constrained to test additions plus the *minimum* production-code change that introduces the required testable seam. It must **not modify or remove any existing test**, and the pre-build suite must stay green throughout.
2. **Binding mode applied:** `none` → plain xUnit; `xunit-with-annotations` → test names mirror scenario names with Given/When/Then in leading comments; `bdd-runner` → implement the step defs to green.
3. **Coverage delta:** `/coverage-delta <repo-path> --workflow test-upgrade --story <id>` to measure coverage movement for the Story. (Omit `--story-files` — mutation is the `mutation-kill` agent's job in the next step, not `/coverage-delta`'s internal gate, so the two never double-run.)
4. **Mutation improvement (mutation-kill agent):** after `/coverage-delta` reports green, invoke the `mutation-kill` agent `mutation-kill --file <story-file> --max-rounds 3`. The agent loops (scoped tool → survivors → generate tests → verify → commit → repeat) until survivors stop decreasing or max rounds is reached. **For Go, `mutation-kill` runs advisory** — it logs survivors and the generated tests but **does not commit**; the operator applies them manually.

   **Mutation halt prompt** (surface when `mutation-kill` exits with remaining survivors — hard kills only, timeouts excluded):

   ```
   ⚠ Story <id> — <n> survivors remain after mutation-kill (hard kills only; timeouts excluded)

   Surviving mutation types:
       Statement   — missing code paths; new tests required, not stronger assertions
       String      — assertion too broad; mutation-kill could not find a value to assert
       …

   Actions:
     [c] continue  — accept remaining survivors and advance to the next Story
     [r] retry     — adjust test scope and re-run mutation-kill for this Story
     [w] waive     — record reason; survivors carry forward to Phase 4
     [q] quit      — halt the workflow

   Choose [c/r/w/q]:
   ```

**Human gate** — the coverage delta + `mutation-kill` result are accepted before advancing to the next Story.

## Phase 4 — Validate (`/quality-targets-converge`)

Delegate to `/quality-targets-converge`, which loops until all four targets are
met or each gap is waived with a reason. If survivors remain after Phase 3, it
may invoke `mutation-kill --all --max-rounds 5` for a final full-pass attempt
before declaring the mutation target unmet. The **Go mutation target is advisory
only** throughout.

**If coverage < 90% at the end of Phase 4 in no-refactor mode**, surface:

```
Coverage achieved: <line>% line / <branch>% branch (target: 90%)
Gap: <delta>% — closed by these REFACTOR_REQUIRED items currently in backlog:
  • <item> — <why a seam is needed>
  • …

To pursue 90%, re-run and choose refactor-allowed at Phase 0:
  /test-upgrade <repo-path>
  Phase 0 re-runs the approach contract — select "refactor-allowed" to promote
  the above items into the work queue (the new mode overwrites phase-0.md). The
  prior Phase 1 health report is reused, so analysis is not repeated; existing
  tests stay locked (additions only) for the run.
  (Do not use --from-phase here: it reads the old mode from phase-0.md and would
  keep no-refactor.)
```

**Final report:** achieved coverage % (line + branch), the **honest mutation
score** (hard kills / effective total, with **timeouts reported separately**),
wall-clock, PRs opened, any waived targets with reasons, and — in no-refactor
mode — the backlogged `REFACTOR_REQUIRED` items that would close the remaining
coverage gap.

## Key differences from `/test-modernize`

| `/test-modernize` | `/test-upgrade` |
|---|---|
| Brownfield legacy rescue | **General-purpose** (any codebase) |
| `cd-test-architecture` drives analysis | `/test-health` drives analysis |
| Disable-cannot-fail phase | No disable phase |
| Gherkin authoring required | Optional (BDD value gate) |
| Tracker required | **Local-first**; tracker optional |
| 5 phases + heavy ceremony | 4 phases, lighter gates |
| No `LOW_VALUE` classification | `LOW_VALUE` drives removals |
| `/mutation-testing` advisory | `mutation-kill` autonomous loop |

## Notes

- Every phase delegates to its worker; the orchestrator only sequences, gates, and persists progress.
- `--from-phase <n>` resumes from `memory/test-upgrade/<slug>/phase-<n>.md`; the refactoring mode and binding mode are re-read from `phase-0.md`.
