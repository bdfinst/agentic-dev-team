# Multi-project coverage discovery — implementation detail

`/coverage-baseline` Step 1's `.sln`/`.csproj` row and its JS/TS-manifest row are the **contract surface**: when a multi-project signal is present, they discover every real test project/package fresh, reconcile it against `coverage-config.json`, and merge the per-project coverage into one weighted percentage. This file holds the mechanics both rows point to, so the SKILL.md stays a thin orchestrator. `/coverage-delta` links here too — it re-runs the *same* discovery every call rather than reading a frozen list.

Root cause this exists for (#1759): a hand-picked project exclusion, recorded once in prose notes and never re-checked, accumulated real assertions after its exclusion. A branch-coverage delta was underreported ~30x and a real line-coverage delta reported as zero. Nothing here holds a frozen project list.

## When discovery runs at all

Discovery activates only when a stack's multi-project signal is actually present. Otherwise the existing single-command path is untouched — no discovery call, no `coverage-config.json` written.

| Stack | Signal | No signal |
| --- | --- | --- |
| .NET | a `*.sln` at the repo root | a single `.csproj` keeps today's single command |
| JS/TS | root `package.json` has a `workspaces` field, **or** `pnpm-workspace.yaml`/`pnpm-workspace.yml` exists, **or** `lerna.json` exists | a single `package.json` keeps today's single command |

Both discovery scripts report this as `{"applicable": false, "projects": []}` and exit 0. A **mixed-stack** repo (a `.sln` *and* a workspace `package.json`) runs each stack's discovery independently for whichever signals are present; Step 1's existing first-match-wins manifest selection is unchanged.

Java/Gradle/Maven multi-module generalization is deliberately out of scope — tracked as issue #1765.

## Structural markers

Classification is by structural marker only. There is no path filter, no naming convention, and no hand-maintained list.

**`.NET`** — `scripts/coverage_discovery_dotnet.py`, driven by `dotnet sln <sln> list`:

| Marker state | Classification |
| --- | --- |
| inline `Microsoft.NET.Test.Sdk` `PackageReference` in the project file | `TEST` |
| no inline reference, but an **unconditioned** reference in an ancestor `Directory.Build.props` or `Directory.Build.targets` (up to and including the solution directory) | `TEST` |
| the only reference found is **conditioned** (`Condition` on the reference or an ancestor element) | `AMBIGUOUS` |
| no reference anywhere | `NOT_TEST` |

The project XML is parsed, so attribute order is irrelevant, a version-less Central Package Management form counts, a `Microsoft.NET.Test.Sdk.Extras`-style lookalike does not, and a commented-out reference does not. Package IDs match case-insensitively and a semicolon item list (`Include="xunit;Microsoft.NET.Test.Sdk"`) counts, because MSBuild expands both.

Discovered project paths are recorded exactly as `dotnet sln list` printed them, including Windows backslashes; a separator-normalized copy is used for filesystem reads only, so a Windows-authored solution still classifies on POSIX. Quote the path when interpolating it into a `dotnet test` command — `src/My Project/My Project.csproj` is an ordinary layout, and rejecting spaces would reject valid solutions.

**JS/TS** — `scripts/coverage_discovery_js.py`, driven by resolving the declared workspace globs against the filesystem (no package-manager CLI is invoked, so discovery does not depend on npm/yarn/pnpm being installed or configured correctly):

| Marker state | Classification |
| --- | --- |
| a non-placeholder `test` script **and** a coverage-capable runner (`jest`, `vitest`, or `mocha`/`ava` paired with `nyc`/`c8`) | `TEST` |
| anything less | `NOT_TEST` |

`npm init`'s `echo "Error: no test specified" && exit 1` placeholder is not a test script, but a real one that merely *starts* with an `echo` (`echo linting && jest --coverage || exit 1`) is. `@types/jest` and `eslint-plugin-jest` are not the runner. Both `devDependencies` and `dependencies` are read — a runner misplaced in `dependencies` is never a reason to leave a real test package out of coverage.

Glob resolution matches what npm/yarn/pnpm enumerate, not raw `pathlib` semantics: brace alternations (`apps/{web,api}`) are expanded, `!` negations apply as global ignores regardless of order, `node_modules` matches are dropped, and a `*` wildcard does not match leading-dot directories (though a pattern that explicitly names one, like `.internal/*`, is honoured). A symlinked workspace keeps the identity the glob matched rather than its target's. An unbalanced brace is a hard failure, because it would otherwise match nothing silently.

There is no `AMBIGUOUS` state for JS/TS: unlike MSBuild's conditioned references, a manifest carries no build condition discovery would have to decline to evaluate.

## Why `AMBIGUOUS` is never a silent negative

Build conditions are never evaluated. A marker discovery cannot resolve mechanically becomes `AMBIGUOUS` and must reach a human, because the alternative — treating it as `NOT_TEST` — is exactly the silent omission that caused #1759. `AMBIGUOUS` needs accounting in `coverage-config.json` just like `TEST` does, and its hard-failure message is deliberately worded differently so an operator can tell "we know this is a test project" from "we could not decide".

## `coverage-config.json`

Written to `.dev-team-reports/<workflow>/<slug>/data/coverage-config.json`, alongside `baseline-coverage.json`, with the same temp-file-then-rename atomic write. One stack-agnostic schema serves both stacks:

```json
{
  "included": ["<project-or-package-path>"],
  "excluded": [{ "path": "<project-or-package-path>", "reason": "<human-readable>" }],
  "bootstrapped_at": "2026-08-04T12:00:00Z"
}
```

**Path identity is an exact, unmodified string match.** Each stack records paths in its own native form — .NET exactly as `dotnet sln list` printed them, JS/TS as repo-relative forward-slash paths — and there is deliberately no cross-stack normalization, so a normalization bug can never make an unaccounted-for project look accounted for.

### Bootstrap

An **absent** config bootstraps from the fresh discovery pass: every project needing accounting goes into `included`, `excluded` is empty, `bootstrapped_at` records when. This is what keeps a workflow that already has a `baseline-coverage.json` from hard-failing the moment this ships. Print the returned operator notice; it names the config path and how many projects were included.

An **unreadable** config — bad JSON, or valid JSON that does not carry this feature's keys — is treated as absent and re-bootstrapped, matching Step 2's established "malformed tracked artifact → capture fresh" convention. Its notice additionally names the shape problem, because re-bootstrapping discards whatever exclusion reasons the unreadable file held.

A **valid** config is never overwritten. A human's recorded exclusions and reasons survive every run.

### Drift check

| Condition | Severity |
| --- | --- |
| a discovered `TEST` project in neither `included` nor `excluded` | hard failure |
| a discovered `AMBIGUOUS` project in neither list | hard failure, distinct message |
| a path in both `included` and `excluded` | hard failure |
| an `excluded` entry with no reason recorded | hard failure |
| an `excluded` entry matching no discovered project | **warning**, non-blocking, named in run output |

Every hard failure means: stop, write no baseline, print the message. The stale-exclusion warning is what keeps an exclusion questionable by a human every run; the check deliberately does not try to decide whether a *reason* has gone stale, which needs judgement a mechanical check cannot make (stated non-goal).

## Weighted merge

Run coverage per `included` project, then merge the per-project percentages **weighted by each project's total statement/branch count**. Never a simple average: a 10-statement project at 100% and a 1000-statement project at 50% merge to ~50.5%, not 75%. That gap is the #1759 incident in miniature.

Each dimension is weighted independently. A project that did not measure branches is excluded from the branch weighting only, so one branchless project cannot drag the merged branch number toward zero. The reported `statements_total`/`branches_total` are the **denominators of the reported percentages**, so a consumer can reconstruct covered counts as `pct * total / 100` without over-counting.

Per-stack inputs to the merge:

- **.NET** — each project's Coverlet `coverage.json` (`summary.linecoverage`, `summary.branchcoverage`) plus its statement/branch totals.
- **JS/TS** — each package's `coverage/coverage-summary.json` (`total.lines`, `total.branches`), or Step 4's existing Istanbul fallback chain applied **per package**.

Zero merged projects is a hard failure, never a `null` baseline: "no test projects were included" must not be persisted as a measurement.

## Measurement-basis notice

When a `baseline-coverage.json`'s `captured_at` predates the config's `bootstrapped_at`, that baseline may reflect a single project rather than the full merged set, so a delta against it is not comparable. Surface the notice and recommend re-capturing. Timestamps are compared as instants using one pinned shared ISO-8601 format (`%Y-%m-%dT%H:%M:%SZ`), never as strings.

## Known limitations

- **.NET `Directory.Packages.props`** — the `GlobalPackageReference` mechanism is not walked. A solution supplying the test SDK exclusively that way classifies `NOT_TEST`. Documented in epic #1766's Risks section, out of scope for this slice.
- **`<Import Project="…" />` inside a `Directory.Build.*` file** is not followed, so a marker declared only in an imported file is not seen.
- **The `.sln` search is root-only, not recursive.** A repo whose solution lives at `src/App.sln` passes it explicitly via `--solution`; recursing would make the measured set depend on directory layout and would pick up nested sample/fixture solutions.
- **More than one `.sln`** at the repo root is a hard failure naming them all rather than a sort-order pick; pass the one to measure explicitly.
- **`pnpm-workspace.yaml`** is read by a minimal, documented-shape-only parser: a `packages:` key (quoted or bare, declared once) followed by a block sequence of quoted or bare scalars, at any indentation including zero. A syntactically-valid-but-unsupported shape (flow-style array, nested mapping, block scalar, anchor/alias, a duplicated `packages:` key) is a discovery error, explicitly **not** a not-applicable signal and **not** a silent empty list.
- **A `**` workspace pattern still walks `node_modules`** before matches are filtered out; correct, but not free on a repo with dependencies installed.
- **Exclusion rationale staleness** is not auto-detected — only the exclusion's continued existence is re-surfaced.

## Superseded

`../scripts/discover_coverage_projects.py` was #1759's .NET-only first fix. Its structural marker and path-safety rules carry forward into `scripts/coverage_discovery_dotnet.py`, but its config schema (`known_projects`/`exclusions`, stored next to the `.sln`) is **not** this feature's schema. `/coverage-delta` still invokes the older script until its own slice lands; until then the two workers reconcile against different files, and only `/coverage-baseline`'s number reflects the weighted merge.
