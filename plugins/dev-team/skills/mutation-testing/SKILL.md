---
name: mutation-testing
description: Validate test suite quality by running a real mutation testing tool and triaging surviving mutants. Use after writing tests to verify assertions catch behavioral changes, when evaluating test coverage quality, or as a CI quality gate on critical modules. The AI value here is triage — classifying survivors, writing fix tests — not generating or estimating mutations.
role: worker
user-invocable: true
---

# Mutation Testing

Role: worker. This command runs the mutation tool and triages survivors
directly — it does not generate or estimate mutations, and it does not
replace the tests it validates.

Wraps a real mutation tool (Stryker, pitest, mutmut, Stryker.NET, go-mutesting) and adds AI triage of survivors. The tool generates mutations and reports survivors; the AI classifies survivors and writes fix tests. **Never estimate or guess mutation outcomes** — if no tool is available, help set one up; do not substitute reasoning for execution.

This file describes the language-agnostic workflow and the data contract. **Per-language detail — install, run commands, timeout flag names, native-report mapping — lives in [`references/languages/`](references/languages/).** Detect the language first via [`references/tool-detection.md`](references/tool-detection.md), then load the matching language file.

**Unattended, LLM-free overnight measurement.** [`scripts/mutation_nightwatch.py`](scripts/mutation_nightwatch.py) (detection/repair/measurement mechanics split into [`scripts/mutation_nightwatch_stacks.py`](scripts/mutation_nightwatch_stacks.py)) is a third, report-only mode alongside `mutation-kill`'s interactive and `--headless` fixing modes — no generation, no LLM, no commits, so it can run overnight unattended. See the companion [`mutation-night-watch`](../mutation-night-watch/SKILL.md) skill for launch/detach/schedule guidance.

**Committed, human-approved exclude-policy bootstrap.** When no `mutation-exclude-policy.json` exists at the repo root yet, a night-watch run drafts one via [`scripts/mutation_exclude_policy.py`](scripts/mutation_exclude_policy.py) — the same two-signal judgment (score < 15%, NoCoverage > 50%, filename hint promotes to a stronger tier) `mutation-kill`'s own [Infrastructure exclusion detection](../../agents/mutation-kill.md#infrastructure-exclusion-detection-before-the-loop-starts) applies, but persisted as a source-controlled file instead of a build-output-only convergence log. The night-watch run only ever drafts a proposal alongside its other reports; `mutation_exclude_policy.py --approve` is the only code path that writes the committed file, and it is never called unattended.

## Constraints

- **Always ask the user before running.** Present the time estimate and scope; get explicit approval. Mutation testing can be slow — never surprise the user.
- Only run after tests exist; mutation testing validates tests, it does not replace them.
- Do not chase 100% mutation score; equivalent mutants are noise.
- Scope to changed files by default; full-codebase runs are periodic audits.
- Surviving mutants in critical paths require action; in trivial code they may be acceptable.
- **Per-mutant wall-clock timeout.** Every mutant run is capped at a wall-clock timeout. A run that exceeds the timeout counts as a **killed** mutant (matching the experiment-harness fix). Default: `timeout_seconds = max(60, suite_time_seconds × 10)`. Never run without a timeout — an infinite-loop mutant will hang the harness indefinitely. Per-tool flag names live in each [`references/languages/<lang>.md`](references/languages/).
- **`--workflow-managed-approval` carve-out.** When this flag is set, the `Step 0` confirmation prompt is skipped — but the "always ask the user before running" invariant still holds at a higher boundary. The flag is reserved for orchestrated workflows that capture operator approval once for the whole run, then propagate the consent down to each scoped invocation. The authoritative caller registry is [`references/workflow-callers.md`](references/workflow-callers.md). Today's allowed callers are `/coverage-delta` (Phase 4 of `/test-improve`), `/quality-targets-converge` (Phase 6 of `/test-improve`), and `/test-improve` itself (Phase 2 baseline). Each inherits its workflow-level approval from `/test-improve` Phase 0. Any new caller must document where its workflow-level approval is captured before adopting the flag — see the registry file for the full process.

