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
| `package.json` (JS/TS) | Single package (no `workspaces` field, no `pnpm-workspace.yaml`, no `lerna.json`): `npm test -- --coverage` (or `pnpm test --coverage`, `yarn test --coverage`). **Workspace repo** (any of those signals present): run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_js.py" <repo-path>` to discover and classify every workspace package by structural marker (a real `test` script plus a coverage-capable runner), then follow the multi-project flow below and run the package's own coverage command per included package. |
| `pyproject.toml` / `setup.py` | `pytest --cov=. --cov-report=json` |
| `pom.xml` | `mvn test jacoco:report` |
| `build.gradle*` | `./gradlew test jacocoTestReport` |
| `*.sln` / `*.csproj` | Single `.csproj` with no `.sln`: `dotnet test /p:CollectCoverage=true /p:CoverletOutputFormat=json`. **Solution present**: run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_dotnet.py" <repo-path>` to discover and classify every project in the solution by structural marker (`Microsoft.NET.Test.Sdk`, re-derived every run — no caller-supplied single command, no hand-maintained list), then follow the multi-project flow below and run `dotnet test "<project>" /p:CollectCoverage=true /p:CoverletOutputFormat=json` per included project (quote the interpolated path — `src/My Project/My Project.csproj` is an ordinary .NET layout). This supersedes `scripts/discover_coverage_projects.py`, #1759's .NET-only first fix, whose different config schema `/coverage-delta` still reads until its own slice lands. |
| `Cargo.toml` | `cargo llvm-cov --json` |
| `go.mod` | `go test -coverprofile=coverage.out ./...` + `go tool cover -func=coverage.out` |

If the repo has its own coverage script (e.g. `npm run coverage`, `make coverage`), prefer that — detect via `package.json#scripts.coverage`, the `Makefile`, or a documented run target in `README.md`. If detection is ambiguous, ask the operator for the exact command. This override does not apply to the discovered *project set* in either multi-project row above — that set is always re-derived per run, regardless of any repo-level coverage script. The operator may still override the coverage command each project is measured with.

### 1a. Multi-project discovery, config, and merge

Runs only when Step 1 found a multi-project signal — a `.sln`, or a JS/TS workspace config. A single-manifest repo skips this section entirely: no discovery call, no `coverage-config.json`, and Step 1's command selection is unchanged. Mechanics — markers, schema, drift categories, merge arithmetic, known limitations: [`references/multi-project-discovery.md`](references/multi-project-discovery.md).

1. **Discover.** Run the stack's discovery script. `{"applicable": false}` means no multi-project signal after all — fall back to Step 1's single command and skip the rest of this section.
2. **Load or bootstrap the config** at `.dev-team-reports/<workflow>/<slug>/data/coverage-config.json` via `coverage_config.load_or_bootstrap`. Absent or unreadable bootstraps from this run's discovery (everything included, zero exclusions); a valid config is never overwritten. Echo the returned operator notice to run output when there is one.
3. **Drift-check** the fresh discovery against the config via `coverage_config.drift_check`. Echo each warning. On any error, stop — see the hard-failure block below.
4. **Measure** each `included` project with the stack's coverage command, parse each per Step 4, then **weighted-merge** them via `coverage_config.weighted_merge`. The merge is weighted by statement/branch counts, never a simple average. Zero merged projects is itself a hard failure.

**On a drift hard failure**, print this block *verbatim as its own distinct block* — never folded into Step 3's generic coverage-run-failure banner, and never abbreviated:

```text
## Coverage discovery drift — no baseline written

<each drift_check error message, one per line>
```

Then stop. Write no baseline and no `coverage-config.json` change. The drift messages are the actionable part: each names the offending path and the exact edit that resolves it.

### 2. Existing-baseline guard

Check whether `.dev-team-reports/<workflow>/<slug>/data/baseline-coverage.json` already exists for the resolved slug. This existing-baseline guard is this worker's application of the shared existing-tracked-artifact re-capture guard — the canonical definition and rationale live once in `knowledge/decision-defaults.md`'s "Re-capture: keep vs. overwrite an existing tracked artifact" axis; this step cites that axis for the *why* and spells out the operational branches below so an executing agent doesn't need to open a second file mid-task to know what to do.

Applied here:

- **No existing file, or overwrite chosen** — proceed to Step 3 (Run coverage) and the rest of the normal flow.
- **Existing file, interactive session** — prompt keep/overwrite (default keep). An answer that is neither "keep" nor "overwrite" (case-insensitive) re-prompts with the identical choice — never falls back silently to either option, no retry limit, no timeout.
- **Existing file, non-interactive** (no usable TTY, or `DEV_TEAM_AUTO_APPROVE=1`) — keep the existing baseline automatically; both log the auto-decision and echo it to run output, not only record it to a file.
- **Existing file is malformed or corrupt** (fails to parse as JSON — e.g. left over from a prior interrupted write) — treat it as absent, never as a baseline to keep. Emit a warning naming why a fresh capture is happening, then proceed to Step 3.
- **On keep** — skip straight to Step 7 (Report). Reuse the existing file's `tool`, `line_pct`, and `branch_pct`, and report its `captured_at` instead of a freshly captured timestamp. Do not dispatch a coverage run.

