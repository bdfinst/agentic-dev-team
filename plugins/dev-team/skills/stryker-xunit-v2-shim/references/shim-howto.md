# Building a xunit.v2 Stryker shim for a xunit.v3 test project

How to make Stryker.NET produce a valid mutation score for a project whose real
test suite is **xunit.v3**. This is the full reference behind the
`stryker-xunit-v2-shim` skill; read it when an edge case isn't covered by
`SKILL.md`.

---

## 1. Why the shim exists

Stryker.NET (through at least 4.15/4.16) **cannot observe mutant kills through
xunit.v3.** xunit.v3 runs on the Microsoft Testing Platform (MTP), and Stryker's
per-test coverage/kill mapping does not work across it (stryker-net issues
3237, 3629, 3094). Symptom: the run completes but nearly every mutant is reported
*Survived*, e.g. **0.13% (3 killed / 7,685 survived)** — the *observation-failure
signature*. The initial test run passes and coverage filters even fire, so the
failure is silent unless you sanity-check the score.

The fix is a **shim**: a second test project that recompiles the *same test
source files* under **xunit.v2** (classic VSTest), which Stryker observes
correctly. No test is rewritten — the shim links the existing `.cs` files.

**Precondition that makes this cheap:** the test sources must be
source-compatible with xunit.v2. `[Fact]`, `[Theory]`, `[InlineData]`,
`TheoryData<>`, `MemberData`, `ClassData`, and `Assert.*` are all source-identical
between v2 and v3. Only genuinely v3-only constructs need porting (see step 4).
AutoFixture.Xunit3 `[AutoData]`/`[InlineAutoData]` attributes are **not**
v2-compatible; if the suite uses them heavily, this approach needs more work.

---

## 2. When to build / use it

Trigger conditions (all true):

- The target test project references `xunit.v3` (check its `.csproj`).
- You need a Stryker mutation score for it.
- The test sources are mostly plain xunit (grep confirms few/no `[AutoData]`,
  `AutoFixture.Xunit3`, `TestContext`, `Assert.Skip`, `Assert.Multiple`,
  `IAsyncLifetime` usages).

Quick scope probe (run against the branch under test):

```bash
# v3-incompatible attribute usage in test .cs sources
git grep -l "AutoFixture.Xunit3\|\[AutoData\|InlineAutoData\|AutoMoqData\|MemberAutoData" -- 'tests/**/*.cs'
# other v3-only APIs
git grep -l "TestContext\|Assert.Skip\|Assert.Multiple\|IAsyncLifetime\|Assert.Equivalent" -- 'tests/**/*.cs'
```

Each hit is a file the operator gate asks about. Zero hits → this is a ~10-minute
unattended job.

### 2a. The operator gate, recorded (#1791)

Any hit means the operator picks between `port`, `exclude`, `skip`, and
`degrade`, and `stryker_xunit_shim_guard.py` blocks every `dotnet-stryker` run
against that project until the choice is recorded. The guard's block body prints
the classified breakdown, the four tradeoffs, and the exact command to run —
including the fingerprint of *this* blocker set. Its shape:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" \
   "$CLAUDE_PLUGIN_ROOT/hooks/lib/xunit_v3_operator_gate.py" record \
   --project <TestProject> --choice exclude --fingerprint <from-the-block-body>
```

Prefer the command the guard printed (absolute paths, correct fingerprint) over
retyping this. `--fingerprint` is what scopes a decision to the blockers the
operator actually saw: omit it and the choice silently covers blockers added
later; reuse a stale one and the gate re-asks. Add `--file <path>` per flagged
file and `--note "<why>"` to leave the rationale in the record. `check --project
<TestProject>` prints the stored decision and exits non-zero when there is none.

Recorded decisions live in `.claude/metrics/xunit-v3-shim-decisions.json`
(override with `DEV_TEAM_XUNIT3_SHIM_DECISION_FILE`).

---

## 3. Build the shim project

Create `tests/<TestProject>.Mutation/<TestProject>.Mutation.csproj` next to the
real test project. It has **no `.cs` of its own** — it links the real project's
sources. (The bundled [`generate_shim.py`](../scripts/generate_shim.py) writes this
for you; the template below is what it emits and what to hand-fix for an unusual
`.csproj`.)

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <!-- xunit.v2 shim of <TestProject> for Stryker.NET.
       Delete once stryker-net fixes MTP mutation observation
       (issues 3237, 3629, 3094). -->

  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>          <!-- match the test project's TFM -->
    <IsPackable>false</IsPackable>
    <RootNamespace><TestProject></RootNamespace>        <!-- SAME namespace as the real project -->
    <AssemblyName><TestProject>.Mutation</AssemblyName> <!-- distinct assembly name -->
    <CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>
    <NoWarn>$(NoWarn);IDE0028;RCS1163;CS8032;NU1701</NoWarn>
    <GenerateProgramFile>true</GenerateProgramFile>
  </PropertyGroup>

  <ItemGroup>
    <!-- Mirror EVERY non-xunit package from the real test project at the SAME
         versions (AutoFixture, Moq, assertion lib, Grpc.Core.Testing, any
         private/internal deps). Swap the xunit stack for v2: -->
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />
    <PackageReference Include="xunit" Version="2.9.2" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2">
      <PrivateAssets>all</PrivateAssets>
      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
    </PackageReference>
    <!-- Do NOT reference xunit.v3 or AutoFixture.Xunit3 here. -->
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\..\src\<Product>\<Product>.csproj" />
  </ItemGroup>

  <ItemGroup>
    <!-- Link the real test project's sources; exclude build output. -->
    <Compile Include="..\<TestProject>\**\*.cs"
             Exclude="..\<TestProject>\obj\**\*.cs;..\<TestProject>\bin\**\*.cs">
      <Link>Linked\%(RecursiveDir)%(FileName)%(Extension)</Link>
    </Compile>
  </ItemGroup>

</Project>
```

