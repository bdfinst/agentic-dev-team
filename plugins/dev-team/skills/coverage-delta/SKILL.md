---
name: coverage-delta
description: >-
  Multi-workflow coverage delta worker. Reads the baseline coverage, re-runs
  the same coverage tool against the current suite, computes the delta on
  line+branch percentages, and posts it to the parent issue (or local
  `FEATURE.md`). Called after each Story so the operator sees coverage move
  with every test added. Called by `/test-improve` (Phase 5) via
  `--workflow test-improve`.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--story <id-or-path>] [--story-files <glob-or-comma-list>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Coverage Delta

Role: worker. Reports coverage change vs. the captured baseline. One snapshot per Story so the operator can see whether each add actually moved the needle. Callers with a phase model (such as `/test-improve`, where the baseline lands in Phase 2 and per-Story deltas fire in Phase 5) label snapshots by phase; phase-less workflows omit that label.

You have been invoked with the `/coverage-delta` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>`.
- `--parent <issue-url>` — parent issue URL (or empty for local-files).
- `--repo-slug <slug>` — `.claude/memory/<workflow>/` namespace.
- `--workflow <name>` — the workflow namespace under `.claude/memory/`. Defaults to `test-improve`. Orchestrators pass their own namespace (e.g. `/test-improve` passes `test-improve` for its Phase-5 per-Story deltas).
- `--story <id-or-path>` — optional Story this delta is attributed to. Used as the snapshot label.
- `--story-files <glob-or-comma-list>` — production-code files the Story touched (typically from `/build`'s commit diff, tests filtered out). When both `--story` AND a non-empty `--story-files` are present, Step 2b runs scoped mutation; otherwise it is a no-op so `/quality-targets-converge` can keep calling this worker without `--story-files` exactly as before.

## Steps

### 1. Load the baseline

Read `.dev-team-reports/<workflow>/<slug>/data/baseline-coverage.json`. If missing, tell the operator the baseline has not been captured (`/coverage-baseline` must run first; for `/test-improve` that is Phase 2) and stop.

### 2. Re-run coverage

Use the same coverage **tool** `/coverage-baseline` recorded — DO NOT switch tools mid-workflow, or the delta is meaningless. This governs the tool only, never the project/package list: for a multi-project repo (Step 2a below), the set of included projects/packages is re-derived from fresh discovery on every call, never reused from a prior run — a frozen, never-revisited list is exactly what caused issue #1759's ~30x underreported delta.

For a multi-project repo, load the persisted `coverage-config.json` first (Step 2a) and print `coverage_config.measurement_basis_notice(config.get("bootstrapped_at"), baseline["captured_at"])`'s result verbatim when non-`None` — a non-blocking notice that the comparison baseline predates multi-project discovery, so a reported delta may reflect a widened measurement scope rather than a real coverage change.

Capture exit code + stdout + stderr.

If the run fails, surface the first error and stop. Do not post a delta from a broken run.

### 2a. Multi-project re-derivation (.NET solutions & JS/TS workspaces)

When a `.sln` file exists at the repo root (.NET), or a workspace signal is present (JS/TS) — the same triggers `coverage-baseline`'s Step 1a uses — re-run the appropriate discovery script **fresh, every call**, never reusing a project/package list recorded by a prior run:

- **.NET**: `${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_dotnet.py`'s `discover_dotnet_projects(repo_root)`
- **JS/TS**: `${CLAUDE_PLUGIN_ROOT}/scripts/coverage_discovery_js.py`'s `discover_js_packages(repo_root)`

Implementation mechanics (the bootstrap/drift-check contract, weighted-merge, and the exact message templates): [`../coverage-baseline/references/multi-project-discovery.md`](../coverage-baseline/references/multi-project-discovery.md) — this section pins the contract surface only, mirroring how `coverage-baseline`'s own Step 1a links the same file rather than re-deriving the mechanics a second time.

**Config path.** `coverage-config.json` is read from the exact resolved path `.dev-team-reports/<workflow>/<slug>/data/coverage-config.json` — the SAME path `coverage-baseline`'s Step 5 persists to, and the SAME path `load_or_bootstrap` reads/writes in `coverage-baseline`'s Step 1a. There is no ambiguity: both skills operate on the identical file.

**Absent/malformed `coverage-config.json`.** Before calling `drift_check`, check whether that path exists and parses. If missing (the baseline predates this feature, or was captured on the single-project path with no config ever persisted) or malformed, stop with a named message telling the operator to re-run `/coverage-baseline` first — mirroring Step 1's existing missing-baseline branch. Do **not** silently bootstrap a config in-memory here: this worker is read-only on the repo's source (see Notes), and a delta is only ever meaningful against a config `/coverage-baseline` itself persisted.

**Discovery-signal check.** Before calling `drift_check`, check the fresh discovery call's return value — the same two branches `coverage-baseline`'s Step 1a already carries:

- `coverage_config.DISCOVERY_NOT_APPLICABLE` — should not occur here (this step only runs when the `.sln`/workspace trigger already fired); if it somehow does, treat it like the missing-config branch above: stop, post no delta.
- `coverage_config.discovery_error(...)` — surface `message`, post no delta, stop — the same treatment as an existing Step 2 run-failure (a genuine tool failure, not the actionable config gap the hard-failure block below describes).

Never let `discovered` reach `drift_check` unchecked.

**Zero-real-test-project guard.** Before calling `drift_check`, apply the same `any(coverage_config.needs_accounting(entry["classification"]) for entry in discovered)` check `coverage-baseline`'s Step 1a already carries. If `False` (every discovered project/package classifies `NOT_TEST`), stop immediately with the exact message `coverage-baseline`'s Step 1a uses, worded for a delta: `"Coverage capture stopped: no real test project was discovered in this <solution|workspace> — cannot establish a coverage floor. If this repo has test projects, verify they reference Microsoft.NET.Test.Sdk (or, for JS/TS, use jest/vitest/mocha+nyc/c8) so discovery can recognize them; otherwise there is no coverage floor to capture."` Post no delta.

Read the persisted `.dev-team-reports/<workflow>/<slug>/data/coverage-config.json` (written by the prior `/coverage-baseline` run) and call `coverage_config.drift_check(config, discovered)` against it:

- If `drift_check` raises `ValueError` (a malformed-but-parseable `included`/`excluded` shape — e.g. present but not a list), print the exception's message **verbatim, as its own named block**, and stop without posting a delta.
- `drift["hard_failure"]` is `True` (an unaccounted-for or conflicting project/package) — print `drift["hard_failure_message"]` **verbatim, as its own distinct, named block** headed `Coverage capture stopped:` — the same hard-failure rule and message `coverage-baseline` applies, never folded into or reusing this skill's own generic run-failure wording above. Stop; post no delta.
- `drift["hard_failure"]` is `False` — run the coverage command per included project/package (never once for the whole repo) and merge the results with `coverage_config.weighted_merge(project_reports)`, same as `coverage-baseline` Step 1a.

`drift["stale_warning_message"]` is carried forward regardless of `hard_failure` — see Step 5 (Report) for where it surfaces.

Single-project and mixed-stack repos (`coverage-baseline`'s Step 1b unaffected cases) never reach this step — Step 2's single-command path runs unchanged, and no `coverage-config.json` is ever read here for them.

### 2b. Measure scoped mutation (only when both `--story` AND `--story-files` are present)

**Worker boundary.** This worker measures and reports; it does NOT halt the workflow on net-new survivors. Policy enforcement is the orchestrator's job (`/test-improve` Phase 5 reads the structured `status` field this step emits and decides whether to pause Story close via the mutation-kill agent's `[c/r/w/q]` prompt).

**Implementation detail** — baseline-of-record lookup, equivalent-mutant filter, classification table, atomic-write idiom: [`references/mutation-gate.md`](references/mutation-gate.md). This section pins the contract (flags, status enum, exit-code rule, schema keys); the reference holds the mechanics.

Gating: skip this whole step unless BOTH `--story <id>` AND a non-empty `--story-files <files>` are supplied. `--story` alone (the call path `/quality-targets-converge` uses) triggers no mutation run and no `mutation-history.json` write — the result block on stdout carries `"mutation": null`.

When the gate fires:

1. Invoke `/mutation-testing --scope <expanded --story-files> --emit-json <tmp> --workflow-managed-approval`. The `--workflow-managed-approval` flag is allowed here because `/test-improve` Phase 0 captured operator approval at the workflow boundary (see `mutation-testing` `## Constraints` carve-out).
2. **Baseline-of-record per file.** For each file in `--story-files`, look up the most recent entry in `.dev-team-reports/<workflow>/<slug>/data/mutation-history.json`; that entry's `survivors_after` is the baseline-of-record. If no prior entry exists, the file's status is `first_measurement` (`survivors_before: null`, `delta: null`).
3. **Filter `status: "equivalent"` AND `status: "accepted"` survivors** from the `/mutation-testing` output before computing delta — reclassifications between runs, and documented rationale-bearing deferrals, must not show up as regressions.
4. Compute `delta = survivors_after - survivors_before` (skip when `first_measurement`) and assign a status per file:
   - `ok` — `delta <= 0`.
   - `net_new_survivors` — `delta > 0`. The result block lists each new survivor by `file:line:operator`.
   - `first_measurement` — no prior entry.
   - `tool_unavailable` — `/mutation-testing` returned the `no_tool_installed` envelope. The result block names `/setup` as the install path and includes `language: "<detected>"`. If a prior history entry recorded a different tool, surface that as `prior_tool: "<name>"` so the operator sees the disappearance.
   - `skipped_empty_scope` — `--story-files` expanded to zero files. No mutation run; one history entry recorded with this status.
5. Append per-file entries to `mutation-history.json` via **temp-file-then-rename** (write to `<path>.tmp` then `mv -f <path>.tmp <path>`). This keeps parallel `/coverage-delta` writes from interleaving when two Phase-5 Stories close within the same second. Direct overwrite of `mutation-history.json` is forbidden.

**Exit code.** This step's exit code is `0` on every status above, including `net_new_survivors` — the worker carries the signal in the status field, not the exit code. The exit code is non-zero ONLY on tool execution failure (a crash inside `/mutation-testing`, an unwritable history path, malformed JSON from the underlying tool). This is the worker/policy boundary: orchestrator reads `status`, worker reports cleanly.

**Result block on stdout** — a single JSON object the orchestrator can parse:

```json
{
  "status": "ok | net_new_survivors | first_measurement | tool_unavailable | skipped_empty_scope",
  "story": "<id>",
  "story_files": ["src/order.ts"],
  "mutation": {
    "tool": "stryker",
    "files": [
      { "file": "src/order.ts", "survivors_before": 8, "survivors_after": 3, "delta": -5, "status": "ok" }
    ]
  }
}
```

When the step is skipped (no `--story-files`), the block is `{"status": "ok", "mutation": null, ...}`.

### 3. Parse + compute the delta

Parse line + branch percentages with the same logic `/coverage-baseline` used. Compute:

```json
{
  "phase": <phase-number-or-null>,
  "captured_at": "<ISO-8601>",
  "story": "<id-or-path-or-null>",
  "line_pct": <current>,
  "branch_pct": <current>,
  "line_delta": <current - baseline>,
  "branch_delta": <current - baseline>,
  "baseline_line_pct": <from baseline.json>,
  "baseline_branch_pct": <from baseline.json>
}
```

`phase` is the calling workflow's phase number when it has one (`/test-improve` supplies `5`); workflows without a phase model supply `null`.

Append to `.dev-team-reports/<workflow>/<slug>/data/coverage-history.json` (array of snapshots, newest last).

### 4. Post the snapshot

Append a markdown row to the parent's `## Metrics history` section (tracker mode) or to `.claude/plans/<workflow>/FEATURE.md` (local-files mode):

```markdown
| <ISO-8601> | Phase <n> | <story-id-or-—> | Line <pct>% (Δ <+/-pct>) | Branch <pct>% (Δ <+/-pct>) | Mutants <count> (Δ <+/-n>) |
```

Create the table header on first call if it doesn't exist:

```markdown
## Metrics history

| Captured | Phase | Story | Line | Branch | Mutants |
|---|---|---|---|---|---|
```

The Mutants column is `—` when Step 2b was a no-op (no `--story-files`); otherwise it carries the aggregate `survivors_after` across the Story's files and `Δ` vs. the prior history entries.

Use the resolved CLI pattern from Phase 1 (same edit-the-parent invocation `/coverage-baseline` used).

### 5. Report

Print:

- Line + branch percentages and deltas.
- The destination (parent issue URL or `FEATURE.md`).
- The path to `coverage-history.json` for `/continue`.
- **Multi-project repos only**: when Step 2a's `drift["stale_warning_message"]` is non-`None` (an `excluded` entry that no longer matches any freshly-discovered project/package), print it **verbatim, as a named, non-blocking warning line** — it never blocks the run and never overrides the reported delta.
- **Multi-project repos only, every run**: print `coverage_config.format_active_exclusions(config)`'s result **verbatim** whenever it is non-`None` — one line per currently-excluded project/package naming its path and reason. This is informational context shown on every run (not a warning, not blocking), distinct from the stale-warning line above: it surfaces what is currently excluded and why, regardless of whether that exclusion has gone stale.

If the delta is **negative** (a Story made coverage worse), surface that as a warning so the operator can decide whether to keep the Story.

## Notes

- This worker is read-only on the repo's source — it runs the coverage command and parses the report. It does not modify tests or production code.
- Snapshots accumulate; nothing is overwritten. The full history feeds `/quality-targets-converge` in Phase 7.
- Wall-clock for the coverage run is not tracked here — that's `/quality-targets-converge`'s job.