## Parse Arguments

The skill accepts free-form natural-language arguments AND the following named flags for workflow callers:

- `--scope <files-or-globs>` — restrict the mutation run to the listed files or shell globs. Comma-separated lists and quoted globs both accepted. When omitted, the skill scopes to changed files by default.
- `--emit-json <path>` — write the structured result to `<path>` (see `## Machine-readable output` below) in addition to any human-readable output. The path's parent directory must be writable; failure writes to stderr and exits non-zero.
- `--workflow-managed-approval` — skip the `Step 0` confirmation gate because the calling workflow captured approval at a higher boundary. Restricted to the allowlist in `## Constraints`.

## Time estimation

See [`references/time-estimation.md`](references/time-estimation.md) for the formula, heuristic table, and how to estimate for a specific project. Present the estimate to the user; if > 5 minutes, suggest scoping down.

## Step 0: Confirmation gate

Before any mutation run, present the estimated time and the scope, then block on stdin for explicit approval. The prompt is observable: stdout contains the literal string `Estimated time:` followed by the scope summary. This gate is **skipped when `--workflow-managed-approval` is set** — see the carve-out in `## Constraints`.

## Step 1: Detect or set up tooling

**Prefer a local install** over a global one. Global installs depend on the user's `PATH` and produce silent "command not found" failures when it is not configured (see [`references/languages/csharp-stryker-net.md`](references/languages/csharp-stryker-net.md) for the observed Stryker.NET case). Each [`references/languages/<lang>.md`](references/languages/) file below shows the **local**-install command as the primary path.

Use [`references/tool-detection.md`](references/tool-detection.md) to resolve the project's ecosystem to a mutation tool, then load the matching `references/languages/<lang>.md` for install and run commands. **Do not proceed without a working tool.**

**Go is advisory-only.** When the project has a `go.mod`, resolve to **go-mutesting** in advisory mode (it is alpha quality — the surviving-mutant count is not a reliable gate). Advisory mode emits the `schema_version: 1` envelope with `"advisory": true`; orchestrated workflows treat that as **warn, do not block** — a non-zero survivor count never fails the gate. Always pair it with Go's built-in fuzzing (`go test -fuzz=FuzzXxx -fuzztime=30s ./path/to/pkg`), which is production-quality, for boundary and edge-case discovery. Full install path and fuzz idioms: [`references/languages/go-go-mutesting.md`](references/languages/go-go-mutesting.md). Never tell a Go project "no tool installed" without giving both the go-mutesting install path and the fuzz alternative.

## Step 1b: Configure per-mutant timeout

Set a per-mutant wall-clock timeout before running. A timed-out mutant is **killed** (counts toward the mutation score as a non-survivor). This matches the experiment-harness fix in `docs/experiments/`.

Derive the timeout:

```
suite_time_seconds = time the baseline test suite (from Step 1 output, or measure: `time <test-command>`)
timeout_seconds    = max(60, suite_time_seconds × 10)
```

For tool-specific flag names and config-file keys (e.g. Stryker's `timeoutMS`, pitest's `--timeoutConst`), see the matching [`references/languages/<lang>.md`](references/languages/). Document the chosen timeout in the output summary.

## Step 1c: Smoke gate — verify the tool is actually observing mutations

