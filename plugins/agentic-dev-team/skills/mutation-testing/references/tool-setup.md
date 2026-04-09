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

**Do not proceed to mutation testing without a working tool.** If the user declines to install one, explain that this skill requires real test execution and cannot substitute estimation.

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

Capture the full output. If the tool produces an HTML report, note its path for the user.
