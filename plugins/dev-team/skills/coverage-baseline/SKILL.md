---
name: coverage-baseline
description: >-
  Multi-workflow coverage baseline worker. Detects the repo's coverage tool
  from its build manifest, runs it, records the resulting line+branch
  percentages as the baseline, and posts the number to the parent issue (or
  local `FEATURE.md`). This number is the floor every later phase must improve
  on. Called by `/test-improve` (Phase 2) via `--workflow test-improve`.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Coverage Baseline

Role: worker. Captures the true baseline coverage of the repo *after* cannot-fail tests have been disabled so the floor isn't inflated by tautologies.

You have been invoked with the `/coverage-baseline` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>`.
- `--parent <issue-url>` — parent issue URL on the resolved tracker (or empty for local-files mode).
- `--repo-slug <slug>` — namespace under `.claude/memory/<workflow>/`.
- `--workflow <name>` — the workflow namespace under `.claude/memory/`. Defaults to `test-improve`. Orchestrators pass their own namespace (e.g. `/test-improve` passes `test-improve` for its Phase-2 baseline).

If `<repo-path>` is absent, ask the operator.

## Steps

### 1. Detect the coverage tool

Read the build manifest at the repo root and pick the appropriate command:

| Manifest | Default coverage command |
|---|---|
| `package.json` (JS/TS) | `npm test -- --coverage` (or `pnpm test --coverage`, `yarn test --coverage`) — or, when a workspace signal is present (a root `workspaces` field, `pnpm-workspace.yaml`, or `lerna.json`), multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions-jsts-workspaces--java-multi-module-builds)) |
| `pyproject.toml` / `setup.py` | `pytest --cov=. --cov-report=json` |
| `pom.xml` | `mvn test jacoco:report` — or, when the root `pom.xml` declares `<modules>`, multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions-jsts-workspaces--java-multi-module-builds)) |
| `build.gradle*` | `./gradlew test jacocoTestReport` — or, when `settings.gradle`/`settings.gradle.kts` declares `include(...)`, multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions-jsts-workspaces--java-multi-module-builds)) |
| `*.csproj` | `dotnet test /p:CollectCoverage=true /p:CoverletOutputFormat=json` — or, when a `.sln` is present at the repo root, multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions-jsts-workspaces--java-multi-module-builds)) |
| `Cargo.toml` | `cargo llvm-cov --json` |
| `go.mod` | `go test -coverprofile=coverage.out ./...` + `go tool cover -func=coverage.out` |

If the repo has its own coverage script (e.g. `npm run coverage`, `make coverage`), prefer that — detect via `package.json#scripts.coverage`, the `Makefile`, or a documented run target in `README.md`. If detection is ambiguous, ask the operator for the exact command. This override does not apply to the `.sln`/`.csproj`, `pom.xml`, or `build.gradle*` rows above — each of those rows' discovery scripts always re-derives the project/module list itself, per-run, regardless of any repo-level coverage script.

### 1a. Multi-project discovery (.NET solutions, JS/TS workspaces & Java multi-module builds)