Key points:

- **`RootNamespace` must equal the real project's root namespace** so linked
  sources resolve the same types.
- **`AssemblyName` must differ** (`.Mutation`) so both projects can coexist.
- **Mirror non-xunit package versions exactly** — a version drift causes compile
  errors in the linked sources.
- Do **not** add the shim to the `.sln` (see step 5 for why).

### 3a. Grant internals access

If the product uses `InternalsVisibleTo` for the real test assembly, add the shim
assembly too (the shim tests exercise `internal` types):

```csharp
[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("<TestProject>.Mutation")]
```

---

## 4. Port v3-only constructs (only the files step 2 flagged)

Rewrite v3-only APIs to v2-compatible, behavior-equivalent forms. Common cases:

| v3-only | v2-compatible replacement | Notes |
|---|---|---|
| `TestContext.Current.CancellationToken` | `CancellationToken.None` | Equivalent for passing tests; the token was never cancelled |
| `[AutoData]` / `[InlineAutoData]` (AutoFixture.Xunit3) | manual `new Fixture()` in the test body, or convert to `[Fact]`/`[Theory]+[InlineData]` | Heavier; avoid this shim if pervasive |
| `Assert.Skip(...)` | `[Fact(Skip="…")]` or guard-and-return | |

Port **in the real test project's source** — the shim links those same files, so
one edit satisfies both. Verify the replacement still compiles under v3 too
(`CancellationToken.None` does).

---

## 5. Invoke Stryker against the shim (the critical part)

**Run `dotnet-stryker` FROM the shim's project directory**, with a
`stryker-config.json` beside it:

```bash
cd tests/<TestProject>.Mutation
dotnet-stryker
```

Why this and not a bare run at repo root:

- The repo root has a single `.sln` that does **not** contain the shim. A bare
  `dotnet-stryker` at root **auto-detects the `.sln`, enters solution mode,
  ignores `test-projects`, and binds to the real xunit.v3 project** → false ~0%.
- Running from a directory with **no `.sln`** forces **project mode**: Stryker
  uses the test project in the cwd (the shim) and finds the product via its
  `ProjectReference`.

`stryker-config.json` (place in the shim directory):

```json
{
  "stryker-config": {
    "mutate": ["**/*.cs", "!obj/**/*.cs", "!**/gRPC/**/*.cs", "!**/Caching/**/*.cs"],
    "mutation-level": "Standard",
    "coverage-analysis": "perTest",
    "additional-timeout": 30000,
    "target-framework": "net10.0",
    "reporters": ["html", "json", "progress"],
    "thresholds": { "high": 80, "low": 60, "break": 0 }
  }
}
```

(Adjust the `mutate` excludes to the product's own out-of-scope folders.)

---

## 6. Validate BEFORE the full run

A full run can take hours; a wrong harness wastes all of it. Two gates:

1. **Green baseline** — the shim must build and all tests pass:
   ```bash
   dotnet build tests/<TestProject>.Mutation/<TestProject>.Mutation.csproj -c Release
   dotnet test  tests/<TestProject>.Mutation/<TestProject>.Mutation.csproj -c Release --no-build
   # expect the same test count as the real project, 0 failed
   ```
2. **Kills register** — scope `mutate` to one small, well-covered file and run
   Stryker from the shim dir. Expect a *non-zero* score with real kills:
   ```json
   { "stryker-config": { "mutate": ["**/Extensions/DecimalExtensions.cs"],
       "coverage-analysis": "perTest", "reporters": ["json","progress"] } }
   ```
   A healthy scoped run produces real kills (e.g. **5 killed / 4 survived →
   55.56%**) — proof observation works. If this scoped run shows ~0%, the harness
   is still wrong; do **not** launch the full run.

Then widen `mutate` to the full scope and launch the full run in the background,
with periodic status monitoring rather than blocking on it.

---

## 7. Sanity-check the result

Before recording any score, reject the observation-failure signature: a
near-zero score with almost everything *Survived* means the run bound to the v3
project — rerun from the shim dir. A healthy run kills the majority of covered
mutants (a real example from this technique: **57.44%**, 4,419 killed / 2,209
survived / 1 timeout of 6,629 tested).

Output lives at `StrykerOutput/<timestamp>/reports/mutation-report.{html,json}`.

---

## 8. Teardown

The shim, its `stryker-config.json`, the `InternalsVisibleTo` line, and any v3→v2
source ports are **measurement scaffolding**. If measuring a branch you won't
merge (e.g. a worktree baseline), discard the worktree. If the shim is meant to
live in the repo, keep it out of the `.sln` and out of CI test discovery so it
isn't run as a normal suite.
