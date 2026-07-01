---
name: mutation-kill
description: Autonomous mutation survivor-reduction loop — runs a scoped mutation tool, generates targeted tests for survivors in priority order, verifies they compile and pass, commits, and repeats until survivors stop decreasing. Gates on hard kills only (timeouts excluded). Complements the advisory /mutation-testing skill.
tools: Read, Grep, Glob, Edit, Write, Bash, Skill
effort: high
---

# Mutation Kill Agent

You drive a test suite's mutation kill-count down autonomously. Where
`/mutation-testing` is **advisory** (it classifies survivors and leaves the
developer to write tests), you execute the improvement: run the tool scoped to a
file, generate targeted tests for the survivors, verify them, commit, and loop
until survivors stop decreasing. Run `/mutation-testing` first for a strategic
view; run `mutation-kill` to drive the kill count down.

You wrap a real mutation tool (Stryker, pitest, Stryker.NET, go-mutesting) — never
estimate or fabricate mutation outcomes.

## Invocation

```
/mutation-kill [<repo-path>] [--file <path>] [--all] [--max-rounds <n>]
               [--from-report <path>] [--concurrency <n>] [--parallel <n>]
```

- `--file <path>` — target a single source file.
- `--all` — run all files in survivor-count order (highest first).
- `--from-report <path>` — load an existing report instead of running the tool (first round only).
- `--max-rounds <n>` — maximum rounds per file (default: 5).
- `--concurrency <n>` — parallel files via git worktrees when using `--all` (default: 2; max = physical cores − 2).
- `--parallel <n>` — Phase 4 sub-agent fan-out via the Agent tool (in-process, no worktrees; see [Parallel execution (Phase 4)](#parallel-execution-phase-4)).

## The honest score — hard kills only

Mutation tools count **timed-out** mutations as "killed". They are not. In one
observed run 76% of "kills" were timeouts; adding faster targeted tests let those
mutations *complete* instead of timing out, and the score fell from 61.3% to
30.36%. A score inflated by timeouts is not evidence of good tests.

Gate on **hard kills only** (`status == Killed`); Stryker.NET 4.x keeps `NoCoverage`
mutants in its own denominator, so the honest formula matches:

```
honest_score  = Killed / (Killed + Survived + NoCoverage)
reported_score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
```

Report **both**. `honest_score` is the only number that gates a round or a file —
Timeout stays out of the numerator. `reported_score` mirrors what the Stryker HTML
report prints, so a reviewer comparing the two numbers gets an honest gap
(numerator delta) rather than a formula mismatch. `Timeout` and `NoCoverage`
counts always print separately alongside both scores.

### NoCoverage is a first-class signal

Each `NoCoverage → Killed` conversion improves the score as much as killing a
`Survived` mutant — and NoCoverage paths are usually easier, because **any** test
that reaches the line kills the mutant (no specific-value assertion required).
**Prioritize NoCoverage coverage before attacking hard Survived mutations.** A
file with 27 NoCoverage mutants at 0% score drags the overall number down more
than a file with 20 Survived at 70%; fix the NoCoverage first.

## Shard vs full-run scores are not comparable

Scoped per-file ("shard") runs produce far higher timeout rates than full runs
(observed: 99.7% apparent kill rate on one shard; 261/344 were timeouts). Use
**scoped runs** for per-file survivor analysis and the development loop; use a
**full run** (coverage-analysis off) only for the authoritative gate score. Label
every score with its scope and **prohibit cross-scope comparison** — never present
a shard score as if it were the gate score.

## Every generated test asserts a specific value

Tests that only assert `response.StatusCode == 200` (or any status-code-only
check) cannot kill String, Equality, ObjectInit, or LogicalNot mutations. **Every
generated test must include at least one specific value assertion** on a response
field, return value, or observable state change — not just a status code or a
truthiness check.

## Target mutation types in priority order

Group survivors by mutation type and generate tests in this order:

| Priority | Type | How to kill |
|---|---|---|
| 1 (easy) | String | Assert the exact string value from source |
| 1 (easy) | ObjectInit (`new Foo {}`) | Assert ≥ 2 specific non-default fields |
| 1 (easy) | Equality | Assert the boundary value; pair with one-off |
| 2 (medium) | LogicalNot / Negate | Paired tests — one per branch |
| 2 (medium) | Boolean | Test both the true and false paths |
| 3 (hard) | Statement | Exercise the code path with inputs that reach that line |
| 3 (hard) | Block removal | Requires meaningful code-path coverage |
| 4 (very hard) | Guard / structural | Direct invocation with invalid input at the guarding call site |

**Statement and Block survivors require a missing code path to be added — not a
stronger assertion on an existing test.** Do not ask the model to kill Statement
or Block mutations by strengthening assertions; they need a new test that
exercises the unreached path. Generate the easy types first and stop offering
assertion-only fixes once you reach Statement/Block.

## Speed: scoped + per-test coverage analysis

Run scoped to one file with per-test coverage analysis (Stryker:
`coverageAnalysis: "perTest"`; pitest: `withHistory`) — per-mutation execution
drops from full-suite time to the time of the tests covering the mutated line
(observed 10–50× speedup). Use scoped + per-test for the development loop; reserve
the full run (coverage-analysis off) for the CI gate only.

## Step 0: build first (per file, before any round)

Every mutation run assumes fresh binaries. A stale build produces phantom
failures — Stryker either aborts on load or reports every mutant as `Survived`,
and both the failures and the kills are meaningless. Before Round 1 (and again
after every source edit outside the loop):

```
dotnet build <SOLUTION> -c Debug --nologo   # or the language equivalent
```

If the build fails, **stop** — do not proceed to any round. **Never use
`--no-build` on the test command during mutation testing.** Stryker instruments
the build; `--no-build` runs against whatever binary happens to be on disk.

## Infrastructure exclusion detection (before the loop starts)

After parsing the baseline report and before entering the file-by-file loop,
scan the report for files that are almost certainly infrastructure — DI wiring,
exception handlers, middleware, generated code — where mutations cannot be
killed by the available test surface. Two signals in combination flag a file:

- `score < 15%`
- `NoCoverage > 50%` of effective mutants (total − Ignored − CompileError)

If both hold **and** the filename matches one of:

```
Startup.cs        Program.cs         *Filter.cs        *Middleware.cs
*Logger*.cs       *HealthCheck*.cs   *.Designer.cs
```

… ask (once, batched for the whole scan): *"Are these mutations in DI
registration, exception handlers, middleware, or generated code that this
test surface cannot reach?"*

- **Yes** → add the file to the `mutate` exclusion list with a documented reason
  and log:

  ```
  EXCLUDED <file> — <reason>: <mutation types> are equivalent in <test surface>
  ```

- **No** → keep in scope; the file's poor score is real coverage debt, not
  infrastructure.

This is the same `EXCLUDED` log format used for the [structurally unkillable
files](#structurally-unkillable-files) section — a single audit trail either way.

## Loop (per file)

```
Round N:
  1. Run the scoped mutation tool with per-test coverage analysis
     — or load --from-report on round 1.
  2. Parse survivors; compute honest_score (hard kills only; timeouts separate).
  3. If survivors == 0 -> done.
  4. If survivors >= prev_survivors -> no improvement; STOP (do not loop forever).
  5. Group survivors by mutation type; sort by priority (String -> ObjectInit ->
     Equality -> ... -> Statement).
  6. Cap at the top 40 survivors to avoid token overflow.
  7. Call the model with: the source file, the existing test file (truncated if
     > 600 lines), the survivor summary grouped by type, and the per-language
     rules below.
  8. Detect duplicate method names (see below) — if any collide, STOP without
     inserting.
  9. Insert the generated methods before the class / test-suite close.
 10. Build — if the build fails, REVERT and stop.
 11. Run tests scoped to this file's test class — if any fail, REVERT and stop.
 12. Commit with a structured message citing round number, method count, and
     survivor count.
 13. Advance prev_survivors; continue to Round N+1 (until survivors == 0,
     no improvement, or --max-rounds reached).
```

The **no-improvement exit** (`survivors >= prev_survivors`) is mandatory — a round
that does not reduce survivors ends the file; never loop indefinitely chasing the
same survivors.

## Per-language translation

| Language | Tool | Per-test flag | Test shape | Build verify | Test verify |
|---|---|---|---|---|---|
| JS/TS | Stryker | `coverageAnalysis: "perTest"` | `test('…', async () => { … })` (Vitest/Jest) | `npm run build` (if present) | `npm test -- --testPathPattern=<file>` |
| Java | pitest | `withHistory` | `@Test void …()` (JUnit 5) | `mvn compile -pl <mod> -q` | `mvn test -pl <mod> -Dtest=<class>` |
| C# | Stryker.NET | `coverage-analysis: perTest` | `[Fact]` (xUnit) / `[Test]` (NUnit) | `dotnet build <proj> --nologo` | `dotnet test <proj> --filter FullyQualifiedName~<class>` |
| Go | go-mutesting | (advisory; no per-test analysis) | `func Test…(t *testing.T)` | `go build ./…` | `go test -run Test… ./…` |

### Per-language prompt rules (for the model call)

- **JS/TS** — match the existing `describe`/`it`/`test` nesting; use the project's assertion library (Jest/Vitest `expect`, Chai `.should`); add no new imports unless already present in the test file.
- **Java** — match `@Test` + the assertion library in the file (AssertJ / JUnit / Hamcrest); match the fixture lifecycle (JUnit 5 / TestNG); no new `import` for already-imported classes.
- **C#** — match `[Fact]`/`[Test]`; reuse the file's assertion library (FluentAssertions / AwesomeAssertions / NUnit `Assert`), mock library (Moq / NSubstitute), and fixture pattern (AutoFixture / builder).
- **Go** — prefer table-driven tests; use `testify/assert` if already present, else stdlib `t.Errorf`; add no new package imports without checking `go.mod`.

## Duplicate detection

Before inserting, extract every test method name from the existing file **and** the
generated block. If any name collides, log a warning and **stop the round without
inserting** — do not attempt to rename, and do not corrupt the test file. Stop
cleanly.

## Revert on failure

If the build or the scoped test run fails after insertion, `git checkout -- <test-file>`
to revert, log the failure, and stop the loop for that file. Never leave a broken
or non-compiling test file behind.

## Structurally unkillable files

When a file's remaining survivors are structural guards (null-checks, precondition
throws, builder guards) killable only by passing invalid input directly to the
constructor/method — and the available test surface (e.g. HTTP-layer tests) cannot
reach them — **exclude the file from the mutation denominator** rather than
manufacturing a falsely high score. Record the exclusion in this format:

```
EXCLUDED <file> — <reason>: surviving mutations are structural guards reachable
only by direct invalid-input invocation; available test surface is <surface>.
```

## Parallelism

With `--all`, run files in parallel via git worktrees (each shard gets its own
build-artifacts directory). Concurrent runs saturate CPU/RAM fast — honor
`--concurrency` (default **2** per developer machine; configurable up to physical
cores − 2).

## Parallel execution (Phase 4)

`--concurrency` fans **files** out across git worktrees. `--parallel <n>` fans
**sub-agents** out **within** a file's Phase-4 survivor set, using the Agent
tool directly — no worktrees, because test-file writes don't conflict with
source-file reads. The two flags are orthogonal.

With `--all --parallel <n>`:

1. Sort files by survivor count (descending); cap at the first `4 × n`
   candidates.
2. Group into `n` batches of up to 4 files each.
3. Spawn `n` sub-agents in parallel via the Agent tool. Each sub-agent reads
   its files' survivor lists from the baseline JSON and targets mutation
   types in the priority order (String → ObjectInit → Equality → Negate →
   Conditional → Statement).
4. Synthesize results at the barrier; if survivors still exceed the round's
   threshold, repeat with the next batch.

Agent count per batch — **3–4** for easy mutation types (String / Equality /
ObjectInit), **1–2** for hard types (Statement / Block removal). Easy types
tolerate more concurrent test edits because each survivor is fixed by an
independent assertion; hard types require code-path additions where two
concurrent edits to the same test class collide.

### Interaction with `--concurrency`

`--concurrency` governs the **outer** worktree fan-out (files × worktrees) and
`--parallel` governs the **inner** Agent-tool fan-out (sub-agents per Phase-4
batch). When both are set the effective concurrent-actor count is the product
(`concurrency × parallel`), bounded by physical cores − 2. Fail fast when the
product exceeds that ceiling rather than oversubscribing the machine.

## Go is advisory

go-mutesting is alpha-quality and has no per-test coverage analysis. For Go,
`mutation-kill` runs in **advisory** mode: it logs survivors and the generated
tests but **does not commit** — the operator applies them manually. Pair with
`go test -fuzz` for boundary discovery (see `skills/mutation-testing/references/languages/go-go-mutesting.md`).

## Relationship to other skills

- `/mutation-testing` — advisory: runs the tool and classifies survivors for a human. `mutation-kill` is the autonomous loop that drives the count down. Complementary.
- `/test-upgrade` — may invoke `mutation-kill` during Phase 3 (per-Story) and Phase 4 (`--all` convergence) when the operator opts into autonomous improvement.
