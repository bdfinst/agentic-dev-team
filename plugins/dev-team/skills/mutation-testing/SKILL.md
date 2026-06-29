---
name: mutation-testing
description: Validate test suite quality by running a real mutation testing tool and triaging surviving mutants. Use after writing tests to verify assertions catch behavioral changes, when evaluating test coverage quality, or as a CI quality gate on critical modules. The AI value here is triage — classifying survivors, writing fix tests — not generating or estimating mutations.
role: worker
user-invocable: true
---

# Mutation Testing

Wraps a real mutation tool (Stryker, pitest, mutmut, Stryker.NET, go-mutesting) and adds AI triage of survivors. The tool generates mutations and reports survivors; the AI classifies survivors and writes fix tests. **Never estimate or guess mutation outcomes** — if no tool is available, help set one up; do not substitute reasoning for execution.

## Constraints

- **Always ask the user before running.** Present the time estimate and scope; get explicit approval. Mutation testing can be slow — never surprise the user.
- Only run after tests exist; mutation testing validates tests, it does not replace them.
- Do not chase 100% mutation score; equivalent mutants are noise.
- Scope to changed files by default; full-codebase runs are periodic audits.
- Surviving mutants in critical paths require action; in trivial code they may be acceptable.
- **Per-mutant wall-clock timeout.** Every mutant run is capped at a wall-clock timeout. A run that exceeds the timeout counts as a **killed** mutant (matching the experiment-harness fix). Default: `timeout_seconds = max(60, suite_time_seconds × 10)`. Never run without a timeout — an infinite-loop mutant will hang the harness indefinitely.
- **`--workflow-managed-approval` carve-out.** When this flag is set, the `Step 0` confirmation prompt is skipped — but the "always ask the user before running" invariant still holds at a higher boundary. The flag is reserved for orchestrated workflows that capture operator approval once for the whole run, then propagate the consent down to each scoped invocation. The authoritative caller registry is [`references/workflow-callers.md`](references/workflow-callers.md). Today's allowed callers are `/coverage-delta` (Phase 4 of `/test-modernize`) and `/quality-targets-converge` (Phase 5); both inherit the workflow-level approval obtained at `/test-modernize` Phase 0. Any new caller must document where its workflow-level approval is captured before adopting the flag — see the registry file for the full process.

## Parse Arguments

The skill accepts free-form natural-language arguments AND the following named flags for workflow callers:

- `--scope <files-or-globs>` — restrict the mutation run to the listed files or shell globs. Comma-separated lists and quoted globs both accepted. When omitted, the skill scopes to changed files by default.
- `--emit-json <path>` — write the structured result to `<path>` (see `## Machine-readable output` below) in addition to any human-readable output. The path's parent directory must be writable; failure writes to stderr and exits non-zero.
- `--workflow-managed-approval` — skip the `Step 0` confirmation gate because the calling workflow captured approval at a higher boundary. Restricted to the allowlist in `## Constraints`.

## Time estimation

Use the heuristics in `references/tool-setup.md`. Present the estimate to the user; if > 5 minutes, suggest scoping down.

## Step 0: Confirmation gate

Before any mutation run, present the estimated time and the scope, then block on stdin for explicit approval. The prompt is observable: stdout contains the literal string `Estimated time:` followed by the scope summary. This gate is **skipped when `--workflow-managed-approval` is set** — see the carve-out in `## Constraints`.

## Step 1: Detect or set up tooling

Detect and install the tool for the project's language (Stryker for JS/TS, pitest for Java/Kotlin, mutmut for Python, Stryker.NET for C#, go-mutesting for Go). Per-language detection and installation: `references/tool-setup.md`. **Do not proceed without a working tool.**

**Go is advisory-only.** When the project has a `go.mod`, resolve to **go-mutesting** in advisory mode (it is alpha quality — the surviving-mutant count is not a reliable gate). Advisory mode emits the `schema_version: 1` envelope with `"advisory": true`; orchestrated workflows treat that as **warn, do not block** — a non-zero survivor count never fails the gate. Always pair it with Go's built-in fuzzing (`go test -fuzz=FuzzXxx -fuzztime=30s ./path/to/pkg` — `-fuzz` takes a single target regexp, not a package glob), which is production-quality, for boundary and edge-case discovery. Never tell a Go project "no tool installed" without giving both the go-mutesting install path and the fuzz alternative.

## Step 1b: Configure per-mutant timeout

Set a per-mutant wall-clock timeout before running. A timed-out mutant is **killed**
(counts toward the mutation score as a non-survivor). This matches the experiment-harness
fix in `docs/experiments/`.

Derive the timeout:

```
suite_time_seconds = time the baseline test suite (from Step 1 output, or measure: `time <test-command>`)
timeout_seconds    = max(60, suite_time_seconds × 10)
```

Per-tool configuration:

