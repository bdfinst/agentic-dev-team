---
name: coverage-delta
description: >-
  Phase-4 worker for `/test-modernize`. Reads the Phase-3 baseline coverage,
  re-runs the same coverage tool against the current suite, computes the
  delta on line+branch percentages, and posts it to the parent issue (or
  local `FEATURE.md`). Called after each Phase-4 Story so the operator sees
  coverage move with every test added.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--story <id-or-path>]"
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

## Steps

### 1. Load the baseline

Read `memory/test-modernize/<slug>/baseline-coverage.json`. If missing, tell the operator Phase 3 has not run and stop.

### 2. Re-run coverage

Use the same `tool` and command that `/coverage-baseline` recorded — DO NOT switch tools mid-workflow or the delta is meaningless. Capture exit code + stdout + stderr.

If the run fails, surface the first error and stop. Do not post a delta from a broken run.

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
| <ISO-8601> | Phase <n> | <story-id-or-—> | Line <pct>% (Δ <+/-pct>) | Branch <pct>% (Δ <+/-pct>) |
```

Create the table header on first call if it doesn't exist:

```markdown
## Metrics history

| Captured | Phase | Story | Line | Branch |
|---|---|---|---|---|
```

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