Replaces the single frozen coverage command above for a multi-project .NET
solution, JS/TS workspace, or Java multi-module build — closing the gap where
a hand-picked,
never-revisited inclusion list caused a real coverage delta to be
underreported (issue #1759). **Implementation detail** — the discovery,
bootstrap/drift-check, weighted-merge, and persist mechanics below:
[`references/multi-project-discovery.md`](references/multi-project-discovery.md),
mirroring the `../coverage-delta/references/mutation-gate.md` precedent. This
section pins the contract surface (script names, the hard-failure rule, and
the exact message templates) that reviewers and tests depend on; the
reference file holds the mechanics. `coverage-delta`'s own Step 2 links to
the same reference file rather than re-deriving this a third time.

**.NET** — when a `.sln` file exists at the repo root, run
`${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_dotnet.py`'s
`discover_dotnet_projects(repo_root)` instead of the single `dotnet test`
command above. It returns every project in the solution, each classified
`TEST`, `AMBIGUOUS`, or `NOT_TEST` (`coverage_config.TestClassification`).

**JS/TS** — when the root `package.json` declares a `workspaces` field, or a
`pnpm-workspace.yaml`/`lerna.json` is present, run
`${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_js.py`'s
`discover_js_packages(repo_root)` instead of the single `npm test --
--coverage` command above. It returns every resolved workspace package, each
classified `TEST` or `NOT_TEST`.

**Java** — when a root `pom.xml` declares `<modules>` (Maven), or a
`settings.gradle`/`settings.gradle.kts` declares `include(...)` (Gradle), run
`${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_java.py`'s
`discover_java_modules(repo_root)` instead of the single `mvn test
jacoco:report` / `./gradlew test jacocoTestReport` command above. Maven takes
precedence when both signals are present (no cross-merge). It returns every
module in the build graph — recursively through Maven aggregator modules —
each classified `TEST`, `AMBIGUOUS`, or `NOT_TEST`. `TEST` requires BOTH a
`src/test/java`/`src/test/kotlin` directory AND a JUnit/TestNG dependency
declared on a test configuration in the module's OWN build file; a test-source
directory whose framework dependency is only inherited (a parent POM, a Gradle
`subprojects {}` block, a convention plugin) is `AMBIGUOUS`, never silently
`NOT_TEST`.

Any of the three discovery functions can return `coverage_config.DISCOVERY_NOT_APPLICABLE`
(no `.sln` / no workspace signal / no multi-module signal — see Step 1b below: the repo is
single-project and unaffected by anything in this section) or
`coverage_config.discovery_error(...)` for a tooling/parsing failure — treat
a `discovery_error` exactly like an existing Step 3 coverage-run failure
(surface the error, write no baseline, stop). That is a genuine tool
failure, not the actionable config gap the hard-failure block below
describes, so it stays on Step 3's existing path rather than growing a
third failure shape.

**Config path.** `coverage-config.json` is read from and written to the exact
resolved path `.dev-team-reports/<workflow>/<slug>/data/coverage-config.json`
— the SAME path Step 5 below persists it to, and the SAME path `coverage-delta`'s
Step 2a reads it from. There is no ambiguity: both skills operate on the
identical file.

When discovery returns a real project/package list, call, in this order:

1. **Zero-real-test-project check** — if no discovered entry needs
   accounting (`coverage_config.needs_accounting`) at all — every project
   classifies `NOT_TEST` — stop immediately, before touching
   `coverage-config.json` or `baseline-coverage.json`, with the exact
   message: `"Coverage capture stopped: no real test project was discovered
   in this <solution|workspace|multi-module build> — cannot establish a
   coverage floor. If this repo has test projects, verify they reference
   Microsoft.NET.Test.Sdk (for .NET), use jest/vitest/mocha+nyc/c8 (for
   JS/TS), or declare a JUnit/TestNG dependency alongside a
   src/test/java|kotlin directory (for Java) so discovery can recognize
   them; otherwise there is no coverage floor to capture."`
   (`<solution|workspace|multi-module build>` resolved to whichever stack
   applies).
   Write no baseline.
2. `coverage_config.load_or_bootstrap(config_path, discovered, now_iso)` —
   loads `coverage-config.json` if present (verbatim, unmodified), or
   bootstraps it (every accounted-for project `included`, zero `excluded`)
   if absent. On bootstrap, print the returned `notice` verbatim before
   proceeding — this call never touches any existing `baseline-coverage.json`.
3. `coverage_config.drift_check(config, discovered)`:
   - If it raises `ValueError` (a malformed-but-parseable `included`/
     `excluded` shape — e.g. present but not a list), print the
     exception's message **verbatim, as its own named block**, and stop
     without writing a baseline.
   - On `hard_failure` (an unaccounted-for or conflicting project), print
     `hard_failure_message` **verbatim, as its own distinct, named block**
     headed `Coverage capture stopped:` — **never** folded into or reusing
     Step 3's "Run coverage" failure wording (`Surface the first error.` /
     `Do NOT write a baseline. The floor must be a true measurement.`).
     This failure class has a concrete fix (edit `coverage-config.json` to
     add the named project to `included` or `excluded`) that Step 3's
     generic wording doesn't carry. Stop; write no baseline.
4. On success (`hard_failure` is `False`), run the stack's coverage command
   **per included project** (never once per repo), parse each project's
   report with `coverage_report_parse.parse(report_path)` (auto-detects the
   format — lcov, cobertura, clover, jacoco-csv, istanbul-summary,
   istanbul-final, coverage-py, or coverlet — and returns one
   `CoverageRecord` per source file), sum each project's records with
   `coverage_report_parse.aggregate(records)` into that project's single
   `CoverageRecord`, and call
   `coverage_config.weighted_merge(project_reports)` — passing the list of
   per-project `CoverageRecord`s directly, no dict translation needed — to
   produce the merged `line_pct`/`branch_pct` that Step 4/5 record as the
   baseline. This same shared parser is what `coverage_gap_ranking.py` uses
   for its per-module ranking, so there is one implementation of "what a
   coverage report means," not a second copy re-derived per run.

   **Check the result before using it.** `weighted_merge` returns either the
   merged `{"line_pct": ..., "branch_pct": ...}` dict, or the shared
   `discovery_error(...)` shape (`{"signal": "error", "message": ...}`) when
   any per-project report is missing a required raw count field —
   `weighted_merge` already validates report completeness internally, so
   there is no separate pre-validation step for the caller. Discriminate
   with `if "signal" in merged:` — on a hit, print `merged["message"]`
   verbatim and stop without writing a baseline; only proceed to Step 4/5
   when the `"signal"` key is absent.

