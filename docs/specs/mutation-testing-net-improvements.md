<!-- spec-version: 1 -->
# Spec: .NET Mutation-Testing Improvements (issue #528)

**Format:** dev-team `/specs` v1

## Intent Description

Eight improvements to the dev-team plugin's mutation-testing surface, derived from a real .NET 10 / ASP.NET Core mutation drive (57.69% → 75.75%, 448 new tests, 5 waves). The current agent spec and C# reference silently misrepresent the Stryker.NET score, offer no `NoCoverage`-first prioritization, force a serial file-by-file loop, and lack build/exclusion guardrails — each of which cost real time on the drive.

The change updates three files:

- `plugins/dev-team/agents/mutation-kill.md` — score formulas (report both honest and Stryker-reported), NoCoverage-first prioritization, infrastructure-exclusion detection, `--parallel <n>` flag and orchestration logic, stale-build step, structurally-untestable pattern catalog.
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` — `--since` incremental-run pattern with the "verification-config-has-no-since" trap called out, infrastructure exclusion template, NoCoverage denominator note. The `--report-file-name` correction from issue #522 stays as-is (already landed).
- `plugins/dev-team/hooks/mutation-adapters/stryker-net.sh` — env-var-gated `--since` pass-through: `STRYKER_SINCE_TARGET=<ref>` + `CI!=true` adds `--since:<ref>` to the run; unset in CI.

Item 3 (parallel agents) lands as a real `--parallel <n>` flag with orchestration logic, per user decision. Item 7 lands as env-var-gated pass-through only, per user decision. Item 8 is a patch checklist; every row folds into items 1–7 or the two files above — no new `mutation-test-workflow.md` doc is created (that file does not exist and the issue's rows all have homes in existing files).

The PR body must include `Closes #528`. This diff touches code and hook files, so **auto-merge is not armed** — merge requires explicit human approval per the repo working rules.

## Architecture Specification

**Files touched:**

1. `plugins/dev-team/agents/mutation-kill.md`
2. `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`
3. `plugins/dev-team/hooks/mutation-adapters/stryker-net.sh`
4. `tests/agents/mutation_kill_agent_tests.bats` — update existing formula assertion + add tests for new sections
5. `tests/hooks/stryker_net_adapter_tests.bats` — add `--since` pass-through tests

**Changes per file:**

### `mutation-kill.md`

- Replace the "The honest score — hard kills only" section:
  - `honest_score = Killed / (Killed + Survived + NoCoverage)` (gates on this)
  - `reported_score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)` (reported for parity with Stryker HTML report)
  - `NoCoverage` is a first-class signal: each NoCoverage→Killed conversion improves the score as much as killing a Survived mutant, and is usually easier (any test reaching the line, not one detecting a specific value change). Prioritize NoCoverage coverage **before** attacking hard Survived mutations.
  - Timeout continues to be reported separately and excluded from the gate numerator; the change is that `NoCoverage` is now in the denominator, matching Stryker.NET 4.x.
- Add a "Step 0: Build first" preamble to the Loop:
  - `dotnet build <SOLUTION> -c Debug --nologo` (or language equivalent). Build failure = STOP. Never use `--no-build` when running mutation testing.
- Add "Infrastructure exclusion detection" section (after baseline parse, before generation loop):
  - Scan for files where `score < 15%` AND `NoCoverage > 50%` of effective mutants
  - Match filenames: `Startup.cs`, `Program.cs`, `*Filter.cs`, `*Middleware.cs`, `*Logger*.cs`, `*HealthCheck*.cs`, `*.Designer.cs`
  - For each match, ask: "DI registration / exception handlers / generated code that the test surface can't reach?" — yes → add to mutate exclusion list with a documented reason; no → keep in scope
  - Log format: `EXCLUDED <file> — <reason>: <mutation types> are equivalent in <test surface>`
