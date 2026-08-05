# Multi-project coverage discovery — implementation detail

`coverage-baseline`'s Step 1a (.NET `.sln` / JS-TS workspace / Java
multi-module rows) and Step 5 (persist), and `coverage-delta`'s Step 2, are
the **contract surface**: when a `.sln` is present (.NET), a workspace signal
is present (JS/TS), or a multi-module signal is present (Java),
discovery runs fresh every call, bootstraps or drift-checks
`coverage-config.json` against it, and — on success — weighted-merges the
included projects'/packages' coverage into one number. The contract surface
owns the script names, the hard-failure rule, the schema keys, and the exact
message templates because that is what reviewers and tests depend on; this
file holds the mechanics — mirroring the
`../../coverage-delta/references/mutation-gate.md` precedent (issue #1759).

Every function named below lives in `${CLAUDE_PLUGIN_ROOT}/scripts/`:
`coverage_config.py` (shared: bootstrap, drift-check, weighted merge,
measurement-basis notice, and the `read_and_screen_xml` entity-expansion
screen every XML-parsing stack routes through), `coverage_discovery_dotnet.py`
(.NET), `coverage_discovery_js.py` (JS/TS), `coverage_discovery_java.py`
(Java: Maven + Gradle).

## 1. Discovery step (stack-specific; everything after this is shared)

| Stack | Trigger | Call |
| --- | --- | --- |
| .NET | a `.sln` file exists at the repo root | `${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_dotnet.py`'s `discover_dotnet_projects(repo_root)` |
| JS/TS | root `package.json#workspaces`, or `pnpm-workspace.yaml`, or `lerna.json` is present | `${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_js.py`'s `discover_js_packages(repo_root)` |
| Java | root `pom.xml` declares `<modules>` (Maven), or `settings.gradle`/`settings.gradle.kts` declares `include(...)` (Gradle). Maven wins when both are present — no cross-merge | `${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_java.py`'s `discover_java_modules(repo_root)` |

Both return one of three shapes:

- A list of `{"path": <opaque identity string>, "classification":
  TestClassification}` entries on success. `path` is the exact,
  unmodified string the discovery function produced — never
  normalized, case-folded, or separator-translated when later matched
  against `included`/`excluded` (`coverage_config`'s identity contract).
- `coverage_config.DISCOVERY_NOT_APPLICABLE` — no `.sln` / no workspace
  signal / no multi-module signal. The repo is single-project for this stack; neither discovery nor
  any of the steps below run. See `SKILL.md` Step 1b.
- `coverage_config.discovery_error(message)` — a tooling/parsing failure
  (`dotnet` missing, a malformed `.csproj`, an unsupported
  `pnpm-workspace.yaml` shape, etc.). Treat this exactly like an existing
  Step 3 ("Run coverage") failure: surface `message`, write no baseline,
  stop. This is a genuine tool failure, not the actionable config gap the
  hard-failure block below describes — it deliberately reuses Step 3's
  existing failure *behavior*, not a third failure shape.

## 2. Zero-real-test-project check

Before touching `coverage-config.json` at all, check whether **any**
discovered entry needs accounting:

```python
any(coverage_config.needs_accounting(entry["classification"]) for entry in discovered)
```

If this is `False` — every discovered project/package classified
`NOT_TEST` — stop immediately with the exact message (never write
`coverage-config.json` or `baseline-coverage.json` on this path):

```
Coverage capture stopped: no real test project was discovered in this <solution|workspace|multi-module build> — cannot establish a coverage floor. If this repo has test projects, verify they reference Microsoft.NET.Test.Sdk (for .NET), use jest/vitest/mocha+nyc/c8 (for JS/TS), or declare a JUnit/TestNG dependency alongside a src/test/java|kotlin directory (for Java) so discovery can recognize them; otherwise there is no coverage floor to capture.
```

`<solution|workspace>` resolves to `solution` for .NET, `workspace` for
JS/TS. This is a diagnosable message, not a silent empty baseline: it names
the exact markers discovery recognizes for both stacks, so a repo whose
tests use an unrecognized runner gets an actionable next step instead of a
gap that looks like "no tests exist."

## 3. Bootstrap / drift-check step

```python
config, notice = coverage_config.load_or_bootstrap(config_path, discovered, now_iso)
```

- **Config absent (or malformed)** — bootstrapped fresh from `discovered`
  (every accounted-for entry `included`, zero `excluded`, tagged
  `bootstrapped_at`). Print `notice` verbatim. This call never touches any
  existing `baseline-coverage.json` — the previously-captured value, if
  any, is left exactly as it was.
- **Config present** — read back verbatim, unmodified. `notice` is `None`.

Then, always:

```python
drift = coverage_config.drift_check(config, discovered)
```

- `drift["hard_failure"]` `True` (an unaccounted-for or conflicting
  project) — print `drift["hard_failure_message"]` **verbatim, as its own
  distinct, named block** headed `Coverage capture stopped:`. **Never**
  fold this into or reuse Step 3's "Run coverage" failure wording
  (`Surface the first error.` / `Do NOT write a baseline. The floor must
  be a true measurement.`) — this failure class has a concrete,
  actionable fix (edit `coverage-config.json`) that Step 3's generic
  wording doesn't carry, and the two message bodies are textually
  distinct by construction (`drift_check`'s messages always open with
  `Coverage capture stopped: <N> discovered project(s)...` or `...are
  listed in both...`, never Step 3's phrasing). Stop; write no baseline.
- `drift["hard_failure"]` `False` — proceed to the merge step below.
  `drift["stale_warning_message"]`, when non-`None`, is a non-blocking
  signal (excluded entries that no longer match discovery) —
  `coverage-baseline` does not print it (that is `coverage-delta`'s job,
  which re-derives discovery on every later call and surfaces staleness
  there); `coverage-baseline` only needs the `hard_failure` branch above.

## 4. Weighted-merge step

For each path in `config["included"]`, run the stack's coverage command
**per included project/package** (never once for the whole repo), and parse
its raw `{covered_statements, total_statements, covered_branches,
total_branches}` from that report. For JS/TS, this extends Step 4's existing
per-tool parsing table (Istanbul's `coverage-final.json`/`lcov.info`, etc.) to
the raw counts those reports already carry, not only the derived percentage.

**Known, documented limitation (.NET/Coverlet).** Step 4's Coverlet row
documents only the derived `summary.linecoverage`/`summary.branchcoverage`
percentages — not the raw counts `weighted_merge` requires. Coverlet's raw
JSON layout (nested per-module/per-class/per-method hit data) needs
verification against a real Coverlet run before this repo can document an
exact JSON path to sum with confidence; asserting one without running the
real tool risks documenting a shape that doesn't match Coverlet's actual
output. Until that verification happens, multi-project .NET merge requires
the operator's own coverage command wrapper to parse and supply the four raw
counts per included project. If a per-project report carries only
percentages with no raw counts, **stop** with a
`coverage_config.discovery_error(...)` naming the project and the missing
raw counts — never silently degrade to a `null`/`0` baseline by feeding
`weighted_merge` an incomplete report. See `SKILL.md` Step 1a item 4 for the
exact stop message.

Feed the collected per-project reports to:

```python
merged = coverage_config.weighted_merge(project_reports)
# {"line_pct": <float|None>, "branch_pct": <float|None>}
```

`weighted_merge` sums covered/total across every included project **before**
dividing — never a per-project average — so a large, well-covered project
and a small, poorly-covered one merge to the size-weighted percentage, not
the midpoint of the two percentages. `merged` is Step 4/5's baseline
`line_pct`/`branch_pct`.

## 5. Persist step

`baseline-coverage.json` is written exactly as Step 5 already documents
(temp-file-then-rename), using `merged`'s `line_pct`/`branch_pct`.

Additionally, for a multi-project repo, persist
`.dev-team-reports/<workflow>/<slug>/data/coverage-config.json` — `config`
from step 3 above — via `coverage_config.atomic_write_json(config_path,
config)`, the identical temp-file-then-rename idiom. Single-project repos
(Step 1b) skip this write entirely — no `coverage_config.py` function is
ever called for them, and no `coverage-config.json` file appears in their
`data/` directory.

## Single-project and mixed-stack repos are unaffected

A `.csproj` repo with no `.sln`, or a `package.json` with no workspace
signal, never reaches any function in this file — Step 1's existing
single-command path runs exactly as it did before this feature existed.

A repo with **both** a `.sln` and a workspace-configured `package.json` is
out of scope: `coverage-baseline`'s existing manifest table resolves to a
single tool via first-match order, unchanged by this feature. No function
in this file is ever called for the losing stack, and no cross-stack merge
is introduced.

## Adding a fourth stack

Each stack gets its own `coverage_discovery_<stack>.py` implementing
`discover_<stack>_<units>(repo_root)` against the three return shapes in §1.
Deliberately **not** a strategy/registry abstraction: the stacks share only
leaf helpers (the result signals, `TestClassification`, the XML screen), while
enumeration, trigger precedence, the classification predicate, and the identity
string all differ per stack by design. A new stack reuses the shared leaf
helpers in `coverage_config.py` rather than re-implementing them — the Java
stack shipped its first revision without the entity-expansion screen the .NET
stack already had, which is the drift a shared helper exists to prevent.

Two rules every stack follows, learned from #1759 and #1765:

- **A declared-but-unusable build graph is a `discovery_error`, never a
  classification.** A missing module directory, a declared-but-empty module
  list, or a settings file with no recognizable declaration must fail loudly:
  classifying it `NOT_TEST` makes `needs_accounting` false and drops it from
  operator accounting silently. (Stack-specific judgement still applies to what
  counts as unusable — a Maven `<module>` with no POM is broken because `mvn`
  itself fails on it, while a Gradle subproject directory with no build file is
  a legitimate container project.)
- **An inherited or conditional marker is `AMBIGUOUS`, never `TEST` and never
  `NOT_TEST`.** Discovery never evaluates inheritance (an MSBuild `Condition`,
  a parent POM's `<dependencyManagement>`, a Gradle `subprojects {}` block, a
  BOM version pin); it reports the ambiguity and lets `drift_check` force an
  operator decision.