Before running the full scan, run the tool against **one covered file** and confirm the mutation-switch mechanism is actually observing mutations at runtime. On some tool + test-framework combinations (issue [#554](https://github.com/bdfinst/agentic-dev-team/issues/554), [#557](https://github.com/bdfinst/agentic-dev-team/issues/557) on Stryker.NET + xunit.v3 + MTP), the tool cheerfully runs to completion but reports **every mutant as `Survived`** because the injected `ActiveMutation` env var never reaches the test host — the score looks like `0.00 %` but the run wasted hours. This gate catches that failure mode in one file's worth of wall-clock time.

**Deterministic parse source.** Parse the tool's **report JSON** (Stryker's `StrykerOutput/<run>/reports/mutation-report.json`, pitest's `target/pit-reports/mutations.xml`, mutmut's `mutmut junitxml` output, etc.). **Do not parse stdout, the ANSI progress reporter output, or any log tail** — those are lossy, reporter-config-dependent, and don't survive redirection (see `## Capturing run output safely`). The gate is deterministic only when it reads the same artifact downstream steps read.

**Three-way decision** (from the parsed counts):

1. **`Killed > 0`** — the mutation-switch mechanism is working. **Proceed** to Step 2's full run.
2. **`Killed == 0 && Survived > 0`** — the tool ran the test suite for every mutant and killed **none of them**. This is the mutation-switch-not-observing-mutations failure mode. **Halt** with an error message that:
   - names the failure mode (mutation-switch not observing mutations at runtime),
   - references issues #554 and #557 for the observed Stryker.NET / xunit.v3 / MTP case,
   - and enumerates the diagnostic checklist below.
3. **`Killed == 0 && Survived == 0`** (no-signal probe — all mutants `NoCoverage`, `CompileError`, or none generated) — the probe file provides no configuration signal. **Halt** and instruct the operator to pick a different probe file with real test coverage; a probe with no scored mutants can't distinguish "tool is broken" from "tool works but this file has no tests."

**Diagnostic checklist** (for the mutation-switch failure mode — walk this before touching any config):

- [ ] **Manual mutation kills the test?** Edit one covered line of the probe file, rebuild, run the specific test that covers it — does that test fail? If yes, the tests can observe changes but the tool's mutation-switch isn't activating them at runtime.
- [ ] **`SolutionPath` in the config?** Multi-project configs that set both `SolutionPath` and an explicit test-projects list may see the tool enumerate additional test projects from the solution and prefer them over the ones listed. Verify the tool is actually running the test project you configured (`--diag` output on Stryker.NET; equivalent flag on other tools). See `references/languages/csharp-stryker-net.md` § SolutionPath trap.
- [ ] **Unintended test-project enumeration?** Confirm no other test project in the solution is being picked up ahead of yours. If the tool is running the wrong test project, the smoke gate will fail even though the tool and configured tests are both fine in isolation.
- [ ] **Is the target on .NET 10 with the default `vstest` runner?** Stryker.NET's bundled `vstest` runner can silently fail coverage capture on .NET 10 test assemblies, producing this exact `Killed==0 && Survived>0` shape. Retry with `-t mtp` — see `references/languages/csharp-stryker-net.md` § .NET 10 targets: default `vstest` runner can silently fake a 0% score.

Per-language commands (which probe file to pick, how to invoke the tool with a single-file mutate glob, and where the report JSON lands) live in each [`references/languages/<lang>.md`](references/languages/). This step's decision procedure is language-agnostic; the mechanics are language-specific.

**Mechanical enforcement (Claude Code sessions).** Inside a Claude Code session, the `PreToolUse` hook [`hooks/mutation_testing_smoke_gate.py`](../../hooks/mutation_testing_smoke_gate.py) enforces this step automatically — it intercepts `dotnet stryker` and shipped-wrapper invocations, checks for a smoke report at the fixed convention path `StrykerOutput/smoke/reports/mutation-report.json`, and blocks whole-scope runs until a probe report reports at least one `Killed` mutant. Run your smoke probe with `-O StrykerOutput/smoke` so the report lands where the hook looks; a single-file `--mutate` value (no glob metacharacters, no `;`) is recognized as the probe itself and never blocked. To bypass the gate for a legitimate one-off, set `MUTATION_SMOKE_GATE_SKIP=1` in the environment — every bypass appends one JSONL audit line to `.claude/metrics/gate-bypass.jsonl` recording the timestamp, cwd, and a sha256 hash of the command (the raw command is never logged). Direct-terminal and CI operators — outside Claude Code — rely on this step's prose plus the shipped wrapper's own defenses; the hook is Claude-Code-only.

## Step 2: Run the tool (scoped to target)

Run scoped to user-specified files or changed files. Capture full output and note any HTML report paths. Per-language commands and scoping idioms — including the C# shard-aware execution path for large repos — live in [`references/languages/<lang>.md`](references/languages/).

### Capturing run output safely

Do **not** wrap the mutation tool in a bare `<tool> 2>&1 | tee run.log` pipeline. Bash pipeline exit status defaults to the last command's — `tee` always exits 0 on a successful write — so any Stryker / mutmut / pitest / go-mutesting startup failure (missing tool manifest, invalid config key, wrong `DOTNET_ROOT`, compile-error abort) is silently masked. Downstream automation (background tasks, CI wrappers, this plugin's own monitor loops) then sees "success" and moves on, and the failure is discovered only when the report JSON is missing.