### 1b. Single-project and mixed-stack repos are unaffected

A `.csproj` repo with no `.sln`, or a `package.json` with no workspace
signal (no `workspaces` field, no `pnpm-workspace.yaml`, no `lerna.json`),
takes the pre-existing single-command path from the table above completely
unchanged — no discovery call, and no `coverage-config.json` write, ever.

A repo containing **both** a `.sln` and a workspace-configured
`package.json` is explicitly **out of scope** for multi-project discovery:
the manifest table above already resolves to a single tool via first-match
order, unchanged by this feature — no new cross-stack merge behavior is
introduced, and neither discovery script runs for the other stack's files.

### 2. Existing-baseline guard

Check whether `.dev-team-reports/<workflow>/<slug>/data/baseline-coverage.json` already exists for the resolved slug. This existing-baseline guard is this worker's application of the shared existing-tracked-artifact re-capture guard — the canonical definition and rationale live once in `knowledge/decision-defaults.md`'s "Re-capture: keep vs. overwrite an existing tracked artifact" axis; this step cites that axis for the *why* and spells out the operational branches below so an executing agent doesn't need to open a second file mid-task to know what to do.

Applied here:

- **No existing file, or overwrite chosen** — proceed to Step 3 (Run coverage) and the rest of the normal flow.
- **Existing file, interactive session** — prompt keep/overwrite (default keep). An answer that is neither "keep" nor "overwrite" (case-insensitive) re-prompts with the identical choice — never falls back silently to either option, no retry limit, no timeout.
- **Existing file, non-interactive** (no usable TTY, or `DEV_TEAM_AUTO_APPROVE=1`) — keep the existing baseline automatically; both log the auto-decision and echo it to run output, not only record it to a file.
- **Existing file is malformed or corrupt** (fails to parse as JSON — e.g. left over from a prior interrupted write) — treat it as absent, never as a baseline to keep. Emit a warning naming why a fresh capture is happening, then proceed to Step 3.
- **On keep** — skip straight to Step 7 (Report). Reuse the existing file's `tool`, `line_pct`, and `branch_pct`, and report its `captured_at` instead of a freshly captured timestamp. Do not dispatch a coverage run.

### 3. Run coverage

Run the chosen command from `<repo-path>`. Capture stdout, stderr, and the exit code.

If the run fails:

- Surface the first error.
- Do NOT write a baseline. The floor must be a true measurement.
- Stop.

### 4. Parse line + branch percentages

**Only resolve the tool → report-file-path mapping by hand.** That part
genuinely needs human/agent judgment about where each tool writes its
output; the parsing itself does not — use the same shared parser Step 1a's
multi-project merge already calls, never a hand-rolled per-tool reader.

Resolve the report path for the detected tool:

- Istanbul / Jest / Vitest → `coverage/coverage-summary.json` (preferred).
  **If absent** (the `json-summary` reporter wasn't enabled — see #1086), do
  not abort. Fall back, in order, to whichever of these exists first:
  `coverage/coverage-final.json`, `coverage/lcov.info`,
  `coverage/clover.xml`. Note which report was used (`raw_report`) in the
  persisted baseline, and recommend the operator run `/setup` (which now
  checks coverage readiness) or add the `json-summary` reporter so future
  runs use the canonical summary.
- pytest-cov → `coverage.json`.
- JaCoCo → `target/site/jacoco/jacoco.csv`.
- Coverlet → `coverage.json` (the assembly → file → class → method JSON reporter).

Then parse it with the shared parser — same call, same vocabulary, as
Step 1a:

```python
records = coverage_report_parse.parse(report_path)  # auto-detects lcov,
                                                      # cobertura, clover,
                                                      # jacoco-csv,
                                                      # istanbul-summary,
                                                      # istanbul-final,
                                                      # coverage-py, or
                                                      # coverlet
total = coverage_report_parse.aggregate(records)     # one CoverageRecord
line_pct = 100 * total.covered_statements / total.total_statements
branch_pct = (
    100 * total.covered_branches / total.total_branches
    if total.total_branches
    else None
)
```

`coverage_report_parse.parse`/`aggregate` raise `ReportError` on an
unrecognized or unreadable report, and on a recognized format that parses to
zero records (a misdetected/malformed report, not a genuine 0% measurement)
— treat either exactly like an existing Step 3 coverage-run failure: surface
the error, write no baseline, stop.

**cargo-llvm-cov and Go are not covered by the shared parser** — both use
tool-specific output shapes (`cargo llvm-cov --json`'s own schema; `go tool
cover -func`'s plain-text summary) that `coverage_report_parse` does not
recognize, so these two keep their own hand-parsed rules rather than a
parser call that doesn't exist yet:

- cargo-llvm-cov → `--json` → `data[0].totals.lines.percent`, `…branches.percent`.
- Go → `go tool cover -func` → `total:` line; branch coverage isn't native, report `null` and flag.

### 5. Persist the baseline

Write `.dev-team-reports/<workflow>/<slug>/data/baseline-coverage.json` directly to tracked storage, via temp-file-then-rename (write to `<path>.tmp` then `mv -f <path>.tmp <path>`) — never a direct, non-atomic write. "Tracked" depends on the resolved `<workflow>` having a matching `.gitignore` re-include: today only `!/.dev-team-reports/test-improve/` exists, so this write is genuinely git-tracked for the `test-improve` caller; a future caller passing a different `--workflow` value would need its own `.gitignore` exception added first, or this write silently lands in ignored space despite the tracked-storage framing above.

```bash
BASELINE=".dev-team-reports/<workflow>/<slug>/data/baseline-coverage.json"
mkdir -p "$(dirname "$BASELINE")"
cat > "${BASELINE}.tmp" <<'JSON'
{
  "phase": 2,
  "captured_at": "<ISO-8601>",
  "tool": "jest",
  "line_pct": 41.2,
  "branch_pct": 28.7,
  "raw_report": "coverage/coverage-summary.json",
  "disabled_test_count": 47
}
JSON
mv -f "${BASELINE}.tmp" "$BASELINE"
```

**Multi-project repos only** (Step 1a ran): additionally persist
`.dev-team-reports/<workflow>/<slug>/data/coverage-config.json` — the
`config` dict Step 1a's `load_or_bootstrap`/`drift_check` resolved (the
just-bootstrapped config on a first run, or the existing config read
verbatim on every later run) — via `coverage_config.atomic_write_json`, the
same temp-file-then-rename idiom as `baseline-coverage.json` above. This
step is skipped entirely for single-project repos (Step 1b) — no
`coverage-config.json` is written for them.

`disabled_test_count` is included **only** when `.claude/memory/<workflow>/<slug>/disabled-tests.json` exists (present when a caller ran `/test-audit-disable` first); omit the field otherwise. `phase` carries the calling workflow's phase number when it has one, and may be omitted for workflows without numbered phases.

Append a baseline summary to the workflow's baseline memory file (for `/test-improve`, `.claude/memory/<workflow>/<slug>/phase-2.md`; other workflows write to their own baseline phase file). Just the coverage block — auditing is a separate worker. This is process bookkeeping, distinct from the baseline data file above, and is unaffected by the atomic-write change.

### 6. Post to the parent

**Tracker mode** — append a markdown block to the parent issue's description (the resolved CLI was recorded in Phase 1):

```markdown
## Phase-2 baseline (captured <ISO-8601>)
- Coverage tool: <tool>
- Line: <pct>%
- Branch: <pct>% (or "not native — see notes")
- Cannot-fail tests disabled in Phase 3: <count> (omit this line when no `disabled-tests.json` exists for the workflow)
- Quality targets: line ≥ 90% · branch ≥ 90% · mutants = 0 · determinism = 100% · wall-clock = fastest achievable
```

Use the same CLI pattern Phase 1 resolved. Examples:

```bash
# GitHub
gh issue edit <parent-id> --body-file <(gh issue view <parent-id> --json body -q .body; echo; cat phase-2-block.md)

# Azure DevOps
az boards work-item update --id <parent-id> --description "$(az boards work-item show --id <parent-id> --query 'fields."System.Description"' -o tsv)<append>"

# GitLab
glab issue note add <parent-iid> --message "$(cat phase-2-block.md)"

# Jira
acli jira workitem comment add --key <parent-key> --body "$(cat phase-2-block.md)"
```

**Local-files mode** — append the block to `.claude/plans/<workflow>/FEATURE.md` under a `## Metrics history` heading (create the heading if missing).

### 7. Report

Print:

- Line %, branch %.
- The path to `baseline-coverage.json`.
- The destination (parent issue URL or `FEATURE.md`).
- A reminder that the orchestrator's human gate runs next.

## Notes

- Coverage tools may legitimately differ by repo; never replace the repo's own script with a generic one unless detection fails. Operator override always wins for the coverage command/flags — but never for the `.sln`/`.csproj` row's discovered project set, which is always re-derived per run regardless of any operator-supplied command.
- The "fastest pre-merge wall-clock" target is not captured here — that's recorded by `/quality-targets-converge` once the full suite is in place. Baseline is line + branch only.
- For Go (and any tool without native branch coverage), `branch_pct` is `null` and `phase-2.md` flags the gap so the operator can decide whether to install an alternate coverage tool or waive the target.
