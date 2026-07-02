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

The four steps above defend against the *fake-100 %-via-Timeout* variant of the MTP-runner incompatibility. The **complementary** *fake-0 %-via-Survived* variant (mutation-switch not observing mutations at runtime; every mutant reported `Survived`; final score `0.00 %`) is caught by [`SKILL.md`](../../SKILL.md) **Step 1c smoke gate** — run a single-file probe before any full run and parse `mutation-report.json` for `Killed > 0`. Do not skip Step 1c on xunit.v3 configurations; it is the specific safety net for issues [#554](https://github.com/bdfinst/agentic-dev-team/issues/554) and [#557](https://github.com/bdfinst/agentic-dev-team/issues/557). Inside a Claude Code session the [`mutation_testing_smoke_gate`](../../../../hooks/mutation_testing_smoke_gate.py) PreToolUse hook enforces this step automatically — see SKILL.md § Step 1c for the operator-facing contract.

## Default `coverage-analysis: perTest` for xunit.v2 / non-MTP projects

For Stryker.NET projects that are **not** on xunit.v3 / the MTP runner (see the [xunit.v3 detection](#xunitv3-detection-do-this-before-configuring-runs) section above, which stays mandatory for those projects), default `"coverage-analysis": "perTest"` in `stryker-config.json` rather than `"off"`. Per-test coverage tracking lets each mutant run only the tests that actually exercise the mutated line, instead of the full suite — a significant speedup on large suites.

[#669](https://github.com/bdfinst/agentic-dev-team/issues/669) validated this against an xunit.v2-shim repo (the shim workaround from #554/#557, described in the [SolutionPath trap](#solutionpath-trap) section below) at two points. It specifically checked the two failure modes a static-analysis-based coverage tool is prone to:

- **Reflection** (`MethodInfo.Invoke`) — a test invoking a private method via reflection correctly killed its target mutant under `perTest`.
- **Container-resolution DI** (Autofac `container.Resolve<T>()`) — 14 tests building a real Autofac container and resolving decorated services were correctly attributed as covering the registration statements they exercise.

Both risks checked out clean — zero mutants flipped from `Killed` to `Survived`/`NoCoverage` between the `"off"` baseline and `perTest`:

| File | Baseline (`off`) | `perTest` |
| --- | --- | --- |
| DataFormatter.cs | 40 Killed / 2 Survived | 41 Killed / 1 Survived |
| SystemConstants.cs | 78 Killed / 0 | 78 Killed / 0 — identical |
| RequestContext.cs | 10 Killed / 0 | 10 Killed / 0 — identical |
| PublicApiAttribute.cs | 1 Killed / 0 | 1 Killed / 0 — identical |
| ComponentModule.cs | 48 Killed / 168 Survived | 48 Killed / 164 Survived / 4 NoCoverage — identical Killed count |

Speed: the testing-phase wall-clock dropped roughly **5-6x** (~17-21 min under `off` → ~3-4 min under `perTest`; total run including build+shim went from ~19-24 min to ~6 min).

This recommendation **does not apply to xunit.v3 / MTP-runner projects** — the [xunit.v3 detection](#xunitv3-detection-do-this-before-configuring-runs) section's `"coverage-analysis": "off"` mandate above is unrelated and unaffected; #669 did not re-test that failure mode.

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

### Tiered mutation-level: Basic baseline, Standard escalation

Pairs with the mutation-kill agent's [tiered mutation-level](../../../../agents/mutation-kill.md#tiered-mutation-level-strykernet-only) rule: the baseline `--all` scan runs at `Basic`; only files with survivors remaining after Basic converges get a Standard-level pass scoped to that one file.

**Basic baseline (whole scan):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo
dotnet stryker \
  --config-file stryker-config.shard-<name>.json \
  --mutation-level Basic \
  --coverage-analysis perTest \
  --reporter json \
  -O StrykerOutput/baseline
```

**Standard escalation (single file, after Basic converges with survivors remaining):**

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo
dotnet stryker \
  --config-file stryker-config.shard-<name>.json \
  --mutation-level Standard \
  --mutate "**/CacheKeyBuilder.cs" \
  --coverage-analysis perTest \
  --reporter json \
  -O StrykerOutput/escalation-CacheKeyBuilder
```

If the Standard escalation run hits the caching/key-building `CompileError` trap above, drop back to the Basic-level results and exclude the file from further Standard-level attempts rather than retrying.

## Run (scoped)

Large C# repos take 60–90 min for a whole-project run. Always scope runs; if the repo has pre-generated shard configs, use them.

> When capturing run output to a log file, do **not** use a bare `dotnet stryker ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a Stryker failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

**Single file in `--scope` (Phase 4 per-Story gate):**

`coverage-analysis` is config-file-only in Stryker.NET 4.15.0 — there is no CLI flag for it (confirmed via `--help`); set it in `stryker-config.shard-<name>.json` (see [Default `coverage-analysis: perTest`](#default-coverage-analysis-pertest-for-xunitv2--non-mtp-projects) above) rather than passing it on the command line below.

```bash
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
dotnet build <solution> -c Debug --nologo

# Scope to the changed file within its shard config
dotnet stryker \
  --config-file stryker-config.shard-<name>.json \
  --mutate "**/ChangedFile.cs" \
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
# (set "coverage-analysis" in stryker-config.json itself — it's config-file-only, no CLI flag)
dotnet stryker --reporter json -O StrykerOutput/baseline
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

## Shipped wrapper

The plugin ships a Python wrapper + status loop under `plugins/dev-team/skills/mutation-testing/scripts/`:

- **`csharp_stryker_net_wrapper.py`** — hides `.sln` during the run + restores on any exit path, exports `DOTNET_ROOT` (auto-probed across all supported platforms; a pre-set value is respected), pre-builds `${SLN}` and optional `${SHIM_PROJECT}` **before** hiding, runs Stryker as a subprocess so SIGINT/SIGTERM kill the child too (no orphans), and redirects log via file descriptor (never a bare `| tee`).
- **`csharp_stryker_net_status_loop.py`** — status + red-flag inspection loop invoked by the wrapper. Ticks every `STATUS_INTERVAL` seconds emitting one status record plus zero-or-more `[RED-FLAG]` lines when known-broken patterns are observed (mutation-switch not observing; CompileError count over threshold; SolutionPath trap; Stryker died mid-run; parser drift).

Cross-platform authoritative: same code runs identically on macOS, Linux, Windows Git Bash, and native Windows via Python 3.8+'s stdlib. Requires only `python3` on PATH — no bash-shell tooling, no MSYS quirks. See [ADR 0014](../../../../../../docs/adr/0014-python-for-cross-os-scripts.md).

### Install

Copy `csharp_stryker_net_wrapper.py` AND `csharp_stryker_net_status_loop.py` into your repo's `scripts/` directory. The wrapper imports the status loop by module name; both files must sit next to each other so Python can find the loop on `sys.path`.

### Run

Run in place of a bare `dotnet stryker`:

```bash
python3 scripts/csharp_stryker_net_wrapper.py \
  --sln Foo.sln \
  --shim-project tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj \
  --stryker-bin dotnet-stryker \
  --logfile StrykerOutput/wrapper.log \
  --config-file stryker-config.json \
  --mutate "**/Validators/**/*.cs" \
  -O StrykerOutput/slice-validators
```

CLI flags (all optional; every one accepts an environment-variable equivalent so header-var configuration is preserved):

| Flag | Env var | Default |
| --- | --- | --- |
| `--sln PATH` | `SLN` | `Foo.sln` |
| `--shim-project PATH` | `SHIM_PROJECT` | (empty; no shim) |
| `--stryker-bin CMD` | `STRYKER_BIN` | `dotnet-stryker` |
| `--logfile PATH` | `LOGFILE` | `StrykerOutput/wrapper.log` |
| `--stryker-concurrency N` | `STRYKER_MUTANT_CONCURRENCY` | `max(1, cpu_count - 2)` (computed) |

Everything after those flags forwards to Stryker unchanged.

`DOTNET_ROOT` is auto-probed across the standard install locations on all supported platforms; a pre-set value is respected. When no SDK is found the wrapper exits 3 with an actionable message.

### Concurrency default

The wrapper defaults Stryker's own mutant-testing-process concurrency (its
`-c`/`--concurrency` flag) to `max(1, cpu_count - 2)` instead of Stryker's
flat default of 5, computed from `os.cpu_count()`. Override precedence,
highest to lowest: a pass-through `-c`/`--concurrency` already present in
the args forwarded to Stryker (explicit caller intent, never overridden) >
the `--stryker-concurrency` CLI flag > the `STRYKER_MUTANT_CONCURRENCY`
env var > the computed `cores - 2` default. When a pass-through value
conflicts with an explicit `--stryker-concurrency`/env value, the wrapper
logs a one-line note to stderr naming which pass-through value overrode
which explicit value — the override is never silent.

`--stryker-concurrency`/`STRYKER_MUTANT_CONCURRENCY` is deliberately **not**
named `--concurrency`/`-c`: that spelling is reserved for (a) Stryker's own
pass-through flag — registering `-c` as a wrapper-owned option would make it
structurally impossible for a caller's pass-through `-c` to ever reach the
"already present" detection above — and (b) `mutation-kill`'s own
pre-existing `--concurrency` flag (worktree fan-out, a different dial at a
different layer) despite the shared "cores − 2" heuristic.

**CI/cgroup caveat:** `os.cpu_count()` reads the host/system core count, not
a container's cgroup quota. On resource-capped CI runners this can compute a
concurrency value higher than the container's actual allotment — pass an
explicit `--stryker-concurrency` value (or set `STRYKER_MUTANT_CONCURRENCY`)
rather than rely on the computed default in those environments.

## Slice runner

The plugin ships a third script, `csharp_stryker_net_slice_runner.py`, under
`plugins/dev-team/skills/mutation-testing/scripts/`, layering first-class
slicing and configurable slice-level parallelism (#561) on top of the
wrapper documented above. It imports `csharp_stryker_net_wrapper.py`
directly and reuses its `hide_sln`/`restore_sln`/`build_project`/
`run_stryker` primitives — the slice runner does not duplicate the
DOTNET_ROOT probe, the pre-build-before-hide ordering, or the signal-safe
Stryker subprocess handling; it only adds the fleet-level orchestration
around them.

### Invocation

```bash
python3 scripts/csharp_stryker_net_slice_runner.py \
  --slices-config mutation-slices.json \
  --slice <name>       # a single configured slice by name
  --slice all          # every configured slice, resuming past terminal ones
  --sln Foo.sln \
  --output-root StrykerOutput \
  --total-workers auto
```

### `slices:` config block

A top-level `slices` array in `mutation-slices.json` (JSON, not YAML — this
plugin's shipped scripts are stdlib-only Python, and `json` is stdlib while
YAML is not). Only `name` + `mutate` are required in this first cut; `kind`,
`mutation-level`, and `exclude-converged` are accepted and passed through
but reserved for #667's within-slice refinements — a typo in one of those
field names still fails config validation, it just isn't acted on yet:

```json
{
  "slices": [
    {
      "name": "validators",
      "mutate": "**/Validators/**/*.cs",
      "kind": "logic",
      "mutation-level": "Basic",
      "exclude-converged": true
    },
    {
      "name": "services",
      "mutate": "**/Services/**/*.cs"
    }
  ]
}
```

Each generated per-slice `stryker-config.json` inherits
`"coverage-analysis": "perTest"` by default (per #669's validated
recommendation above); pass a `--base-config` pointing at an existing
`stryker-config.json` whose `"coverage-analysis": "off"` should be
preserved (e.g. xunit.v3/MTP projects) — an explicit value in the base
config always wins over the per-slice default.

### Output layout and the aggregate roll-up

Each slice writes its own report to
`<output-root>/slice-<name>/reports/mutation-report.json` (Stryker's native
JSON-reporter shape). After every slice in the run completes, the runner
reads each slice's report, sums per-status mutant counts, and writes one
aggregate roll-up to `<output-root>/aggregate-mutation-report.json` — the
stable, programmatic entry point for #667's glob-shrinking logic (or any
other tooling) instead of scraping per-slice reports individually.

### Resume by skipping terminal slices

A slice is **terminal** when its `mutation-report.json` exists, parses as
JSON, and has a non-empty `files` map — a partial file from a crashed mid-
run either fails to parse or has no `files` entries, so it is never
mistaken for a completed run. On `--slice all`, the runner skips every
terminal slice and logs `SKIPPED <name> — terminal report exists (use
--force to rerun)`; pass `--force` to rerun every selected slice
unconditionally, including terminal ones.

### Configurable slice-level parallelism

- `--total-workers N|auto` — the overall worker ceiling. `auto` (the
  default) computes `max(2, cores / 2)`.
- `--parallel-slices N` / `--per-slice-concurrency N` — optional hints for
  operators who want to fix one axis explicitly. When **both** are set, the
  runner refuses (unless `--force`) when their product exceeds
  `--total-workers`.
- When **neither** is set, the default split allocates slices first (up to
  the configured slice count), then divides the remainder as per-slice
  concurrency — this favours cross-slice parallelism over deeper
  within-slice parallelism, matching #667's per-slice-convergence work.
- A `--total-workers` value over `cores − 1` is refused with an error
  unless `--force` is passed, in which case it proceeds with a warning
  instead — never silently oversubscribe the machine.

### `.sln` hide/restore is a fleet-level ceremony, done once

Only one Stryker instance can safely hide the shared `.sln` at a time — a
per-slice hide/restore would race across parallel slices. The slice runner
hides `.sln` **once**, before spawning any slice, and restores it **once**,
after every slice in the fleet has finished (success, failure, or
exception) — never per slice. Individual slice invocations run against the
already-hidden `.sln` and never touch the hide/restore state themselves.

### Rolled-up progress reporting

The runner prints one rolled-up progress line per slice-state transition,
e.g.:

```
slice 1/7 running, slice 2/7 running, slice 3/7 queued, slice 4/7 queued, ...
slice 1/7 done, slice 2/7 running, slice 3/7 running, slice 4/7 queued, ...
```

Each slice's state is one of `queued`, `running`, `done`, or `failed`
(non-zero Stryker exit code); the overall exit code is the worst
(highest, non-zero-preferred) of all slice exit codes.

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

Adapter-side, `hooks/mutation_adapters/stryker_net.py` reads `STRYKER_SINCE_TARGET` when `CI` is not `true` and appends `--since:$STRYKER_SINCE_TARGET` to the command line. Set the env var on dev machines; leave it unset in CI so the gate always runs the full scan.

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
      "!**/*.Designer.cs",
      "!**/Validators/AddressValidator.cs"
    ]
  }
}
```

Pairs with the mutation-kill agent's [infrastructure exclusion detection](../../../../agents/mutation-kill.md#infrastructure-exclusion-detection-before-the-loop-starts) — the agent flags candidates at baseline scan time; this template is what actually removes them from the mutation set.

The last entry (`!**/Validators/AddressValidator.cs`) is a **convergence-derived**
negation, not an infra-exclusion one — the mutation-kill agent's [convergence
history](../../../../agents/mutation-kill.md#convergence-history-across---all-invocations)
mechanism added it because that file already converged (or was excluded) at a
recorded commit that still matches the file's current last-commit SHA. The two
kinds of negation share the same `mutate` array but differ in permanence: the
Startup/Program/Filter/etc. negations above are **permanent** (infrastructure
never becomes testable by adding more tests), while convergence-derived
negations like `AddressValidator.cs` are **re-checked on every `--all`
invocation and can drop out** the moment the file's source changes — at that
point the entry goes stale and the file re-enters scope automatically.

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