Two safe patterns — pick by whether you need live tail:

```bash
# One-shot run — direct redirect, simpler, no shell-option side effect.
dotnet stryker --config-file stryker-config.json >StrykerOutput/full-run.log 2>&1

# Live-tail run — pipefail makes the pipeline exit the leftmost non-zero.
set -o pipefail
dotnet stryker --config-file stryker-config.json 2>&1 | tee StrykerOutput/full-run.log
```

This trap is portable across all languages the skill supports; the same rule applies to `npx stryker run ... | tee`, `mutmut run ... | tee`, `mvn pitest:mutationCoverage ... | tee`, and `go-mutesting ... | tee`. If you rely on `$?` or a monitor's exit-code trigger, always use one of the two safe patterns above.

### Probe file selection

Before scoping the full run, pick a **probe file** — one file to shake out configuration and get a first honest signal. A good probe exercises both fast kills and the timeout ceiling, so the run tells you whether the tool is configured correctly. A bad probe produces a mass-CompileError smoke plume that validates nothing.

Rules (language-agnostic):

- **≥ 50 mutants** — enough operator variety that the score is not a coin flip.
- **Highest existing mutation score in the target** — a file already well-tested by unit tests exercises both the "kill fast" and "timeout near the limit" paths; a weakly-tested file only measures how weakly it is tested.

Avoid, in every language:

- **Generated code** (Protobuf, OpenAPI stubs, ORM entity generators) — the mutation tool cannot distinguish generator output from hand-written code, and mutations on generated types typically fail to compile.
- **DTOs / value objects** — no branching logic; every survivor is either equivalent or a wrapper-property assertion, so the file gives no signal about test quality.
- **Files with near-0 % coverage** — validates configuration only, not test quality. Every mutant survives regardless of how the tests are written.

