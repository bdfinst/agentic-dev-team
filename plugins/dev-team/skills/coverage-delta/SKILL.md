---
name: coverage-delta
description: >-
  Phase-4 worker for `/test-modernize`. Reads the Phase-3 baseline coverage,
  re-runs the same coverage tool against the current suite, computes the
  delta on line+branch percentages, and posts it to the parent issue (or
  local `FEATURE.md`). Called after each Phase-4 Story so the operator sees
  coverage move with every test added.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--story <id-or-path>] [--story-files <glob-or-comma-list>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Coverage Delta

Role: worker. Reports coverage change vs. the Phase-3 baseline. One snapshot per Story so the operator can see whether each Phase-4 / Phase-5 add actually moved the needle.

You have been invoked with the `/coverage-delta` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>`.
- `--parent <issue-url>` — parent issue URL (or empty for local-files).
- `--repo-slug <slug>` — `memory/test-modernize/` namespace.
- `--story <id-or-path>` — optional Story this delta is attributed to. Used as the snapshot label.
- `--story-files <glob-or-comma-list>` — production-code files the Story touched (typically from `/build`'s commit diff, tests filtered out). When both `--story` AND a non-empty `--story-files` are present, Step 2b runs scoped mutation; otherwise it is a no-op so `/quality-targets-converge` can keep calling this worker without `--story-files` exactly as before.

## Steps

### 1. Load the baseline

Read `memory/test-modernize/<slug>/baseline-coverage.json`. If missing, tell the operator Phase 3 has not run and stop.

### 2. Re-run coverage

Use the same `tool` and command that `/coverage-baseline` recorded — DO NOT switch tools mid-workflow or the delta is meaningless. Capture exit code + stdout + stderr.

If the run fails, surface the first error and stop. Do not post a delta from a broken run.

### 2b. Measure scoped mutation (only when both `--story` AND `--story-files` are present)

**Worker boundary.** This worker measures and reports; it does NOT halt the workflow on net-new survivors. Policy enforcement is the orchestrator's job (`/test-modernize` Phase 4 reads the structured `status` field this step emits and decides whether to pause Story close).

Gating: skip this whole step unless BOTH `--story <id>` AND a non-empty `--story-files <files>` are supplied. `--story` alone (the call path `/quality-targets-converge` uses) triggers no mutation run and no `mutation-history.json` write — the result block on stdout carries `"mutation": null`.

When the gate fires:

1. Invoke `/mutation-testing --scope <expanded --story-files> --emit-json <tmp> --workflow-managed-approval`. The `--workflow-managed-approval` flag is allowed here because `/test-modernize` Phase 0 captured operator approval at the workflow boundary (see `mutation-testing` `## Constraints` carve-out).
2. **Baseline-of-record per file.** For each file in `--story-files`, look up the most recent entry in `memory/test-modernize/<slug>/mutation-history.json`; that entry's `survivors_after` is the baseline-of-record. If no prior entry exists, the file's status is `first_measurement` (`survivors_before: null`, `delta: null`).
3. **Filter `status: "equivalent"` survivors** from the `/mutation-testing` output before computing delta — reclassifications between runs must not show up as regressions.
4. Compute `delta = survivors_after - survivors_before` (skip when `first_measurement`) and assign a status per file:
   - `ok` — `delta <= 0`.
   - `net_new_survivors` — `delta > 0`. The result block lists each new survivor by `file:line:operator`.
   - `first_measurement` — no prior entry.
   - `tool_unavailable` — `/mutation-testing` returned the `no_tool_installed` envelope. The result block names `/init-dev-team` as the install path and includes `language: "<detected>"`. If a prior history entry recorded a different tool, surface that as `prior_tool: "<name>"` so the operator sees the disappearance.
   - `skipped_empty_scope` — `--story-files` expanded to zero files. No mutation run; one history entry recorded with this status.
5. Append per-file entries to `mutation-history.json` via **temp-file-then-rename** (write to `<path>.tmp` then `mv -f <path>.tmp <path>`). This keeps parallel `/coverage-delta` writes from interleaving when two Phase-4 Stories close within the same second. Direct overwrite of `mutation-history.json` is forbidden.

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
  "phase": <4 or 5>,
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

Append to `memory/test-modernize/<slug>/coverage-history.json` (array of snapshots, newest last).

### 4. Post the snapshot

Append a markdown row to the parent's `## Metrics history` section (tracker mode) or to `./plans/test-modernize/FEATURE.md` (local-files mode):

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

If the delta is **negative** (a Story made coverage worse), surface that as a warning so the operator can decide whether to keep the Story.

## Notes

- This worker is read-only on the repo's source — it runs the coverage command and parses the report. It does not modify tests or production code.
- Snapshots accumulate; nothing is overwritten. The full history feeds `/quality-targets-converge` in Phase 5.
- Wall-clock for the coverage run is not tracked here — that's `/quality-targets-converge`'s job.