| Tool | Config | Default shipped |
|------|--------|-----------------|
| **Stryker (JS/TS)** | `stryker.config.js`: `timeoutMS: <ms>`, `timeoutFactor: 2.5` | 60 000 ms |
| **pitest (Java/Kotlin)** | CLI: `--timeoutConst 60 --timeoutFactor 2.5` | 60 s const |
| **mutmut (Python)** | CLI: `--timeout <seconds>` (passed to subprocess) | 60 s |
| **Stryker.NET (C#)** | `stryker-config.yaml`: `timeout: 60000` | 60 000 ms |
| **go-mutesting (Go)** | no reliable per-mutant flag — wrap the process externally: `timeout <seconds> go-mutesting ./...` (`gtimeout` on macOS) | 60 s |

Set the tool timeout to `timeout_seconds` (converting to ms for Stryker / Stryker.NET)
before running Step 2. Document the chosen timeout in the output summary.

### Stryker.NET (C#): shard-aware execution for large repos

For C# repos, `dotnet stryker` run against the whole solution can take 60–90 minutes. The mutation gate adapter (`stryker-net.sh`) will time out and skip rather than run. The fix is **shard configs** generated by `stryker-setup.py` (from the [nextgen-test-upgrade-process](https://dev.azure.com/acispeedpayportfolio/acispeedpay/_git/nextgen-test-upgrade-process) toolkit):

```bash
# One-time setup in the target repo — generates stryker-config.shard-*.json
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-setup.py
```

Once shard configs exist, the adapter automatically:

1. Detects which shard covers the changed file (by matching the shard's `mutate` path prefix)
2. Passes `--config-file stryker-config.shard-<name>.json` to scope Stryker to that source project + its tests
3. Further narrows with `--mutate "**/ChangedFile.cs"` so only the one changed file is mutated
4. Writes results to `StrykerOutput/gate-shard/` so gate runs don't overwrite full pipeline reports

This drops the wall-clock time from 60–90 min (whole repo) to **5–15 min** (one file in one shard), which fits within the adapter's 600-second outer timeout.

**Without shard configs**, the adapter falls back to `stryker-config.json` (master config). If the master config also mutates the whole codebase this will still time out — run `stryker-setup.py` to fix it.

**For the full improvement pipeline** (not the per-test gate), use `stryker-pipeline.py` instead of bare `dotnet stryker`. It runs shards sequentially, fixes survivors with `mutation-agent.py` using the Claude Code CLI, and is the right tool for batch mutation score improvement:

```bash
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-pipeline.py
```

## Step 2: Run the tool (scoped to target)

Run scoped to user-specified files or changed files. Per-language commands: `references/tool-setup.md`. Capture full output and note HTML report paths.

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

For each survivor, classify and act:

| Classification | Meaning | Action |
|---|---|---|
| **Equivalent** | Mutation produces identical behavior | Mark excluded — no test can kill it |
| **Missing assertion** | Test executes the code but doesn't assert on affected output | Strengthen the assertion |
| **Missing test case** | No test exercises the mutated path | Write a new test |
| **Undertested boundary** | Mutation exposes a boundary/edge with no coverage | Add a boundary test |
| **Acceptable risk** | Trivial code where the mutation doesn't matter | Document and skip |

### Triage procedure

1. **Read the source context** — what does the code do and why.
2. **Check for equivalence** — does the mutation actually change observable behavior? Common equivalent patterns: dead code or unreachable branches; commutative-operation reorderings; conditions redundant with other guards; logging/debug-only code.
3. **Find related tests** — which tests cover this code; what do they assert.
4. **Classify** — missing assertion, missing test, boundary gap, or equivalent.
5. **Write the fix test** with RED-GREEN discipline: must fail against the mutant and pass against the original.

### Weak vs strong test patterns

Most survivors come from tests that execute code without meaningfully asserting on behavior:

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

```markdown
## Mutation Testing Results

**Tool:** Stryker 8.x | **Scope:** src/calculator.ts | **Duration:** 45s | **Per-mutant timeout:** 60s
**Score:** 82% (41 killed / 50 total, 3 equivalent, 6 survived)

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
  "survivors": [
    { "file": "src/calculator.ts", "line": 42, "operator": "ConditionalBoundary", "status": "survived" },
    { "file": "src/calculator.ts", "line": 67, "operator": "ReturnValue",        "status": "equivalent" }
  ]
}
```

Each entry in `survivors` carries `file`, `line`, `operator`, and `status` where `status` is `"survived"` or `"equivalent"`. Callers MUST filter `status: "equivalent"` before computing deltas so reclassifications between runs don't show up as regressions.

An optional top-level `"advisory": true` flag marks a result from an advisory-only tool (go-mutesting today). When present, callers MUST treat the survivor count as warn-not-block — it never fails a gate. Absent (the default), the result is authoritative.

**Error envelopes (exit code non-zero, `<path>` still written for caller diagnostics):**

```json
{ "schema_version": 1, "tool": null, "error": "no_tool_installed", "language": "javascript" }
{ "schema_version": 1, "tool": "stryker", "error": "empty_scope", "scope_glob": "src/does-not-exist/*.ts" }
```

When `<path>` itself is unwritable (read-only directory, permission denied), the skill writes nothing to disk, prints the offending path to stderr, and exits non-zero. No partial JSON is left behind.

Per-tool worked examples (Stryker, pitest, mutmut, Stryker.NET) live in `references/tool-setup.md` under `## Machine-readable output schema`.

## When not to apply

- No tests exist yet → write tests first.
- No tool installed and user declines setup → explain the limitation; do not estimate.
- Prototype or spike code.
