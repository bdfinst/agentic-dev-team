---
name: stryker-xunit-v2-shim
description: Build a xunit.v2 Stryker shim so Stryker.NET produces a valid mutation score for a xunit.v3 test project. Stryker.NET cannot observe mutant kills through xunit.v3 (it runs on the Microsoft Testing Platform), so a normal run reports a false near-zero score with almost every mutant reported Survived. Use this BEFORE running Stryker whenever the target .NET test project references xunit.v3 — including when mutation is enabled via /test-improve or /mutation-testing, or you are about to run dotnet-stryker — and as a rescue when a run already reported ~0% or everything Survived or the user says the score looks suspiciously low. When Stryker and xunit.v3 both appear, build the shim first.
role: worker
user-invocable: true
---

# Stryker xunit.v2 Shim

Role: worker. Builds measurement scaffolding and does not modify the tests it
measures.

## Why this exists

Stryker.NET (through at least 4.15/4.16) **cannot observe mutant kills through
xunit.v3**. xunit.v3 runs on the Microsoft Testing Platform (MTP), and Stryker's
per-test coverage/kill mapping doesn't work across it (stryker-net issues 3237,
3629, 3094). The run completes and the initial test pass even succeeds, so the
failure is **silent** — the only symptom is the score: near-zero, with almost
every mutant reported *Survived* (e.g. `0.13% — 3 killed / 7,685 survived`). That
is the **observation-failure signature**, not a real result.

The fix is a **shim**: a second test project that recompiles the *same test source
files* under xunit.v2 (classic VSTest), which Stryker observes correctly. No test
is rewritten — the shim **links** the existing `.cs` files, so there is one source
of truth. Stryker is then run **from the shim directory** in project mode.

[`references/shim-howto.md`](references/shim-howto.md) has the full reference build
and any edge case not covered here.

## When to build it

Detection is one check: a test `.csproj` contains `Include="xunit.v3"`. Build the
shim **proactively, before the first Stryker run** — because the failure is silent
(the run succeeds and the score is bogus), waiting for the symptom wastes a full,
possibly hours-long run. As a backstop the `stryker_xunit_shim_guard.py` PreToolUse
hook auto-scaffolds the shim (and reports what it wrote) when you run
`dotnet-stryker` against a xunit.v3 project without one, then blocks so you re-run
from the shim dir — but build it proactively rather than relying on the interception.

One precondition decides whether the shim is cheap: source compatibility with
xunit.v2. `[Fact]`, `[Theory]`, `[InlineData]`, `TheoryData<>`, `MemberData`,
`ClassData`, and `Assert.*` are source-identical between v2 and v3, so a plain
suite ports in minutes. `AutoFixture.Xunit3` `[AutoData]`/`[InlineAutoData]` are
**not** v2-compatible; if the suite leans on them heavily, say so and stop rather
than forcing it. The Step 1 scope probe quantifies this.

## Workflow

### Step 1 — Scope probe (decide whether the shim is cheap)

Run against the branch under test to find v3-only usage that would need porting:

```bash
# v3-incompatible attribute usage in test sources
git grep -l "AutoFixture.Xunit3\|\[AutoData\|InlineAutoData\|AutoMoqData\|MemberAutoData" -- 'tests/**/*.cs'
# other v3-only APIs
git grep -l "TestContext\|Assert.Skip\|Assert.Multiple\|IAsyncLifetime\|Assert.Equivalent" -- 'tests/**/*.cs'
```

Each hit is a file to port in Step 3. **Zero/few hits → ~10-minute job, proceed.**
**Pervasive `[AutoData]` / AutoFixture.Xunit3 → stop** and tell the user this
approach isn't a good fit for their suite (porting would rewrite too many tests).

### Step 2 — Scaffold the shim project

Use the bundled script — it reads the real test `.csproj` and writes the shim
`.csproj` (mirroring every non-xunit `PackageReference` verbatim, swapping in the
xunit.v2 stack, setting `RootNamespace`/`AssemblyName`, adding the linked-`Compile`
glob and the product `ProjectReference`) plus a `stryker-config.json`:

```bash
python3 scripts/generate_shim.py tests/<TestProject>/<TestProject>.csproj \
  --mutate-exclude '**/gRPC/**/*.cs' --mutate-exclude '**/Caching/**/*.cs'
```

It creates `tests/<TestProject>.Mutation/` beside the real project. Pass
`--mutate-exclude` for each product folder that's genuinely out of mutation scope
(generated code, gRPC stubs, etc.); omit if none.

Why these choices matter, so you can fix the file by hand if the script's
heuristics miss something in an unusual `.csproj`:

- **`RootNamespace` must equal the real project's root namespace** — the linked
  sources resolve the same types, so a mismatch breaks compilation.
- **`AssemblyName` must differ** (`.Mutation`) so both projects coexist.
- **Non-xunit package versions must match exactly** — a version drift causes
  compile errors in the linked sources.
- **Keep the shim out of the `.sln`** (see Step 4 — this is what forces project
  mode). Do not `dotnet sln add` it.

### Step 3 — Port v3-only constructs (only files Step 1 flagged)

Rewrite v3-only APIs to behavior-equivalent v2-compatible forms, **in the real
test project's sources** (the shim links those same files, so one edit satisfies
both). Verify each replacement still compiles under v3 too.

| v3-only | v2-compatible replacement |
|---|---|
| `TestContext.Current.CancellationToken` | `CancellationToken.None` (token was never cancelled for a passing test) |
| `[AutoData]` / `[InlineAutoData]` | manual `new Fixture()` in the body, or `[Theory]` + `[InlineData]` — heavier; avoid the shim if pervasive |
| `Assert.Skip(...)` | `[Fact(Skip="…")]` or a guard-and-return |

### Step 3a — Grant internals access

If the product exposes internals to the real test assembly via
`InternalsVisibleTo`, add the shim assembly too (its tests exercise `internal`
types):

```csharp
[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("<TestProject>.Mutation")]
```

### Step 4 — Run Stryker FROM the shim directory (the critical part)

```bash
cd tests/<TestProject>.Mutation
dotnet-stryker
```

**This directory choice is the whole game.** A bare `dotnet-stryker` at repo root
auto-detects the single `.sln`, enters **solution mode**, ignores test-project
selection, and binds to the real xunit.v3 project → false ~0%. Running from a
directory with **no `.sln`** forces **project mode**: Stryker uses the shim in the
cwd and finds the product through its `ProjectReference`. The `stryker-config.json`
the script wrote (with `coverage-analysis: perTest` and `additional-timeout:
30000`) lives beside the shim; perTest mode is required for kill observation and
the raised timeout keeps slow mutants from being scored as timeouts.

### Step 5 — Validate BEFORE the full run

A full run can take hours; a wrong harness wastes all of it. Two gates:

1. **Green baseline** — the shim builds and every test passes:
   ```bash
   dotnet build tests/<TestProject>.Mutation -c Release
   dotnet test  tests/<TestProject>.Mutation -c Release --no-build
   # expect the SAME test count as the real project, 0 failed
   ```
2. **Kills register** — temporarily scope `mutate` to one small, well-covered file
   and run Stryker from the shim dir. Expect a **non-zero** score with real kills.
   If this scoped run is still ~0%, the harness is wrong — **do not launch the full
   run**; recheck the directory (Step 4) and the shim references.

### Step 6 — Launch the full run, then sanity-check

Widen `mutate` back to the full scope and launch. A full Stryker run is
long-running — start it in the background and watch it (a Monitor plus a periodic
status check), rather than blocking on it.

Before recording any score, **reject the observation-failure signature**: a
near-zero score with almost everything *Survived* means it bound to the v3 project
again — rerun from the shim dir. A healthy run kills the majority of covered
mutants. Output lands at
`StrykerOutput/<timestamp>/reports/mutation-report.{html,json}`.

## Teardown

The shim, its `stryker-config.json`, the `InternalsVisibleTo` line, and any v3→v2
source ports are **measurement scaffolding**. If you were measuring a throwaway
branch/worktree, discard it. If the shim lives in the repo, keep it **out of the
`.sln` and out of CI test discovery** so it never runs as a normal suite and never
double-counts.
