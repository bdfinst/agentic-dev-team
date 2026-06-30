# Mutation Testing: Tool Setup & Time Estimation

## Time Estimation

Before running, estimate and present the expected duration to the user:

**Formula:** `mutation time ≈ (number of mutants) × (per-mutant test time)`

Tools optimize per-mutant time significantly:

- **Stryker** with `coverageAnalysis: "perTest"` runs only tests covering the mutated line, not the full suite
- **pitest** with `withHistory` skips mutants killed in prior runs — first run is slow, incremental runs are fast

**Rough heuristics (with per-test coverage analysis enabled):**

| Scope | LOC | Expected Duration |
| --- | --- | --- |
| Single small file | 50-200 | Seconds to ~1 min |
| Single medium file | 200-500 | 1-5 min |
| Multiple files / module | 500-1000 | 5-15 min |
| Full codebase | 1000+ | 10 min to hours |

The biggest variable is **test execution speed**, not mutant count. A project with slow integration tests will hurt far more than one with many mutants but fast unit tests.

**How to estimate for a specific project:**

1. Check how long the test suite takes: `time npm test` or `time mvn test`
2. Count approximate mutants: ~5-15 mutants per 100 LOC depending on code density
3. With per-test coverage: per-mutant time is typically 5-20% of full suite time
4. Without per-test coverage: per-mutant time ≈ full suite time (configure coverage analysis!)

**Present to user before running:**
> Mutation testing on `src/calculator.ts` (~150 LOC, ~20 mutants). Test suite runs in ~3s. Estimated time: under 1 minute. Proceed?

If the estimate exceeds 5 minutes, suggest scoping down or confirm the user is willing to wait.

## Detect or Set Up Tooling

Check what's available in the project:

| Ecosystem | Tool | Detection |
| --- | --- | --- |
| JS/TS | [Stryker](https://stryker-mutator.io/) | `package.json` has `@stryker-mutator/core` or `stryker.conf.json` exists |
| Java/Kotlin | [pitest](https://pitest.org/) | `pom.xml` or `build.gradle` has `pitest` plugin |
| Python | [mutmut](https://mutmut.readthedocs.io/) | `mutmut` in requirements or pyproject |
| C#/.NET | [Stryker.NET](https://stryker-mutator.io/docs/stryker-net/introduction/) | `dotnet-stryker` in tool manifest |
| Go | [go-mutesting](https://github.com/zimmski/go-mutesting) | `go.mod` present; `command -v go-mutesting` resolves (installed to `$GOPATH/bin`). **Advisory only.** |

**If no tool is found:** Help the user install one. For JS/TS projects:

```bash
npm install --save-dev @stryker-mutator/core @stryker-mutator/vitest-runner  # or jest-runner, karma-runner
npx stryker init
```

For Java with Maven:

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.4</version>
</plugin>
```

For Go projects (go-mutesting):

```bash
# Install
go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest

# Run (whole module)
go-mutesting ./...
```

**Go is advisory-only.** go-mutesting is alpha quality — its surviving-mutant count is **not** a reliable gate, so treat the results as advisory: surface survivors as suggestions, never block on the count. In orchestrated workflows the Go mutation gate defaults to **advisory** (warn, do not block).

**Complement with Go's built-in fuzzing.** Native fuzzing (Go 1.18+) is production-quality and catches boundary/edge cases mutation testing can miss. The `-fuzz` flag takes a regexp matching a single `FuzzXxx` target and fuzzes one package at a time — it is **not** a package glob:

```bash
# Run every fuzz target's seed corpus as ordinary tests (all packages)
go test ./...

# Actively fuzz one target (bounded for a pre-merge gate)
go test -fuzz=FuzzXxx -fuzztime=30s ./path/to/pkg
```

Manage the fuzz corpus deliberately: seed it from known edge cases, commit interesting inputs under `testdata/fuzz/` so failures reproduce in CI, and run a bounded `-fuzztime` in the pre-merge gate while letting longer campaigns run out of band.

**Do not proceed to mutation testing without a working tool.** (Go is the one exception where "no tool" still yields an actionable path: install go-mutesting in advisory mode, or fall back to `go test -fuzz` — never report "no tool installed" to a Go project without giving both.) If the user declines to install one, explain that this skill requires real test execution and cannot substitute estimation.

## Run the Tool (Scoped to Target)

Run the mutation tool scoped to the files the user specified or to changed files:

**Stryker (JS/TS):**

```bash
# Specific files
npx stryker run --mutate "src/calculator.ts"

# Changed files only (CI mode)
npx stryker run --mutate "$(git diff --name-only HEAD~1 -- '*.ts' | grep -v test | tr '\n' ',')"
```

**Pitest (Java):**

```bash
# Specific class
mvn pitest:mutationCoverage -DtargetClasses="com.example.Calculator"

# With history (faster incremental runs)
mvn pitest:mutationCoverage -DwithHistory
```

**mutmut (Python):**

```bash
mutmut run --paths-to-mutate=src/calculator.py
```

**Stryker.NET (C#):**

Large C# repos take 60–90 min for a whole-project run. Always scope runs; if
the repo has pre-generated shard configs, use them.

*Scoped to a single file (Phase 4 per-Story gate):*

```bash
# Scope to the changed file within its shard config
dotnet stryker \
  --config-file stryker-config.shard-<name>.json \
  --mutate "**/ChangedFile.cs" \
  --coverage-analysis perTest \
  --reporter json \
  --output StrykerOutput/gate-shard
```

*Full scan — shard configs present (Phase 5 convergence, initial baseline):*

```bash
# Run each shard sequentially; aggregate results
# stryker-pipeline.py --skip-agent handles this automatically
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-pipeline.py \
  --skip-agent
```

The pipeline writes one `StrykerOutput/shards/<name>/reports/mutation-report.json`
per shard. Aggregate kills and survivors across all reports for the total score.

*Full scan — no shard configs (first time, small repo):*

```bash
# Generate shard configs first to make future runs fast
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-setup.py

# Then run normally — dotnet stryker finds stryker-config.json
dotnet stryker --coverage-analysis perTest --reporter json
```

*Finding the relevant shard config for a given file (bash helper):*

```bash
changed_file="src/Foo.Bar/Controllers/PaymentController.cs"
for cfg in stryker-config.shard-*.json; do
  prefix=$(python3 -c "
import json
p = json.load(open('$cfg'))['stryker-config'].get('mutate', [''])[0]
print(p.split('/**')[0])
")
  [[ "$changed_file" == ${prefix}/* ]] && echo "$cfg" && break
done
```

Capture the full output. If the tool produces an HTML report, note its path for the user.

## Machine-readable output schema

When the SKILL is invoked with `--emit-json <path>`, write a `schema_version: 1` envelope (see `## Machine-readable output` in `SKILL.md` for the canonical schema). The mapping from each tool's native report to this envelope is below.

### Stryker (JS/TS) — example

Stryker's `reports/mutation/mutation.json` is the source. Map `metrics` to the top-level totals and `files[*].mutants[]` to `survivors[]`:

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

`status: "equivalent"` is set when Stryker's `status` field is `NoCoverage` paired with an operator type the triage step (Step 4) classifies as equivalent; otherwise `survived`.

### pitest (Java/Kotlin) — example

pitest emits `target/pit-reports/<date>/mutations.xml`. Map `<mutation status="SURVIVED">` to `survived`; `<mutation status="NO_COVERAGE">` to `survived` (uncovered, but technically a survivor for downstream callers).

```json
{
  "schema_version": 1,
  "tool": "pitest",
  "scope": ["src/main/java/com/example/Calculator.java"],
  "captured_at": "2026-06-19T14:25:11Z",
  "total": 36,
  "killed": 30,
  "survived": 4,
  "equivalent": 2,
  "survivors": [
    { "file": "src/main/java/com/example/Calculator.java", "line": 19, "operator": "CONDITIONALS_BOUNDARY", "status": "survived" }
  ]
}
```

### mutmut (Python) — example

mutmut's `mutmut results --json` is the source. Each surviving mutant carries `filename`, `line_number`, and a mutmut-specific mutation type.

```json
{
  "schema_version": 1,
  "tool": "mutmut",
  "scope": ["src/calculator.py"],
  "captured_at": "2026-06-19T14:28:42Z",
  "total": 28,
  "killed": 22,
  "survived": 5,
  "equivalent": 1,
  "survivors": [
    { "file": "src/calculator.py", "line": 12, "operator": "RelationalOperator", "status": "survived" }
  ]
}
```

### Stryker.NET (C#) — example

Stryker.NET writes `StrykerOutput/<run>/reports/mutation-report.json` in the same shape as JS Stryker. Map identically; `tool` is `"stryker-net"`.

```json
{
  "schema_version": 1,
  "tool": "stryker-net",
  "scope": ["src/Calculator/Calculator.cs"],
  "captured_at": "2026-06-19T14:31:00Z",
  "total": 44,
  "killed": 38,
  "survived": 4,
  "equivalent": 2,
  "survivors": [
    { "file": "src/Calculator/Calculator.cs", "line": 27, "operator": "ConditionalBoundary", "status": "survived" }
  ]
}
```

### Go (go-mutesting) — example

go-mutesting has no stable machine-readable report, so parse its stdout (each
mutant prints `PASS`/`FAIL` with the mutated `file:line`) and map it into the
same envelope, adding `"advisory": true` so callers warn instead of halt. The
`equivalent` count is `0` unless triage reclassifies a survivor. `tool` is
`"go-mutesting"`.

```json
{
  "schema_version": 1,
  "tool": "go-mutesting",
  "advisory": true,
  "scope": ["pkg/order/order.go"],
  "captured_at": "2026-06-26T14:31:00Z",
  "total": 40,
  "killed": 31,
  "survived": 9,
  "equivalent": 0,
  "survivors": [
    { "file": "pkg/order/order.go", "line": 22, "operator": "branch/condition", "status": "survived" }
  ]
}
```

Because go-mutesting is advisory, downstream workflow callers MUST treat
`advisory: true` as warn-not-block — a non-zero survivor count never fails the
gate. Pair the advisory result with `go test -fuzz` findings when reporting to
the operator.

### Error envelopes

When the per-language tool isn't installed, when the `--scope` glob expands to zero files, or when `--emit-json <path>` is unwritable, emit the structured errors documented in `SKILL.md` `## Machine-readable output`. Downstream callers decide whether to halt (no tool) or warn (empty scope).
