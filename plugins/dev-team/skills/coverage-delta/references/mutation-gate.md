# `/coverage-delta` mutation gate — implementation detail

`/coverage-delta` `### 2b. Measure scoped mutation` is the **contract surface**: when invoked with both `--story` AND a non-empty `--story-files`, it runs scoped mutation against the Story's production-code files, emits a structured status, and writes per-file history without ever halting the workflow.

This file holds the implementation detail of Step 2b so the SKILL.md stays a thin orchestrator of two sub-operations (coverage delta + mutation gate), not a deep implementation of both. The contract surface — flag names, status enum, exit-code rule, schema keys — lives in `SKILL.md` because that is what reviewers, bats tests, and callers depend on. The mechanics live here.

## Baseline-of-record per file

For each file in `--story-files`, the baseline is the most recent entry in `.dev-team-reports/<workflow>/<slug>/data/mutation-history.json` for that file (with `<workflow>` resolved from the calling orchestrator's `--workflow` value — e.g. `test-improve`). Lookup procedure:

1. Read `mutation-history.json` (if absent, every file is `first_measurement`).
2. For each file `F`, filter entries where `entry.file == F`; pick the entry with the largest `captured_at` (ISO-8601 lexicographic sort).
3. `baseline = entry.survivors_after` if found; else `null` (status `first_measurement`).

When two `/coverage-delta` invocations close within the same second, both append entries — neither overwrites the other. The status logic uses the largest `captured_at`, so the most recent close wins.

## Equivalent- and accepted-mutant filter

`/mutation-testing` emits each survivor with `status: "survived"`, `status: "equivalent"`, or `status: "accepted"` (the latter two always carry a `reason` string). Filter both `status: "equivalent"` and `status: "accepted"` survivors before computing the delta — reclassifications between runs, and documented, rationale-bearing deferrals, must not show up as regressions.

Implementation: `jq '.survivors | map(select(.status == "survived")) | length'` on the `--emit-json` document. Selecting only `"survived"` already excludes both `"equivalent"` and `"accepted"` — no additional exclusion logic is needed when a new status value is added to the enum.

## Status classification (per file)

After computing `survivors_after`, classify each file:

| Status | When | Action |
| --- | --- | --- |
| `first_measurement` | baseline is `null` | Record entry with `survivors_before: null, delta: null`. |
| `ok` | `survivors_after <= baseline` | Record entry with `delta = survivors_after - baseline`. |
| `net_new_survivors` | `survivors_after > baseline` | Record entry with positive `delta`. The result block lists each new survivor (`file:line:operator`). |
| `tool_unavailable` | `/mutation-testing` returned `error: "no_tool_installed"` | Record entry with `prior_tool` (if the most recent history entry recorded a tool name); the result block names `/setup`. |
| `skipped_empty_scope` | `--story-files` glob expanded to zero files | Record one history entry per Story (not per file) with this status. |

## Atomic-write semantics

`mutation-history.json` is written via temp-file-then-rename to keep parallel `/coverage-delta` writes from interleaving:

```bash
HISTORY=".dev-team-reports/<workflow>/<slug>/data/mutation-history.json"
TMP="$(mktemp "${HISTORY}.XXXXXX")"
jq '. + [$new]' --argjson new "$NEW_ENTRY" "$HISTORY" > "$TMP" && mv -f "$TMP" "$HISTORY"
```

Direct overwrite of `mutation-history.json` is forbidden — `>` or `tee` would let one writer truncate the other's bytes during a concurrent close.

## Result-block schema on stdout

The block matches the schema documented in `SKILL.md` `### 2b`. Restated here for grep-ability:

```json
{
  "status":      "ok | net_new_survivors | first_measurement | tool_unavailable | skipped_empty_scope",
  "story":       "<id>",
  "story_files": ["<file>", ...],
  "mutation": {
    "tool":  "<stryker|pitest|mutmut|stryker-net|null>",
    "files": [
      { "file": "<path>", "survivors_before": <n|null>, "survivors_after": <n|null>, "delta": <n|null>, "status": "<status>" },
      ...
    ]
  }
}
```

When the step is skipped (no `--story-files`), the block is `{"status": "ok", "mutation": null, ...}` — the orchestrator interprets that as "no mutation signal this run, continue".

## Worker/policy boundary

The worker never halts on a status value. The exit code is `0` on every status above (including `net_new_survivors`) and non-zero ONLY on tool execution failure. The orchestrator (`/test-improve` Phase 5) reads `status` from the result block and decides whether to pause Story close (typically via the `mutation-kill` agent's `[c/r/w/q]` prompt). This is the worker/policy separation `plugins/dev-team/CLAUDE.md` describes — measurement here, policy upstream.
