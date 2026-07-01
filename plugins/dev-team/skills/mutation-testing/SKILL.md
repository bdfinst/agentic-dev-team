---
name: mutation-testing
description: Validate test suite quality by running a real mutation testing tool and triaging surviving mutants. Use after writing tests to verify assertions catch behavioral changes, when evaluating test coverage quality, or as a CI quality gate on critical modules. The AI value here is triage — classifying survivors, writing fix tests — not generating or estimating mutations.
role: worker
user-invocable: true
---

# Mutation Testing

Wraps a real mutation tool (Stryker, pitest, mutmut, Stryker.NET, go-mutesting) and adds AI triage of survivors. The tool generates mutations and reports survivors; the AI classifies survivors and writes fix tests. **Never estimate or guess mutation outcomes** — if no tool is available, help set one up; do not substitute reasoning for execution.

This file describes the language-agnostic workflow and the data contract. **Per-language detail — install, run commands, timeout flag names, native-report mapping — lives in [`references/languages/`](references/languages/).** Detect the language first via [`references/tool-detection.md`](references/tool-detection.md), then load the matching language file.

## Constraints

- **Always ask the user before running.** Present the time estimate and scope; get explicit approval. Mutation testing can be slow — never surprise the user.
- Only run after tests exist; mutation testing validates tests, it does not replace them.
- Do not chase 100% mutation score; equivalent mutants are noise.
- Scope to changed files by default; full-codebase runs are periodic audits.
- Surviving mutants in critical paths require action; in trivial code they may be acceptable.
- **Per-mutant wall-clock timeout.** Every mutant run is capped at a wall-clock timeout. A run that exceeds the timeout counts as a **killed** mutant (matching the experiment-harness fix). Default: `timeout_seconds = max(60, suite_time_seconds × 10)`. Never run without a timeout — an infinite-loop mutant will hang the harness indefinitely. Per-tool flag names live in each [`references/languages/<lang>.md`](references/languages/).
- **`--workflow-managed-approval` carve-out.** When this flag is set, the `Step 0` confirmation prompt is skipped — but the "always ask the user before running" invariant still holds at a higher boundary. The flag is reserved for orchestrated workflows that capture operator approval once for the whole run, then propagate the consent down to each scoped invocation. The authoritative caller registry is [`references/workflow-callers.md`](references/workflow-callers.md). Today's allowed callers are `/coverage-delta` (Phase 4 of `/test-modernize`) and `/quality-targets-converge` (Phase 5); both inherit the workflow-level approval obtained at `/test-modernize` Phase 0. Any new caller must document where its workflow-level approval is captured before adopting the flag — see the registry file for the full process.

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

## Step 2: Run the tool (scoped to target)

Run scoped to user-specified files or changed files. Capture full output and note any HTML report paths. Per-language commands and scoping idioms — including the C# shard-aware execution path for large repos — live in [`references/languages/<lang>.md`](references/languages/).

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

## Step 3: Parse results

Extract surviving mutants. Map each to:

| Field | Source |
|---|---|
| File + line | Tool report |
| Mutation operator | Tool report (`ConditionalBoundary`, `NegateConditional`, etc.) |
| Original code | Read the source at that line |
| Mutated code | Tool report or infer from operator |
| Mutation score | Tool summary |

## Step 4: Triage survivors

For each mutant, classify and act. **`NoCoverage` outranks `Survived`** — a survived mutant at least ran, so a tighter assertion can kill it; a no-coverage mutant was never reached at all, so writing a test that exercises the path is the higher-leverage move.

| Classification | Meaning | Action |
|---|---|---|
| **NoCoverage** | No test exercises this code path at all | Add a test that reaches the path before worrying about killing the mutant — coverage is the prerequisite |
| **Equivalent** | Mutation produces identical behavior | Mark excluded — no test can kill it |
| **Missing assertion** | Test executes the code but doesn't assert on affected output | Strengthen the assertion |
| **Missing test case** | No test exercises the mutated path | Write a new test |
| **Undertested boundary** | Mutation exposes a boundary/edge with no coverage | Add a boundary test |
| **Acceptable risk** | Trivial code where the mutation doesn't matter | Document and skip |

**Recommended work order** — attack in this sequence, not by file order:

1. **NoCoverage** first (each conversion moves the honest score as much as killing a survivor, and it's usually cheaper — the unreached path just needs a test that touches it).
2. **Survived** next (assertion or coverage fix — see the mutation-type-aware guidance below).
3. **Equivalent** last (documentation only; no test to write).

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
4. **Classify** — missing assertion, missing test, boundary gap, or equivalent.
5. **Write the fix test** with RED-GREEN discipline: must fail against the mutant and pass against the original.

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

Report the **honest score** as the operator's primary signal. The claimed score (Stryker's headline) counts timeouts as kills and can inflate — on a real run 999 of 1305 reported "kills" were timeouts, so 61 % claimed corresponded to 23 % honest. Show both, honest above claimed, and emit the timeout warning when it fires. Formula derivation is documented in the [Machine-readable output](#machine-readable-output) section.

```markdown
## Mutation Testing Results

**Tool:** Stryker 8.x | **Scope:** src/calculator.ts | **Duration:** 45s | **Per-mutant timeout:** 60s
**Honest score:** 23.1% (306 killed / 1325 = killed + survived + no-coverage)
**Claimed score:** 61.3% (killed + timeout / killed + survived + timeout + no-coverage)

> ⚠️ **Timeout warning:** 76.5% of run outcomes were timeouts. The claimed score is
> not trustworthy — raise `additional-timeout` (per-tool flag; see the language reference)
> before treating either score as a gate.

### Surviving Mutants

| # | File:Line | Operator | Original | Mutated | Classification | Fix |
|---|---|---|---|---|---|---|
| 1 | calculator.ts:42 | ConditionalBoundary | `x > 0` | `x >= 0` | Missing boundary test | Add test: `expect(calc(0)).toBe(...)` |
| 2 | calculator.ts:67 | ReturnValue | `return result` | `return 0` | Missing assertion | Strengthen: assert on specific value |

### Equivalent Mutants (excluded)
| # | File:Line | Operator | Why equivalent |
|---|---|---|---|
| 1 | calculator.ts:15 | ArithmeticOperator | Dead code — branch unreachable |

### Recommended Test Additions
(Specific test code for each non-equivalent survivor)
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
  "timeout": 0,
  "no_coverage": 0,
  "compile_error": 0,
  "honest_score": 87.2,
  "claimed_score": 87.2,
  "timeout_pct": 0.0,
  "timeout_warning": false,
  "survivors": [
    { "file": "src/calculator.ts", "line": 42, "operator": "ConditionalBoundary", "status": "survived" },
    { "file": "src/calculator.ts", "line": 67, "operator": "ReturnValue",        "status": "equivalent" }
  ]
}
```

Each entry in `survivors` carries `file`, `line`, `operator`, and `status` where `status` is `"survived"` or `"equivalent"`. Callers MUST filter `status: "equivalent"` before computing deltas so reclassifications between runs don't show up as regressions.

An optional top-level `"advisory": true` flag marks a result from an advisory-only tool (go-mutesting today). When present, callers MUST treat the survivor count as warn-not-block — it never fails a gate. Absent (the default), the result is authoritative.

**Formulas.** The score fields are derived; the raw counts are the source of truth.

```
honest_score   = Killed / (Killed + Survived + NoCoverage)
claimed_score  = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
timeout_pct    = Timeout / (Killed + Survived + Timeout)
timeout_warning = timeout_pct > 0.05
```

The honest score matches the sibling `mutation-kill` agent's formula so both surfaces read the same number. It differs from Stryker's own "mutation score" line (Stryker counts `Timeout` toward the numerator). When `timeout_warning` is true, the claimed score is not trustworthy: raise the tool's `additional-timeout` (or equivalent per-tool wall-clock budget) before treating either score as a gate. The warning is advisory — not a hard gate that fails the run — so a caller can decide policy without the skill forcing one.

**Emitting adapters.** Adapters emit the additive score fields only when their native tool distinguishes `Timeout` and `NoCoverage` from `Killed`/`Survived`. Today that is Stryker (JS), **Stryker.NET**, pitest, and mutmut. Advisory-only tools that do not distinguish them — today's example is **go-mutesting** — omit the fields entirely rather than emit misleading zeros; the top-level `"advisory": true` flag is the caller's signal to treat the envelope as warn-not-block. Readers that consume the new fields MUST tolerate them being absent on an advisory envelope.

**Error envelopes (exit code non-zero, `<path>` still written for caller diagnostics):**

```json
{ "schema_version": 1, "tool": null, "error": "no_tool_installed", "language": "javascript" }
{ "schema_version": 1, "tool": "stryker", "error": "empty_scope", "scope_glob": "src/does-not-exist/*.ts" }
```

When `<path>` itself is unwritable (read-only directory, permission denied), the skill writes nothing to disk, prints the offending path to stderr, and exits non-zero. No partial JSON is left behind.

Per-tool native-report mappings (Stryker → JSON, pitest XML → JSON, mutmut → JSON, Stryker.NET JSON, go-mutesting stdout) live with each language file under [`references/languages/`](references/languages/).

## When not to apply

- No tests exist yet → write tests first.
- No tool installed and user declines setup → explain the limitation; do not estimate.
- Prototype or spike code.
