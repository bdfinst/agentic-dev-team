# Mutation Testing — C# / .NET (Stryker.NET)

Tool: [Stryker.NET](https://stryker-mutator.io/docs/stryker-net/introduction/). Detection: `dotnet-stryker` in tool manifest.

## Install / detect

```bash
dotnet new tool-manifest        # if no .config/dotnet-tools.json yet
dotnet tool install dotnet-stryker
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

## Pre-run: build first

Always build before timing the baseline suite or invoking Stryker. A stale binary produces phantom failures — Stryker either aborts on load or reports every mutant as `Survived`. Baseline timing:

```bash
dotnet build <solution> -c Debug --nologo
time dotnet test <test-project> -c Debug --no-build
```

Every Stryker run block below assumes a fresh `dotnet build ... -c Debug --nologo` immediately precedes it.

## Config authoring notes

Stryker.NET rejects **any unknown key** in `stryker-config.json` since v1.x — a JSON comment workaround like `"_note": "..."` or `"//": "..."` causes the entire run to fail with a clear error message. Do not embed intent comments in the config. Document config intent in the git commit message that introduces the config, or in a nearby `README.md`.

### Probe file selection — C#-specific traps

The language-agnostic probe rule (≥ 50 mutants, highest existing mutation score, avoid generated code / DTOs / near-0 %-coverage files) lives in [`../../SKILL.md`](../../SKILL.md) Step 2 — read it first. Two Stryker.NET-specific probe anti-patterns compound the general rule; picking either as a probe validates nothing and produces a mass-CompileError smoke plume:

- **gRPC / Protobuf service implementations.** Stryker.NET's `ObjectInitializer` mutations target the auto-generated Protobuf message types. Because those types are code-generated, the mutations produce constructor / initializer forms that do not compile, yielding hundreds to thousands of `CompileError` mutants — no signal, only cost. Avoid these files as probes; scope them out of full runs unless you have a specific reason.
- **Caching / key-building classes under `mutation-level: Standard`.** The `Standard` mutation level enables `LinqMutation` and `StringMutation` operators that generate calls to methods that **do not exist** — for example `StringBuilder.Prepend` (the method is `Insert(0, …)`) and `IDictionary.Sum` (there is no `Sum` extension in the target namespace). These produce 1000+ `CompileError` mutants on files that build hash keys or aggregate LINQ. Drop such files to `mutation-level: Basic` (or exclude them) before probing.

## Run (scoped)

Large C# repos take 60–90 min for a whole-project run. Always scope runs; if the repo has pre-generated shard configs, use them.

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
