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
| `package.json` (JS/TS) | `npm test -- --coverage` (or `pnpm test --coverage`, `yarn test --coverage`) — or, when a workspace signal is present (a root `workspaces` field, `pnpm-workspace.yaml`, or `lerna.json`), multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions--jsts-workspaces)) |
| `pyproject.toml` / `setup.py` | `pytest --cov=. --cov-report=json` |
| `pom.xml` | `mvn test jacoco:report` |
| `build.gradle*` | `./gradlew test jacocoTestReport` |
| `*.csproj` | `dotnet test /p:CollectCoverage=true /p:CoverletOutputFormat=json` — or, when a `.sln` is present at the repo root, multi-project discovery (see [Step 1a](#1a-multi-project-discovery-net-solutions--jsts-workspaces)) |
| `Cargo.toml` | `cargo llvm-cov --json` |
| `go.mod` | `go test -coverprofile=coverage.out ./...` + `go tool cover -func=coverage.out` |

If the repo has its own coverage script (e.g. `npm run coverage`, `make coverage`), prefer that — detect via `package.json#scripts.coverage`, the `Makefile`, or a documented run target in `README.md`. If detection is ambiguous, ask the operator for the exact command.

### 1a. Multi-project discovery (.NET solutions & JS/TS workspaces)

Replaces the single frozen coverage command above for a multi-project .NET
solution or JS/TS workspace — closing the gap where a hand-picked,
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

Either discovery function can return `coverage_config.DISCOVERY_NOT_APPLICABLE`
(no `.sln` / no workspace signal — see Step 1b below: the repo is
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
   in this <solution|workspace> — cannot establish a coverage floor. If
   this repo has test projects, verify they reference
   Microsoft.NET.Test.Sdk (or, for JS/TS, use jest/vitest/mocha+nyc/c8) so
   discovery can recognize them; otherwise there is no coverage floor to
   capture."` (`<solution|workspace>` resolved to whichever stack applies).
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
   **per included project** (never once per repo), parse each project's raw
   covered/total statement and branch counts, and call
   `coverage_config.weighted_merge(project_reports)` to produce the merged
   `line_pct`/`branch_pct` that Step 4/5 record as the baseline.

   **Known, documented limitation (.NET/Coverlet).** Step 4's Coverlet row
   documents `summary.linecoverage`/`summary.branchcoverage` — final
   percentages, not the raw `covered_statements`/`total_statements`/
   `covered_branches`/`total_branches` counts `weighted_merge` requires.
   Coverlet's raw-count JSON layout (nested per-module/per-class/per-method
   hit data) needs verification against a real Coverlet run before this
   skill can document an exact JSON path to sum — asserting one without
   running the real tool risks documenting a shape that doesn't match
   Coverlet's actual output. Until that verification happens, multi-project
   .NET merge requires the operator's own coverage command wrapper to parse
   and supply the four raw counts per included project. If a per-project
   report carries only percentages with no raw counts, **stop** with
   `coverage_config.discovery_error("Project '<path>' produced only a
   percentage-based coverage report (no raw covered/total statement or
   branch counts); multi-project .NET weighted-merge requires raw counts —
   see the coverage-baseline SKILL.md Step 1a known-limitation note.")` —
   **never** silently degrade to a `null`/`0` baseline by feeding
   `weighted_merge` an incomplete report.

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

For each tool, parse the report into `{ "line": <pct>, "branch": <pct>, "tool": "<name>", "raw_path": "<file>" }`:

- Istanbul / Jest / Vitest → `coverage/coverage-summary.json` → `total.lines.pct` + `total.branches.pct`.
  - **If `coverage-summary.json` is absent** (the `json-summary` reporter wasn't enabled — see #1086), do not abort. Fall back, in order, to another emitted report and derive the two percentages from it:
    - `coverage/coverage-final.json` (Istanbul `json` reporter) → sum each file's statement/branch hit counts (`s`/`b`) into totals, then `line = covered_statements / total_statements * 100`, `branch = covered_branches / total_branches * 100`.
    - `coverage/lcov.info` → tally `LF`/`LH` for lines and `BRF`/`BRH` for branches across all records; `line = ΣLH/ΣLF * 100`, `branch = ΣBRH/ΣBRF * 100` (branch `null` when `BRF` totals 0).
    - `coverage/clover.xml` → read the project-level `<metrics>` element: `line = coveredstatements/statements * 100`, `branch = coveredconditionals/conditionals * 100`.
  - Note in the persisted baseline which report was used (`raw_report`). Recommend the operator run `/setup` (which now checks coverage readiness) or add the `json-summary` reporter so future runs use the canonical summary.
- pytest-cov → `coverage.json` → `totals.percent_covered` (and branch via `--branch`).
- JaCoCo → `target/site/jacoco/jacoco.csv` → sum line/branch missed+covered.
- Coverlet → `coverage.json` → `summary.linecoverage`, `summary.branchcoverage`.
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

- Coverage tools may legitimately differ by repo; never replace the repo's own script with a generic one unless detection fails. Operator override always wins.
- The "fastest pre-merge wall-clock" target is not captured here — that's recorded by `/quality-targets-converge` once the full suite is in place. Baseline is line + branch only.
- For Go (and any tool without native branch coverage), `branch_pct` is `null` and `phase-2.md` flags the gap so the operator can decide whether to install an alternate coverage tool or waive the target.