### 3. Run coverage

Run the chosen command from `<repo-path>`. Capture stdout, stderr, and the exit code. In the multi-project case, run it once per `included` project and treat any project's failure as a failed run.

If the run fails, print this block and stop:

```text
## Coverage run failed — no baseline written

<the first error from the failing command>
```

- Do NOT write a baseline. The floor must be a true measurement.
- This banner covers a *coverage tool* failure only. A Step 1a discovery-drift failure is a different condition with a different fix, so it prints its own `## Coverage discovery drift` block instead — the two are never folded together in either direction.

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
  "phase": 3,
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

In the multi-project case the persisted `line_pct`/`branch_pct` are the **weighted-merged** numbers, `tool` names the per-project tool, and two further fields record the merge: `merged_projects` (the `included` paths that were measured) and `raw_report` naming the per-project report kind. Additionally persist `coverage-config.json` beside the baseline, through the same atomic write:

```bash
CONFIG=".dev-team-reports/<workflow>/<slug>/data/coverage-config.json"
```

`coverage_config.load_or_bootstrap` performs that write itself, temp-file-then-rename, when it bootstraps; a valid pre-existing config is left untouched. Single-manifest repos write no `coverage-config.json` at all.

`disabled_test_count` is included **only** when `.claude/memory/<workflow>/<slug>/disabled-tests.json` exists (present when a caller ran `/test-audit-disable` first); omit the field otherwise. `phase` carries the calling workflow's phase number when it has one, and may be omitted for workflows without numbered phases.

Append a baseline summary to the workflow's baseline memory file (for `/test-improve`, `.claude/memory/<workflow>/<slug>/phase-2.md`; other workflows write to their own baseline phase file). Just the coverage block — auditing is a separate worker. This is process bookkeeping, distinct from the baseline data file above, and is unaffected by the atomic-write change.

### 6. Post to the parent

**Tracker mode** — append a markdown block to the parent issue's description (the resolved CLI was recorded in Phase 1):

```markdown
## Phase-3 baseline (captured <ISO-8601>)
- Coverage tool: <tool>
- Line: <pct>%
- Branch: <pct>% (or "not native — see notes")
- Cannot-fail tests disabled in Phase 3: <count> (omit this line when no `disabled-tests.json` exists for the workflow)
- Quality targets: line ≥ 90% · branch ≥ 90% · mutants = 0 · determinism = 100% · wall-clock = fastest achievable
```

Use the same CLI pattern Phase 1 resolved. Examples:

```bash
# GitHub
gh issue edit <parent-id> --body-file <(gh issue view <parent-id> --json body -q .body; echo; cat phase-3-block.md)

# Azure DevOps
az boards work-item update --id <parent-id> --description "$(az boards work-item show --id <parent-id> --query 'fields."System.Description"' -o tsv)<append>"

# GitLab
glab issue note add <parent-iid> --message "$(cat phase-3-block.md)"

# Jira
acli jira workitem comment add --key <parent-key> --body "$(cat phase-3-block.md)"
```

**Local-files mode** — append the block to `.claude/plans/<workflow>/FEATURE.md` under a `## Metrics history` heading (create the heading if missing).

### 7. Report

Print:

- Line %, branch %. In the multi-project case, say it is a weighted merge and name how many projects it merged.
- Any bootstrap notice, stale-exclusion warning, or measurement-basis notice from Step 1a — a baseline whose `captured_at` predates the config's `bootstrapped_at` is not comparable to a merged delta, and the notice says so.
- The path to `baseline-coverage.json`.
- The destination (parent issue URL or `FEATURE.md`).
- A reminder that the orchestrator's human gate runs next.

## Notes

- Coverage tools may legitimately differ by repo; never replace the repo's own script with a generic one unless detection fails. Operator override always wins for the coverage command/flags — but never for a multi-project row's discovered project set, which is always re-derived per run regardless of any operator-supplied command.
- Multi-project discovery is a re-derivation, not a cache. A project list frozen in prose notes is exactly what caused #1759's ~30x underreported delta, so nothing in this worker records one.
- The "fastest pre-merge wall-clock" target is not captured here — that's recorded by `/quality-targets-converge` once the full suite is in place. Baseline is line + branch only.
- For Go (and any tool without native branch coverage), `branch_pct` is `null` and `phase-3.md` flags the gap so the operator can decide whether to install an alternate coverage tool or waive the target.