- Add `--parallel <n>` flag to the Invocation block, and a new "Parallel execution (Phase 4)" section:
  - With `--all --parallel <n>`: sort files by survivor count (desc), cap at first `4×n` candidates, group into `n` batches of up to 4 files each, spawn `n` sub-agents in parallel via the Agent tool (not git worktrees — test-file writes don't conflict with source-file reads), each sub-agent reads survivors from the baseline JSON and targets in priority order, synthesize results, repeat for next batch if survivors still exceed threshold
  - Agent count per batch: 3–4 for easy types (String / Equality / ObjectInit), 1–2 for hard types (Statement / Block) to avoid conflicting test edits
  - This is orthogonal to the existing `--concurrency` flag (which is for worktree-based file-level parallelism); `--parallel` is Agent-tool-based, in-process, targeted at Phase 4 sub-agent fan-out
- Expand "Structurally unkillable files" section to catalog three specific patterns:
  1. `#if DEBUG` / `#if RELEASE` compilation blocks — code under test doesn't exist in the test build
  2. Service-locator pattern (`HttpContext.RequestServices.GetService<T>()`) — cannot inject mocks without full IServiceProvider per test; requires refactor
  3. Pure DI registration (`services.AddX()`, `builder.Services.AddX()`) — TestStartup/TestServer overrides the real container; exclude the whole file from the mutate glob
  - Each with the `EXCLUDED` log line format already documented in the file. Action: log as technical debt, never spend rounds trying to kill.

### `csharp-stryker-net.md`

- Add "`--since` incremental-run pattern" subsection under `## Run (scoped)`:
  - Dev-shard config example with `"since": { "enabled": true, "target": "main" }`
  - Explicit trap callout: **`--since` limits mutations to source files that changed since the git ref; test-file changes do NOT trigger source mutations. A verification run through a `--since` config silently produces 0 results — always use a separate verification config with no `since` block.**
- Add "Infrastructure exclusion template" subsection with the `mutate` glob showing `!**/Startup.cs`, `!**/Program.cs`, `!**/*ExceptionFilter.cs`, `!**/*ExceptionFormatter.cs`, `!**/*LoggerService.cs`, `!**/*.Designer.cs`.
- Add "NoCoverage denominator note" subsection:
  - Stryker.NET score formula: `(Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)`
  - NoCoverage sits in the denominator even though those mutants are never tested. A file with 27 NoCoverage mutants at 0% score drags overall score down more than a file with 20 Survived at 70%. Fix NoCoverage first.
- Preserve every existing correction from issue #522 (spec `stryker-net-workflow-corrections.md`); no rewrites.

### `stryker-net.sh`

- After `stryker_args` is built, before the `_timeout ... dotnet stryker` call, append this guarded block:

  ```bash
  # Dev-only: --since limits mutation to files changed vs the target ref.
  # Skipped in CI (full run needed for the gate score).
  if [ "${CI:-}" != "true" ] && [ -n "${STRYKER_SINCE_TARGET:-}" ]; then
    stryker_args+=(--since:"$STRYKER_SINCE_TARGET")
  fi
  ```

- No behavior change when `STRYKER_SINCE_TARGET` is unset or when `CI=true`.
- Document the env var in the file header comment near `STRYKER_NET_REPORT`.

**Test updates:**

- `tests/agents/mutation_kill_agent_tests.bats`
  - Update the honest-score assertion (line ~27) to match the new formula: `Killed / (Killed + Survived + NoCoverage)`.
  - Add tests for: `--parallel` flag exists, NoCoverage-first prioritization is documented, infrastructure exclusion detection is documented, `dotnet build` step precedes the loop, all three structurally-untestable patterns are cataloged.
- `tests/hooks/stryker_net_adapter_tests.bats`
  - Add: `STRYKER_SINCE_TARGET` set + `CI` unset → args include `--since:<ref>`
  - Add: `STRYKER_SINCE_TARGET` set + `CI=true` → args do NOT include `--since`
  - Add: `STRYKER_SINCE_TARGET` unset → args do NOT include `--since` (baseline behavior preserved)

**Constraints:**

- Only the three files (plus their tests) change. No new files created; `mutation-test-workflow.md` is explicitly NOT created (does not exist; not in repo).
- Shard-aware execution guidance in `csharp-stryker-net.md` is preserved; new sections are additive.
- `--parallel` and `--concurrency` are orthogonal, independently overridable, both documented.
- Every gate/exit condition documented in the existing agent (no-improvement exit, duplicate detection, revert on failure, structurally-unkillable exclusion) is preserved.
- `/agent-audit` must pass on the modified agent file (structural / frontmatter / registry).
- Bats suites (`stryker_net_adapter_tests.bats`, `mutation_kill_agent_tests.bats`) pass in `scripts/ci-local.sh`.
- PR title uses conventional-commit prefix `feat(mutation-testing):` — this is a code + hook change that adds capability, so it's `feat:`, not `docs:`.

**Non-goals:**

- No refactor of `SKILL.md` workflow steps for mutation-testing.
- No change to the JSON envelope, `--emit-json` schema, or workflow-callers registry.
- No auto-detection of `--since` target — user must set `STRYKER_SINCE_TARGET` explicitly (per user decision).
- No auto-detection of xunit.v3 in the adapter (that's issue #522's out-of-scope deferral, still deferred).
- No worktree change; `--parallel` uses in-process Agent tool fan-out, not worktrees.

## Acceptance Criteria

Every criterion is observable by grepping a file or running a specific test suite.

1. **Honest score formula updated.** `grep -F "Killed / (Killed + Survived + NoCoverage)" plugins/dev-team/agents/mutation-kill.md` returns 1 line. The reported-score formula `(Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)` is also present. Both are labeled: `honest_score` gates; `reported_score` is for HTML-report parity.
2. **NoCoverage-first prioritization documented.** `grep -c -i "NoCoverage" plugins/dev-team/agents/mutation-kill.md` returns ≥ 3 (formula, first-class-signal note, prioritization guidance). The file states NoCoverage → Killed is prioritized before hard Survived mutations, with the "any test reaching the line" rationale.
3. **Infrastructure exclusion detection documented.** `mutation-kill.md` contains a section that names the score/NoCoverage thresholds (< 15% score, > 50% NoCoverage) and lists the file patterns (`Startup.cs`, `Program.cs`, `*Filter.cs`, `*Middleware.cs`, `*Logger*.cs`, `*HealthCheck*.cs`, `*.Designer.cs`). The `EXCLUDED <file> — <reason>:` log format is present.
4. **`--parallel <n>` flag present and documented.** The Invocation block includes `[--parallel <n>]`. A "Parallel execution" section explains agent-tool fan-out (not worktrees), batch sizing (4 files per agent, 3–4 agents for easy types, 1–2 for hard), and the mutation-type gating for parallel dispatch.
5. **Stale-build step documented.** `mutation-kill.md` contains a "Build first" step preceding the Loop, showing `dotnet build ... --nologo` and the rule "never use `--no-build` when running mutation testing".
6. **Structurally untestable patterns cataloged.** The "Structurally unkillable files" section documents all three patterns (`#if DEBUG`/`#if RELEASE`, service-locator, pure DI registration) with the `EXCLUDED` log line for each.
7. **`--since` incremental-run pattern added to C# reference.** `csharp-stryker-net.md` contains a subsection showing the `"since": { "enabled": true, "target": "main" }` config block and the explicit trap: "test-file changes do NOT trigger source mutations; verification runs must use a separate config with no `since` block".
8. **Infrastructure exclusion template added to C# reference.** `csharp-stryker-net.md` contains a `mutate` glob template with `!**/Startup.cs`, `!**/Program.cs`, `!**/*ExceptionFilter.cs`, `!**/*ExceptionFormatter.cs`, `!**/*LoggerService.cs`, `!**/*.Designer.cs`.
9. **NoCoverage denominator note added to C# reference.** `csharp-stryker-net.md` contains the Stryker.NET score formula `(Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)` and the "fix NoCoverage first" rationale.
10. **`--since` env-var pass-through added to adapter.** `stryker-net.sh` includes the guarded block: `if [ "${CI:-}" != "true" ] && [ -n "${STRYKER_SINCE_TARGET:-}" ]; then stryker_args+=(--since:"$STRYKER_SINCE_TARGET"); fi`. The env var is documented in the file header comment.
11. **Adapter tests cover all three env-var branches.** `stryker_net_adapter_tests.bats` includes tests that verify: (a) `STRYKER_SINCE_TARGET=main` + `CI=` → `--since:main` in the command line; (b) `STRYKER_SINCE_TARGET=main` + `CI=true` → no `--since`; (c) `STRYKER_SINCE_TARGET=` → no `--since` (baseline preserved).
12. **Agent tests updated for new formula.** `mutation_kill_agent_tests.bats` asserts `Killed */ *\(Killed \+ Survived \+ NoCoverage\)` (or an equivalent regex) rather than the old `Killed / (Total - Ignored - CompileError - Timeout)` form.
13. **Existing invariants preserved.** All pre-existing tests in `mutation_kill_agent_tests.bats` still pass (frontmatter, 500-line ceiling, priority table, duplicate detection, no-improvement exit, revert-on-failure, structurally-unkillable exclusion, Go advisory).
14. **Local CI gate green.** `bash scripts/ci-local.sh` (or the mutation-adapter and agent bats suites at minimum) exits 0.
15. **`/agent-audit` passes.** Structural, frontmatter, and registry checks on the modified agent file pass.
16. **PR closes the issue on merge.** PR body contains `Closes #528`. `gh pr view <num> --json body` shows the string. Merging the PR auto-closes issue #528.
17. **PR title conventional.** PR title is `feat(mutation-testing): ...` (bumps minor version via release-please). Not `docs:`, not `fix:`.
18. **Auto-merge NOT armed.** Because the diff touches `agents/`, `hooks/`, and `tests/`, the repo working rule mandates explicit human merge. Do not execute `gh pr merge <num> --auto`.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Item 3 shape — doc-only pattern description vs real `--parallel <n>` flag with orchestration logic? | `requires-stakeholder-input` | human | User chose "Add `--parallel <n>` flag and orchestration logic". Larger surface than doc-only, but delivers the productivity win the issue describes. |
| Item 7 shape — env-var-gated pass-through vs adapter-side auto-detection of `since` target? | `requires-stakeholder-input` | human | User chose env-var-gated pass-through. Auto-detection would risk silent zero-mutation runs users didn't ask for; explicit opt-in via `STRYKER_SINCE_TARGET` is the safer default. |
| Item 8 target — patch a nonexistent `mutation-test-workflow.md`, or fold rows into existing files? | `requires-stakeholder-input` | human | User chose "fold into `mutation-kill.md` + `csharp-stryker-net.md`". `find . -name 'mutation-test-workflow*'` returns nothing; every row in the item-8 table maps directly onto items 1–7 or the C# reference. |
| Where does `--parallel` live — flag on the mutation-kill agent, or a new orchestration skill? | `inferable` | inference | Issue text describes it as an agent-level fan-out pattern within the existing Phase 4 loop. `mutation-kill` already has `--concurrency` (worktree-based); adding `--parallel` (Agent-tool-based) as a sibling flag on the same agent is consistent with the existing surface. A new orchestration skill would duplicate scope. |
| Should `--parallel` also use git worktrees? | `inferable` | inference | Issue text explicitly says "test files don't conflict with source files, so git worktrees aren't needed. Simple parallel Agent tool calls are sufficient." Documented accordingly. |
| Priority: NoCoverage vs Survived. Should the agent be **required** to attack NoCoverage before Survived, or is this advisory? | `inferable` | inference | Issue text says "Prioritize NoCoverage coverage BEFORE attacking hard Survived mutations" — imperative. Documented as agent behavior, not advisory. |
| Should `--since` pass-through also validate that `STRYKER_SINCE_TARGET` is a valid git ref before passing it? | `inferable` | inference | No. The adapter is a thin pass-through; Stryker.NET itself will surface the invalid-ref error clearly, and adding pre-validation would duplicate git plumbing in the hook. Keep the block minimal (matches the exact snippet in the issue). |
| Auto-merge armed? | `inferable` | inference | Repo CLAUDE.md working rules: only diffs touching only `*.md` (+ non-shipping metadata) auto-merge. This diff touches `.sh`, `.bats`, and agent files — explicit human merge required. Do not arm auto-merge. |
| Conventional-commit prefix — `feat:`, `fix:`, or `docs:`? | `inferable` | inference | This adds capabilities (`--parallel` flag, `--since` pass-through, NoCoverage prioritization) and changes agent behavior — `feat(mutation-testing):`. Bumps minor version via release-please, correct for user-visible new capability. The issue title uses `fix:` but the actual change set is additive; PR title takes precedence. |
| Should `honest_score` denominator change break existing consumers? | `inferable` | inference | The formula is internal to the agent's decision-making and reporting. No JSON schema field, no `--emit-json` payload, no workflow-caller contract depends on the exact denominator. Only the agent test file (`mutation_kill_agent_tests.bats`) asserts it — updated in this same PR to match. Safe to change. |

## Consistency Gate

- [x] Intent is unambiguous — three files, eight items, decisions on all three ambiguous axes captured explicitly.
- [x] Every behavior/goal maps to an acceptance criterion — item 1 → criterion 1–2; item 2 → criterion 3; item 3 → criterion 4; item 4 → criterion 5; item 5 → criterion 6; item 6 → criterion 7–9; item 7 → criterion 10–11; item 8 folded into criteria 1–9.
- [x] Architecture constrains without over-engineering — three files, minimal new sections, no new abstractions, no worktree changes, no schema changes.
- [x] Terminology consistent across artifacts — "honest_score", "reported_score", "NoCoverage", "STRYKER_SINCE_TARGET", "`--parallel <n>`" used identically in Intent, Architecture, and Acceptance Criteria.
- [x] No contradictions — non-goals in Architecture align with Ambiguity Log deferrals; auto-merge policy in AC-18 aligns with Intent statement.
- [x] Every gap/ambiguity finding is logged — three human-resolved items, seven inference-classified items, each with explicit rationale.