Language-specific probe traps (particularly in C#/Stryker.NET, where certain operator combinations produce methods that don't exist) live in [`references/languages/<lang>.md`](references/languages/).

## Long-run inspection

Real mutation runs take 15 min – several hours. During that window the tool emits progress on the terminal via an ANSI in-place reporter that **does not survive log redirection**, so a redirected run looks frozen even when the tool is fine. A silent-hang and a silent-config-error look identical to a healthy run until the summary lands. That's a several-hour feedback loop when the failure could have been caught in one. Every long run needs a periodic inspection loop watching **three signals**:

1. **Progress** — mutants tested / total. Read from a source that survives redirection: the tool's report JSON while in progress, a non-ANSI reporter's output (Stryker's `dots` reporter is the survives-redirection choice), or counts scraped from the log. Do NOT depend on the ANSI progress reporter.
2. **Health** — is the tool process still alive? Are child test-host processes alive? Elapsed wall-clock time. Silent + live = fine. Silent + dead = an unreported crash.
3. **Error inspection** — grep the log for known-broken signatures each tick, not just at the end. Failure modes to catch at tick boundary:
   - `Killed: 0` co-occurring with `Survived: > 0` — the mutation-switch-not-observing-mutations failure Step 1c gates against; if it slips past Step 1c (e.g. new file added mid-run), catch it here.
   - `CompileError` count spike — probe file, `mutate` glob, or generator-code inclusion misconfigured.
   - Tool-specific config-trap markers (Stryker.NET's `SolutionPath` naming a `.sln` outside the configured `test-projects` list, for example).
   - Frequency spikes in `Restarting` / `test process crashed` / `Timeout`.

**Default cadence: 10 minutes** (600 s). Short enough to catch a stall or config error within one cycle, long enough not to spam operator output. Runs shorter than ~15 min don't need this — the summary at the end is sufficient. Cadence should be configurable.

**This is a contract, not a mandated implementation.** Two examples the plugin ships:

- **Portable Python wrapper** — a Python script that runs the tool as a subprocess, polls the log file, and emits one status + zero-or-more `[RED-FLAG]` lines per tick. Cross-platform via Python 3.10+ stdlib; works outside Claude Code (CI, direct terminal). The Stryker.NET reference in [`references/languages/csharp-stryker-net.md`](references/languages/csharp-stryker-net.md) documents the shipped wrapper (`csharp_stryker_net_wrapper.py`) + status loop (`csharp_stryker_net_status_loop.py`).
- **In-session Monitor** — inside a Claude Code session, a `Monitor` tool call on the log file stream that emits an event on each recognized red-flag pattern. Cleaner integration but no coverage for out-of-session (CI, direct-terminal) operators.

Whichever you pick, never implement the cadence as a foreground `sleep` loop. If the tick is driven by a scheduled wake-up rather than a stream monitor, see [`knowledge/long-run-waiting.md`](../../knowledge/long-run-waiting.md) for the calling contract — a wake-up armed without its replay instruction fails validation and schedules nothing, so the "inspection loop" stops inspecting after tick one.

Per-language references may add tool-specific red-flag signatures — the language file lists them alongside the parse patterns.

## Step 3: Parse results

Extract surviving mutants. Map each to:

| Field | Source |
| --- | --- |
| File + line | Tool report |
| Mutation operator | Tool report (`ConditionalBoundary`, `NegateConditional`, etc.) |
| Original code | Read the source at that line |
| Mutated code | Tool report or infer from operator |
| Mutation score | Tool summary |

## Step 4: Triage survivors

For each mutant, classify and act. **`NoCoverage` outranks `Survived`** — a survived mutant at least ran, so a tighter assertion can kill it; a no-coverage mutant was never reached at all, so writing a test that exercises the path is the higher-leverage move.

| Classification | Meaning | Action |
| --- | --- | --- |
| **NoCoverage** | No test exercises this code path at all | Add a test that reaches the path before worrying about killing the mutant — coverage is the prerequisite |
| **Equivalent** | Mutation produces identical behavior — no test could ever kill it | Mark `status: "equivalent"` with a `reason` string — excluded from the mutation denominator |
| **Missing assertion** | Test executes the code but doesn't assert on affected output | Strengthen the assertion |
| **Missing test case** | No test exercises the mutated path | Write a new test |
| **Undertested boundary** | Mutation exposes a boundary/edge with no coverage | Add a boundary test |
| **Accepted this pass** | A real, killable mutant intentionally deferred — not equivalent, just out of scope for now | Document and skip: mark `status: "accepted"` with a `reason` string per mutant (or tightly-scoped mutant group) — never a file-level wave-off |

Equivalent and Accepted are not the same classification, even though both end in "document and skip." **Equivalent** means no test — now or ever — can distinguish the mutation from the original; it is permanently out of the honest denominator. **Accepted** means the mutant is genuinely killable and a future pass could kill it, but this pass deliberately chose not to chase it (out of scope, low signal, pre-existing debt); it counts against the raw score but not the adjusted score (see [Machine-readable output](#machine-readable-output)). Never mark a killable mutant `"equivalent"` to make the raw score look better — that is what `"accepted"` is for, and it carries its own visible accounting.

**Recommended work order** — attack in this sequence, not by file order:

1. **NoCoverage** first (each conversion moves the honest score as much as killing a survivor, and it's usually cheaper — the unreached path just needs a test that touches it).
2. **Survived** next (assertion or coverage fix — see the mutation-type-aware guidance below).
3. **Equivalent** and **Accepted this pass** last (documentation only; no test to write — each still requires its own `reason` string).

**Cluster survivors by source line before filling in "Recommended Test Additions."** When several survivors land on the same or adjacent source line sharing one expression, group them into one cluster — sorted by survivors-per-line descending (not total mutants-per-line; the ranking targets what still needs killing) — and design one test per cluster where feasible, rather than one per mutant: the same line-clustering approach [`mutation-kill.md`'s generation guidance](../../agents/mutation-kill.md#target-mutation-types-in-priority-order) applies for autonomous test generation, here guiding a human filling the triage table.

### Mutation-type-aware triage

Different mutation types fail for different reasons. A single strategy does not fit all — asking an LLM to strengthen an assertion cannot kill a Statement-removal survivor. Match the fix to the family:

**String / ObjectInitializer / Equality** — the easiest family to kill and the highest kills-per-test. The test executes the code but does not assert on the mutated value (a status-code check will not catch a wrong string). Fix: add a **specific-value assertion** on the affected field. Example (C#):

```csharp
// WEAK — status only
response.EnsureSuccessStatusCode();
// STRONG — assert on the specific field the mutation would change
Assert.AreEqual("expected-value", response.Data.FieldName);
```

**Statement / Block removal** — survives because the code path is not exercised, not because an assertion is weak. **A stronger assertion cannot kill this family.** Fix: add a test that reaches the missing path. Do not ask an LLM to kill a Statement mutation with a stronger assertion — it will produce a plausible-looking test that still doesn't cover the deleted line.

**Guard (null-check / range-check / required-field removal)** — on internal service or builder methods, cannot be killed by HTTP-layer / integration tests: the outer request path validates before reaching the guard. Fix: a **unit test that invokes the guarded method directly** with invalid input, asserting the exception (or the observable side effect the guard prevents). Identify guard survivors by looking for `Statement` survivors in service/builder classes and asking "is this guarding an internal invariant?" — if yes, the fix is a direct call, not a request-level test.

### Triage procedure

1. **Read the source context** — what does the code do and why.
2. **Check for equivalence** — does the mutation actually change observable behavior? Common equivalent patterns: dead code or unreachable branches; commutative-operation reorderings; conditions redundant with other guards; logging/debug-only code.
3. **Find related tests** — which tests cover this code; what do they assert.
4. **Classify** — missing assertion, missing test, boundary gap, equivalent, or accepted (real, killable, deliberately deferred this pass — record the `reason`).
5. **Write the fix test** with RED-GREEN discipline: must fail against the mutant and pass against the original.

**Graph-assisted triage.** For steps 1 and 3, prefer CodeGraph/Repowise over raw `Grep` — they surface a mutated line's callers and its covering tests directly, which is faster and more complete than grepping for the symbol name. See [`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md) for tool selection and the fallback contract.

### Weak vs strong test patterns

Most survivors come from tests that execute code without meaningfully asserting on behavior. Patterns are language-agnostic — JavaScript is shown for illustration; translate the idiom into your language's test framework.

**Arithmetic operators** — beware identity values (`0` for `+/-`, `1` for `*//`, `""` for concat):

```js
// WEAK: 0 is identity for addition — a + 0 === a - 0
expect(calculate(5, 0)).toBe(5);  // passes with + or -

// STRONG: non-identity values distinguish operators
expect(calculate(5, 3)).toBe(8);  // fails if + becomes -
```

**Conditional boundaries** — test both sides:

```js
expect(isAdult(18)).toBe(true);   // exactly at boundary
expect(isAdult(17)).toBe(false);  // one below
```

**Return values** — assert on the actual return, not truthiness:

```js
// WEAK: passes if return value changes from obj to true
expect(getUser(1)).toBeTruthy();
// STRONG: assert on shape
expect(getUser(1)).toEqual({ id: 1, name: "Alice" });
```

**Statement deletion** — verify side effects:

```js
processOrder(order);
expect(db.save).toHaveBeenCalledWith(order);  // catches removed save()
```

## Step 5: Fix and verify

1. **Verify the fix test fails against the mutant** — if possible, manually apply the mutation and run the test, or use the tool's re-run-specific-mutant feature.
2. **Re-run the mutation tool** on the same scope to confirm the mutant is killed.
3. **Report the updated mutation score.**

## Output format

Report the **honest** figure as the operator's primary signal. Tool-claimed scoring counts timeouts as kills and inflates — on a real Stryker.NET run, 999 of 1305 headline "kills" were timeouts (~23 % honest vs. ~61 % as Stryker reported it). Show both, honest above claimed, and emit the timeout warning when it fires. Formulas and rationale are canonical in `${CLAUDE_PLUGIN_ROOT}/knowledge/mutation-score-formulas.md` (shared with the `mutation-kill` agent); derivation for the machine-readable field names is in the [Machine-readable output](#machine-readable-output) section below.

The illustrative counts below are self-consistent under those formulas (verify: `100 / (100+200+135) = 23.0 %`; `(100+430) / (100+200+430+135) = 61.3 %`; `430 / (100+200+430) = 58.9 %`). Do not tune wording without re-checking the arithmetic.

When Step 4 marks one or more survivors `status: "accepted"` (a real, killable mutant intentionally deferred this pass — distinct from `"equivalent"`), also print the **raw/adjusted** pair per the knowledge file above, so a documented deferral never reads as unaddressed test-quality debt. Verify: `24 / (24+11+0) = 68.57 %`; `24 / (24+(11-11)+0) = 100 %`.

```markdown
## Mutation Testing Results

**Tool:** Stryker 8.x | **Scope:** src/calculator.ts | **Duration:** 45s | **Per-mutant timeout:** 60s
**Honest score:** 23.0% (100 killed of 435 candidates; candidates = killed + survived + no-coverage)
**Claimed score:** 61.3% ((killed + timeout) / (killed + survived + timeout + no-coverage))

> ⚠️ **Timeout warning:** 58.9% of run outcomes were timeouts (430 of 730). The claimed score
> is not trustworthy — raise `additional-timeout` (per-tool flag; see the language reference)
> before treating either score as a gate.

**Raw:** 68.57% (24/35) · **Adjusted for 11 accepted survivors:** 100% (24/24)

### Surviving Mutants

| # | File:Line | Operator | Original | Mutated | Classification | Fix |
|---|---|---|---|---|---|---|
| 1 | calculator.ts:42 | ConditionalBoundary | `x > 0` | `x >= 0` | Missing boundary test | Add test: `expect(calc(0)).toBe(...)` |
| 2 | calculator.ts:67 | ReturnValue | `return result` | `return 0` | Missing assertion | Strengthen: assert on specific value |

### Equivalent Mutants (excluded)
| # | File:Line | Operator | Why equivalent |
|---|---|---|---|
| 1 | calculator.ts:15 | ArithmeticOperator | Dead code — branch unreachable |

### Accepted Survivors (deferred)
| # | File:Line | Operator | Reason |
|---|---|---|---|
| 1 | splash.component.ts:31 | StringLiteral | Field overwritten unconditionally in `ngOnInit` before any assertion could observe it; deferred this pass |

### Recommended Test Additions
(Specific test code for each non-equivalent, non-accepted survivor)
```

## Machine-readable output

When `--emit-json <path>` is set, write a structured result document to `<path>`. Workflow callers (`/coverage-delta`, `/quality-targets-converge`) read this document to compute deltas; downstream readers depend on the schema staying stable, so it is versioned.

**Success envelope (`schema_version: 1`):**

```json
{
  "schema_version": 1,
  "tool": "stryker",
  "scope": ["src/calculator.ts"],
  "captured_at": "2026-06-19T14:22:08Z",
  "total": 50,
  "killed": 41,
  "survived": 6,
  "equivalent": 3,
  "accepted": 0,
  "timeout": 0,
  "no_coverage": 0,
  "compile_error": 0,
  "honest_score": 87.2,
  "claimed_score": 87.2,
  "raw_score": 87.2,
  "adjusted_score": 87.2,
  "timeout_pct": 0.0,
  "timeout_warning": false,
  "survivors": [
    { "file": "src/calculator.ts", "line": 42, "operator": "ConditionalBoundary", "status": "survived" },
    { "file": "src/calculator.ts", "line": 67, "operator": "ReturnValue",        "status": "equivalent", "reason": "Dead branch; unreachable after upstream guard" },
    { "file": "src/calculator.ts", "line": 90, "operator": "StringLiteral",      "status": "accepted",   "reason": "Field overwritten unconditionally before any assertion could observe it; deferred this pass" }
  ]
}
```

Each entry in `survivors` carries `file`, `line`, `operator`, and `status` where `status` is `"survived"`, `"equivalent"`, or `"accepted"`. Every `"equivalent"` or `"accepted"` entry MUST carry a sibling `reason` string — a mutant cannot be excluded or deferred without a stated rationale; `"survived"` entries carry no `reason`. Callers MUST filter both `status: "equivalent"` AND `status: "accepted"` before computing deltas so reclassifications and documented deferrals between runs don't show up as regressions.

An optional top-level `"advisory": true` flag marks a result from an advisory-only tool (go-mutesting today). When present, callers MUST treat the survivor count as warn-not-block — it never fails a gate. Absent (the default), the result is authoritative.

**Formulas.** The score fields are derived; the raw counts are the source of truth.

```
honest_score   = Killed / (Killed + Survived + NoCoverage)
claimed_score  = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
timeout_pct    = Timeout / (Killed + Survived + Timeout)
timeout_warning = timeout_pct > 0.05
raw_score      = Killed / (Killed + Survived + NoCoverage)                     // == honest_score; relabeled for the raw/adjusted pair below
adjusted_score = Killed / (Killed + (Survived - Accepted) + NoCoverage)        // excludes accepted survivors from the denominator
```

The honest score matches the sibling `mutation-kill` agent's formula so both surfaces read the same number. It differs from Stryker's own "mutation score" line (Stryker counts `Timeout` toward the numerator). When `timeout_warning` is true, the claimed score is not trustworthy: raise the tool's `additional-timeout` (or equivalent per-tool wall-clock budget) before treating either score as a gate. The warning is advisory — not a hard gate that fails the run — so a caller can decide policy without the skill forcing one.

`raw_score` and `adjusted_score` are a **separate, orthogonal pair** from `honest_score`/`claimed_score` — the latter accounts for `Timeout` inflation, the former accounts for consciously-**accepted** survivors. `Accepted` is the count of `survivors[]` entries with `status: "accepted"`; it is always `<= Survived` (an accepted mutant is a subset of the survived population, not an addition to it). `adjusted_score` MUST NEVER replace `raw_score` in a report — both print, labeled, alongside the "Accepted Survivors (deferred)" table (see [Output format](#output-format)) so a documented deferral stays visible rather than quietly improving the denominator.

**Emitting adapters.** Adapters emit the additive score fields only when their native tool distinguishes `Timeout` and `NoCoverage` from `Killed`/`Survived`. Today that is Stryker (JS), **Stryker.NET**, and pitest. Advisory-only tools that do not distinguish them — today's examples are **go-mutesting** and **mutmut** (`mutation_report.py`/`mutation_kill_loop.py` have no mutmut-specific parsing yet; only the PostToolUse gate's per-file adapter, `hooks/mutation_adapters/mutmut.py`, is wired) — omit the fields entirely rather than emit misleading zeros; the top-level `"advisory": true` flag is the caller's signal to treat the envelope as warn-not-block. Readers that consume the new fields MUST tolerate them being absent on an advisory envelope.

**Error envelopes (exit code non-zero, `<path>` still written for caller diagnostics):**

```json
{ "schema_version": 1, "tool": null, "error": "no_tool_installed", "language": "javascript" }
{ "schema_version": 1, "tool": "stryker", "error": "empty_scope", "scope_glob": "src/does-not-exist/*.ts" }
```

When `<path>` itself is unwritable (read-only directory, permission denied), the skill writes nothing to disk, prints the offending path to stderr, and exits non-zero. No partial JSON is left behind.

Per-tool native-report mappings (Stryker → JSON, pitest XML → JSON, mutmut JUnit XML → JSON, Stryker.NET JSON, go-mutesting stdout) live with each language file under [`references/languages/`](references/languages/).

## When not to apply

- No tests exist yet → write tests first.
- No tool installed and user declines setup → explain the limitation; do not estimate.
- Prototype or spike code.
