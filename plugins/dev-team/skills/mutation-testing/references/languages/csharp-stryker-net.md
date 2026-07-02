# Mutation Testing — C# / .NET (Stryker.NET)

Tool: [Stryker.NET](https://stryker-mutator.io/docs/stryker-net/introduction/). Detection: `dotnet-stryker` in tool manifest.

## Install / detect

The tool manifest is the **local** install path: `.config/dotnet-tools.json` lives in the repo, so `dotnet stryker` resolves via the manifest without depending on `$PATH`. A global install (`dotnet tool install -g dotnet-stryker`) is a fallback only — it depends on `~/.dotnet/tools` being on `PATH` and is the failure mode that motivated the "prefer local install" note in the skill.

```bash
dotnet new tool-manifest        # if no .config/dotnet-tools.json yet
dotnet tool install dotnet-stryker
```

Confirm the tool resolves before configuring a run:

```bash
dotnet stryker --version
```

## Environment preamble (macOS Homebrew)

`dotnet stryker` (whether invoked as the tool or as `~/.dotnet/tools/dotnet-stryker`) fails with **"You must install .NET to run this application"** when .NET is installed via Homebrew, because the runtime lives at `/opt/homebrew/opt/dotnet/libexec` rather than at the default path. Export `DOTNET_ROOT` before any Stryker invocation:

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
```

Confirm the local runtime path with:

```bash
dotnet --info | grep "Base Path"
```

Every run command below assumes this export is in scope.

## xunit.v3 detection (do this before configuring runs)

xunit.v3 adopted the Microsoft Testing Platform (MTP) runner. The MTP runner **does not support per-test coverage boundaries**, so `"coverage-analysis": "perTest"` silently falls back to running the entire test suite against every mutant — plus, hanging async tests burn the entire `additional-timeout` window. The observable symptoms are massive timeout counts, multi-hour runtimes, and a **fake 100% mutation score** (all mutants recorded as `Timeout`, none `Killed` or `Survived`). See [stryker-net#3117](https://github.com/stryker-mutator/stryker-net/issues/3117) and [stryker-net#3629](https://github.com/stryker-mutator/stryker-net/issues/3629).

Detect xunit.v3 before configuring the run:

```bash
grep -rl "xunit.v3" tests/ --include="*.csproj" 2>/dev/null
```

If detected, take **all four** steps below. Missing any one recreates the fake-score failure mode.

1. In every `stryker-config.json` (or per-shard config), set `"coverage-analysis": "off"` explicitly — not `perTest`.
2. Create `xunit.runner.json` in each test project directory with `"testTimeout": 5000` to cap individual hanging tests at 5 s:

    ```json
    {
      "$schema": "https://xunit.net/schema/current/xunit.runner.schema.json",
      "testTimeout": 5000
    }
    ```

3. Deploy `xunit.runner.json` to the output directory by adding this to each test `.csproj`:

    ```xml
    <ItemGroup>
      <None Update="xunit.runner.json">
        <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
      </None>
    </ItemGroup>
    ```

4. In `stryker-config.json`, set `"additional-timeout": 30000` — headroom for ~5 hanging tests × 5 s `testTimeout` per mutant plus overhead. This is a **layered** cap on top of the per-mutant `timeout` documented in [`SKILL.md`](../../SKILL.md) Step 1b.

The four steps above defend against the *fake-100 %-via-Timeout* variant of the MTP-runner incompatibility. The **complementary** *fake-0 %-via-Survived* variant (mutation-switch not observing mutations at runtime; every mutant reported `Survived`; final score `0.00 %`) is caught by [`SKILL.md`](../../SKILL.md) **Step 1c smoke gate** — run a single-file probe before any full run and parse `mutation-report.json` for `Killed > 0`. Do not skip Step 1c on xunit.v3 configurations; it is the specific safety net for issues [#554](https://github.com/bdfinst/agentic-dev-team/issues/554) and [#557](https://github.com/bdfinst/agentic-dev-team/issues/557).

## Pre-run: build first

Always build before timing the baseline suite or invoking Stryker. A stale binary produces phantom failures — Stryker either aborts on load or reports every mutant as `Survived`. Baseline timing:

```bash
dotnet build <solution> -c Debug --nologo
time dotnet test <test-project> -c Debug --no-build
```

Every Stryker run block below assumes a fresh `dotnet build ... -c Debug --nologo` immediately precedes it.

## Config authoring notes

Stryker.NET rejects **any unknown key** in `stryker-config.json` since v1.x — a JSON comment workaround like `"_note": "..."` or `"//": "..."` causes the entire run to fail with a clear error message. Do not embed intent comments in the config. Document config intent in the git commit message that introduces the config, or in a nearby `README.md`.

### SolutionPath trap

When `stryker-config.json` sets **both** `SolutionPath` and an explicit `test-projects` list, Stryker.NET evidently enumerates additional test projects from the solution and prefers them over the ones listed in `test-projects`. On a repo whose main test project is on xunit.v3 + MTP but whose configured `test-projects` points at a working xunit.v2 shim, this manifests as the shim's `InternalsVisibleTo` grant and successful smoke tests not helping — because Stryker isn't actually running the shim; it's running the main xunit.v3 test project it discovered via `SolutionPath`, and the fake-0 %-via-Survived MTP failure mode from #554 strikes anyway. The `--diag` output reveals this via a `Property TargetPath=` line naming the wrong test-project `.dll`. See issue [#557](https://github.com/bdfinst/agentic-dev-team/issues/557).

Three remediation paths, in order of preference:

1. **Remove `SolutionPath` from `stryker-config.json`.** Rely on `test-projects` only. Simplest fix; the plugin **recommends this path** for multi-project repos where the only reason `SolutionPath` was set was to help Stryker resolve source-project dependencies — the explicit `test-projects` list gives it what it needs. This is the path documented in the shipped wrapper.
2. **Add the shim project to the solution and exclude the main test project from Stryker's discovery.** Requires per-repo solution-file surgery and a Stryker-side exclusion rule; brittle and not documented upstream.
3. **Downgrade the main test project to xunit.v2** for the mutation window. Nuclear option — invasive to the main test suite for the duration of a mutation-testing session; only use when path 1 is genuinely impossible.

### Reporters — use `dots` for log-tail parsing

Configure Stryker with a **non-ANSI** reporter alongside JSON/HTML so status-loop tooling and log inspection can read progress deterministically:

```json
{
  "stryker-config": {
    "reporters": ["dots", "json", "html"]
  }
}
```

The default `progress` reporter uses ANSI in-place cursor updates that **do not survive log redirection** — a redirected run's log file has no per-mutant progress record. The `dots` reporter emits one `.` per completed mutant to stdout, which redirects cleanly. Any long-run inspection tooling (see [`SKILL.md` → Long-run inspection](../../SKILL.md#long-run-inspection)) that reads progress from a log tail depends on `dots` (or JSON) being configured.

### Probe file selection — C#-specific traps

The language-agnostic probe rule (≥ 50 mutants, highest existing mutation score, avoid generated code / DTOs / near-0 %-coverage files) lives in [`../../SKILL.md`](../../SKILL.md) Step 2 — read it first. Two Stryker.NET-specific probe anti-patterns compound the general rule; picking either as a probe validates nothing and produces a mass-CompileError smoke plume:

- **gRPC / Protobuf service implementations.** Stryker.NET's `ObjectInitializer` mutations target the auto-generated Protobuf message types. Because those types are code-generated, the mutations produce constructor / initializer forms that do not compile, yielding hundreds to thousands of `CompileError` mutants — no signal, only cost. Avoid these files as probes; scope them out of full runs unless you have a specific reason.
- **Caching / key-building classes under `mutation-level: Standard`.** The `Standard` mutation level enables `LinqMutation` and `StringMutation` operators that generate calls to methods that **do not exist** — for example `StringBuilder.Prepend` (the method is `Insert(0, …)`) and `IDictionary.Sum` (there is no `Sum` extension in the target namespace). These produce 1000+ `CompileError` mutants on files that build hash keys or aggregate LINQ. Drop such files to `mutation-level: Basic` (or exclude them) before probing.

## Run (scoped)

Large C# repos take 60–90 min for a whole-project run. Always scope runs; if the repo has pre-generated shard configs, use them.

> When capturing run output to a log file, do **not** use a bare `dotnet stryker ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a Stryker failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

**Single file in `--scope` (Phase 4 per-Story gate):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo

# Scope to the changed file within its shard config
dotnet stryker \
  --config-file stryker-config.shard-<name>.json \
  --mutate "**/ChangedFile.cs" \
  --coverage-analysis perTest \
  --reporter json \
  -O StrykerOutput/gate-shard
```

**Full scan — shard configs present (Phase 5 convergence, initial baseline):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo

# Run each shard sequentially; aggregate results.
# stryker-pipeline.py --skip-agent handles this automatically.
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-pipeline.py \
  --skip-agent
```

The pipeline writes one `StrykerOutput/shards/<name>/reports/mutation-report.json` per shard. Aggregate kills and survivors across all reports for the total score.

**Full scan — no shard configs (first time, small repo):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo

# Generate shard configs first to make future runs fast
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-setup.py

# Then run — dotnet stryker finds stryker-config.json
dotnet stryker --coverage-analysis perTest --reporter json -O StrykerOutput/baseline
```

**Named-run output directories.** Use the `-O` / `--output` CLI flag to name the output directory, e.g. `-O StrykerOutput/baseline` and `-O StrykerOutput/verification`. Do **not** use `--report-file-name` as a CLI flag — it is not one; it is a **config-file key** (`"report-file-name"` inside `stryker-config.json`) that renames the HTML/JSON output files *within* whichever directory `-O` selected.

**Probe a single file (default verbosity):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo

# Info-level output is default and readable — use trace only when debugging a startup problem.
dotnet stryker -m "**/ProbeFile.cs" -O StrykerOutput/probe
```

Extract the summary from any run regardless of verbosity:

```bash
grep -E "Killed:|Survived:|Timeout:|mutation score" <output-log> | tail -5
```

`-V trace` is a debug-only escape hatch for Stryker startup problems — it emits 1.5M+ lines for a two-minute probe run and buries the summary. Do not include it in probe or gate commands.

**Finding the relevant shard config for a given file (bash helper):**

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

## Shipped wrapper — copy both files together

The plugin ships two operational helper scripts under `plugins/dev-team/skills/mutation-testing/scripts/`:

- **`csharp-stryker-net-wrapper.sh`** — hides `.sln` during the run + trap-restores it on any exit path (EXIT / INT / TERM), exports `DOTNET_ROOT` (Homebrew macOS default; respects a pre-set value), pre-builds `${SLN}` and optional `${SHIM_PROJECT}` **before** hiding, backgrounds Stryker so a wrapper-side SIGINT/SIGTERM kills the child too (no orphans), and redirects with `> "$LOGFILE" 2>&1` (never bare `| tee`).
- **`csharp-stryker-net-status-loop.sh`** — status + red-flag inspection loop sourced by the wrapper. Ticks every `STATUS_INTERVAL` seconds emitting one status record plus zero-or-more `[RED-FLAG]` lines when known-broken patterns are observed (mutation-switch not observing; CompileError count over threshold; SolutionPath trap; Stryker died mid-run; parser drift).

**Copy BOTH files together** into your repo's `scripts/` directory. The wrapper `. "$(dirname "${BASH_SOURCE[0]}")/csharp-stryker-net-status-loop.sh"` — copying only the wrapper hard-fails at `set -e` on the missing `source` when `STATUS_INTERVAL > 0` (the default). If you deliberately want the wrapper without the loop, set `STATUS_INTERVAL=0` in the header vars to disable the loop entirely; the source call is guarded on that check.

Header vars (edit at the top of the wrapper for your repo):

```bash
SLN="Foo.sln"                                      # your solution file
SHIM_PROJECT="tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj"  # or "" if none
STRYKER_BIN="dotnet-stryker"                       # local tool manifest or global
LOGFILE="StrykerOutput/wrapper.log"
STATUS_INTERVAL=600                                # 10-min default; 0 disables the loop
COMPILE_ERROR_THRESHOLD=25                         # tune per repo
```

Run it in place of a bare `dotnet stryker`:

```bash
./scripts/csharp-stryker-net-wrapper.sh --config-file stryker-config.json \
  --mutate "**/Validators/**/*.cs" -O StrykerOutput/slice-validators
```

The wrapper forwards `"$@"` to Stryker unchanged.

## Incremental runs with `--since`

For fast iteration during Phase-4 test-fix work, add a `since` block to the dev shard config so Stryker only mutates source files that changed vs a reference (typically `main`):

```json
// stryker-config.shard-<name>.json — development / Phase 4 fix loop
{
  "stryker-config": {
    "since": {
      "enabled": true,
      "target": "main"
    }
  }
}
```

Run with the dev config for fast feedback:

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo
dotnet stryker --config-file stryker-config.shard-webapi.json
```

**Trap — verification runs must NOT use `since`.** `--since` limits mutations to **source** files that changed since the git ref. Test-file changes do **not** trigger source-file mutations, so a verification run through a `--since` config silently produces **0 results** — no mutants, no report, no useful signal. Always keep a **separate** verification config (`stryker-config.verification.json` or equivalent) that is identical to the dev shard config **except** for having no `since` block:

```bash
# Full verification — no --since; mutates every source file in scope
dotnet stryker --config-file stryker-config.verification.json -O StrykerOutput/verification
```

Adapter-side, `hooks/mutation-adapters/stryker-net.sh` reads `STRYKER_SINCE_TARGET` when `CI` is not `true` and appends `--since:$STRYKER_SINCE_TARGET` to the command line. Set the env var on dev machines; leave it unset in CI so the gate always runs the full scan.

## Infrastructure exclusion `mutate` glob template

DI wiring, exception handlers, and generated code produce mutations that no test surface can kill — dragging the score down without providing any signal. Exclude them from the `mutate` glob in the shard config:

```json
// stryker-config.shard-webapi.json
{
  "stryker-config": {
    "mutate": [
      "**/MyProject.WebAPI/**/*.cs",
      "!**/Startup.cs",
      "!**/Program.cs",
      "!**/*ExceptionFilter.cs",
      "!**/*ExceptionFormatter.cs",
      "!**/*LoggerService.cs",
      "!**/*.Designer.cs"
    ]
  }
}
```

Pairs with the mutation-kill agent's [infrastructure exclusion detection](../../../../agents/mutation-kill.md#infrastructure-exclusion-detection-before-the-loop-starts) — the agent flags candidates at baseline scan time; this template is what actually removes them from the mutation set.

## Score formula and NoCoverage

Stryker.NET's own score formula (v4.x):

```
score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
```

`NoCoverage` sits in the denominator even though those mutants are never executed. A file with 27 `NoCoverage` mutants at 0% score drags the overall score down more than a file with 20 `Survived` mutants at 70%. **Fix `NoCoverage` first** — any test that reaches the line kills a `NoCoverage` mutant, so ROI is higher than crafting value-specific assertions to kill hard `Survived` mutants. This mirrors the mutation-kill agent's [NoCoverage-first-class-signal](../../../../agents/mutation-kill.md#nocoverage-is-a-first-class-signal) guidance.

## Per-mutant timeout flag

Configure in `stryker-config.yaml` (or the per-shard JSON config):

```yaml
timeout: 60000   # milliseconds
```

Default shipped: 60 000 ms. Set `timeout` to `timeout_seconds × 1000` (formula in [`SKILL.md`](../../SKILL.md) Step 1b). For xunit.v3 test projects, also set `additional-timeout: 30000` (see the xunit.v3 detection section above) — the two settings compose.

## Native report → schema mapping

Source: `StrykerOutput/<run>/reports/mutation-report.json` (same shape as JS Stryker). Map identically; `tool` is `"stryker-net"`.

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

## Language-specific notes

### Shard-aware execution for large repos

For C# repos, `dotnet stryker` against the whole solution can take 60–90 minutes. The mutation gate adapter (`stryker-net.sh`) will time out and skip rather than run. The fix is **shard configs** generated by `stryker-setup.py` (from the [nextgen-test-upgrade-process](https://dev.azure.com/acispeedpayportfolio/acispeedpay/_git/nextgen-test-upgrade-process) toolkit):

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
# One-time setup in the target repo — generates stryker-config.shard-*.json
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-setup.py
```

Once shard configs exist, the adapter automatically:

1. Detects which shard covers the changed file (by matching the shard's `mutate` path prefix).
2. Passes `--config-file stryker-config.shard-<name>.json` to scope Stryker to that source project + its tests.
3. Further narrows with `--mutate "**/ChangedFile.cs"` so only the one changed file is mutated.
4. Writes results to `StrykerOutput/gate-shard/` (via `-O`) so gate runs don't overwrite full pipeline reports.

This drops the wall-clock time from 60–90 min (whole repo) to **5–15 min** (one file in one shard), which fits within the adapter's 600-second outer timeout.

**Without shard configs**, the adapter falls back to `stryker-config.json` (master config). If the master config also mutates the whole codebase this will still time out — run `stryker-setup.py` to fix it.

### Batch improvement pipeline

For the full improvement pipeline (not the per-test gate), use `stryker-pipeline.py` instead of bare `dotnet stryker`. It runs shards sequentially, fixes survivors with `mutation-agent.py` using the Claude Code CLI, and is the right tool for batch mutation-score improvement. Pre-build first, then invoke:

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo
python3 /path/to/nextgen-test-upgrade-process/scripts/stryker-pipeline.py
```
