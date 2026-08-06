# Output Format Reference

## Per-agent JSON result

```json
{
  "agentName": "structure-review",
  "status": "pass|warn|fail|skip",
  "modelTier": "mid",
  "issues": [
    {
      "severity": "error|warning|suggestion",
      "confidence": "high|medium|none",
      "file": "src/auth/login.ts",
      "line": 42,
      "message": "God object: AuthController handles login, registration, and password reset",
      "suggestedFix": "Split into LoginController, RegistrationController, and PasswordResetController"
    }
  ],
  "summary": "2 issues found: 1 error, 1 warning"
}
```

### `confidence` field values

| Value | Meaning | `apply-fixes` behavior |
|-------|---------|----------------------|
| `high` | Mechanical fix; correct with high certainty | Auto-apply |
| `medium` | Direction right; tradeoffs possible | Present as suggested diff — require confirmation |
| `none` | Requires human judgment | Present finding only; do not generate correction prompt |

## Aggregated JSON result (`--json` flag)

```json
{
  "overall": "pass|warn|fail",
  "timestamp": "2026-03-01T12:00:00Z",
  "targetFiles": 42,
  "preFlightPassed": true,
  "agents": [
    {"agentName": "test-review", "status": "pass", "modelTier": "mid", "issues": [], "summary": "..."}
  ],
  "totals": {"errors": 0, "warnings": 2, "suggestions": 1},
  "tokenEstimate": {
    "totalInputFiles": 15000,
    "agentCount": 11,
    "contextStrategy": "diff-only|full-file|mixed"
  },
  "topFindings": [
    {
      "severity": "error|warning|suggestion",
      "agents": ["structure-review", "complexity-review"],
      "file": "src/api/handler.ts",
      "line": 15,
      "message": "God object: handler mixes routing, validation, and persistence"
    }
  ],
  "dispatchFailures": [
    {"agentName": "arch-review", "attempts": 2, "error": "Tool result missing due to internal error"}
  ],
  "summary": "FAIL (N agents passed, N warned, N failed). N total issues. 1 lens never ran (dispatch failure)."
}
```

The `tokenEstimate` field provides rough cost observability:

- `totalInputFiles`: approximate character count of all input files passed to agents
- `agentCount`: number of agents that actually reviewed content this run —
  excludes `skip` (contract-shaped, but nothing was reviewed) and
  `dispatchFailures` (never ran)
- `contextStrategy`: whether diff-only, full-file, or a mix was used

The `topFindings` array is the consolidated cross-agent view — one entry per
distinct `file:line`, so a finding surfaced by several agents appears once:

- `severity` is the **single highest** enum (`error` > `warning` > `suggestion`)
  for that finding — never a slash- or comma-joined string.
- `agents` is an explicit array of the reporting agents. Multi-agent
  attribution lives here; never join multiple values into `severity` or an
  `agent` scalar.

`dispatchFailures` (issue #1752, always present, empty array when none):
agents whose `Agent` tool dispatch failed and then failed a single individual
retry — the lens never actually ran. Distinct from an `agents[]` entry with
`status: "skip"` (agent had nothing to review this run — see
[`knowledge/review-agent-output-contract.md`](../../knowledge/review-agent-output-contract.md#status-values))
and from `status: "fail"` (agent ran and found error-severity issues). A
non-empty `dispatchFailures` list is never omitted because the rest of the
panel returned cleanly.

**A non-empty `dispatchFailures` forces `overall: "fail"`**, unconditionally,
regardless of what the per-agent results alone would compute — the coverage
gap is enforced by this DTO itself, not by each caller re-deriving it from
`dispatchFailures` separately. This matters because `SKILL.md` step 9 (the
`.pr-review-passed` gate) never runs under `--json` — without this rule, a
`--json` caller (e.g. `/pr`, which reads only `overall`/`status`) could see
`overall: "pass"` and proceed despite a lens that never ran, exactly the
silent-gap failure mode #1752 exists to close.

**A step 6a fix-loop exit via escalation also forces `overall: "fail"`**
(issue #1880), for the same reason and by the same mechanism as the
`dispatchFailures` rule above: `SKILL.md` step 6a's own exit-conditions table
already treats a round-cap exit, an iteration-limit exit, and a
"same issues persist" exit as fail-equivalent — but only for step 9's
`.pr-review-passed` gate-write condition, and step 9 never runs under `--json`.
Without this second rule, an escalated review whose only remaining issues are
`warning`-severity would compute `overall: "warn"` from the per-agent totals
alone and a `--json` caller (e.g. `/pr`'s internal `/code-review --since
<base> --json` call) would see a passing-looking `"warn"` and proceed —
silently missing the escalation, exactly the gap the `dispatchFailures` rule
above already closed for dispatch coverage. A **clean** `converged` exit
(zero actionable issues, or the round ledger reporting `converged`) is
**not** an escalation and does not trigger this rule. Apply both override
rules — `dispatchFailures` and fix-loop escalation — after the totals-based
`overall` computation, so either one always wins regardless of the per-agent
severity mix.

**`--json` output contract.** When `--json` is set, the object above is the
run's *only* output: printed to stdout, and no `corrections/*.json` files or
`.pr-review-passed` gate file are written — regardless of scope (`--path`,
`--since`, `--all`, auto-scope) or how many issues were found. This holds
whether `--json` was reached directly or via `/pr`'s call into `/code-review
--json` (see SKILL.md steps 7–9).

## Per-slice section artifact (sliced mode)

Written by `scripts/ledger.py` → `write_section` to
`.dev-team-reports/code-review/raw/section-<id>.json` as each slice completes,
then dropped from orchestrator context (persist-and-drop). `scripts/consolidate.py`
reads these back for the final report.

```json
{
  "schema": "code-review-section/v1",
  "id": "0001",
  "files": ["src/auth/login.ts", "src/auth/session.ts"],
  "is_declarative": false,
  "panel": ["correctness-review", "structure-review"],
  "findings": [
    {"severity": "warning", "confidence": "medium", "agent": "structure-review", "file": "src/auth/login.ts", "line": 42, "message": "..."}
  ],
  "dispatchFailures": []
}
```

- `id` is the slice id; the filename is `section-<id>.json`.
- `dispatchFailures` (issue #1762, always present, empty array when none): this
  slice's own unrecovered dispatch failures — same shape as the legacy path's
  field (below). `scripts/consolidate.py` concatenates every slice's list into
  the consolidated aggregate's own `dispatchFailures` field (see below).
- `panel` lists the agents that **actually ran** for this slice — a reduced-panel
  (declarative) slice lists only `correctness-review` and `structure-review`, so
  a reader can tell "fewer findings" from "fewer reviewers ran".
- `findings` use the per-agent `issues[]` shape above **plus an `agent` field**
  naming the review dimension that reported each one. Because a slice's whole
  panel writes into one flat `findings[]` list, that `agent` tag is what lets
  `consolidate.py` merge reporting agents per `file:line` and roll up recurring
  themes — omitting it yields empty `agents[]` arrays and no themes.

### Schema-drift tolerance (#1261)

Real review-agent output drifts from this schema — agents return the native
`{status, issues, summary}` shape, key the list as `issues` (the per-agent key)
instead of `findings` (the section key), or add extra top-level keys. The
aggregator absorbs these variants deterministically rather than miscounting:

- `consolidate.py`'s `consolidate()` reads a section's findings from `findings`
  **or** `issues` (canonical first), so a mis-keyed list is aggregated, never
  silently counted as zero. A value present but not a list degrades to "no
  findings" rather than crashing.
- `consolidate.normalize_agent_result(raw, agent_name=None)` is the extraction
  contract for folding one agent's raw result into a section's flat `findings[]`:
  it pulls the list from either key, ignores extra keys (`status`, `summary`),
  and tags each finding with its reporting `agent` (`raw["agentName"]`, else the
  passed `agent_name`). Non-dict input degrades to `[]`; it never raises.

This tolerance is a safety net for silent drift, **not** a licence to emit the
wrong shape — the per-agent contract above (`issues[]`) remains authoritative.

## Progress ledger (sliced mode)

Written by `init_ledger` to `.dev-team-reports/code-review/ledger.json`, updated to
`done` as each slice's section artifact lands. Inspectable/interruptible — a
partial ledger is always valid JSON.

```json
{
  "schema": "code-review-ledger/v1",
  "cap": 50,
  "slices": [
    {"id": "0001", "files": ["src/auth/login.ts"], "is_declarative": false, "status": "pending"}
  ]
}
```

- `cap` is the per-slice file cap the run partitioned with; `--resume` **refuses**
  a different cap rather than silently repartitioning (see `sliced-mode.md`).
- `status` is `pending` until the slice's section artifact exists, then `done`.
  The artifact on disk — not this status field — is the source of truth for
  `--resume`.

## Consolidated aggregate (sliced mode)

Produced by `scripts/consolidate.py` → `consolidate(sections)` from all
`section-*.json` artifacts. It extends the aggregated `--json` object above with
three sliced-only fields, and reuses the same `topFindings` dedup contract
(one entry per distinct `file:line`, reporting agents merged into `agents[]`,
severity = the single highest enum).

```json
{
  "sliced": true,
  "sliceCount": 24,
  "overall": "warn",
  "totals": {"errors": 0, "warnings": 5, "suggestions": 3},
  "topFindings": [
    {"severity": "warning", "agents": ["structure-review", "complexity-review"], "file": "src/api/handler.ts", "line": 15, "message": "..."}
  ],
  "recurringThemes": [
    {"agent": "structure-review", "slices": ["0003", "0007", "0011"], "occurrences": 9}
  ],
  "reducedPanelSlices": ["0002", "0019"],
  "dispatchFailures": [
    {"agentName": "arch-review", "attempts": 2, "error": "Tool result missing due to internal error"}
  ],
  "summary": "WARN across 24 slices — 0 errors, 5 warnings, 3 suggestions; 1 recurring theme(s)."
}
```

- `summary`: a one-line roll-up (status, slice count, totals, theme count).
- `malformedArtifacts` (optional): present only when a `section-*.json` was
  unreadable — an array of the offending paths; `main()` also reports each to
  stderr and exits non-zero, so a bad artifact is never silently dropped.
- `recurringThemes`: review dimensions (by `agent`) whose findings recur across
  **two or more slices** — the systemic-pattern rollup (e.g. the same god-class
  or leak flagged in many modules). `slices` lists the affected slice ids;
  `occurrences` is the total finding count for that dimension. A dimension
  appearing in only one slice is **not** a theme.
- `reducedPanelSlices`: the ids of slices that ran the reduced (declarative)
  panel — so a reader can tell "fewer findings" from "fewer reviewers ran".
- `dispatchFailures` (issue #1762, always present, empty array when none):
  the concatenation of every slice's own `dispatchFailures` entries (per-slice
  schema above) — agents whose `Agent` tool dispatch failed and then failed a
  single individual retry, for that slice's panel. Same shape and same
  `agentName`/`attempts`/`error` fields as the legacy aggregate's
  `dispatchFailures` above; consolidation only concatenates, it does not
  re-shape. A non-empty list is never omitted because the rest of the run
  returned cleanly.
- **A non-empty `dispatchFailures` forces `overall: "fail"`**, unconditionally,
  after the totals-based `overall` computation above — the same
  unconditional-override rule as the legacy aggregate, so a lens that never
  ran on even one slice cannot be masked by a `pass`/`warn` computed from the
  slices that did return.

## Correction prompt JSON

```json
{
  "priority": "high|medium|low",
  "confidence": "high|medium",
  "category": "structure-review",
  "instruction": "Fix: God object handles too many concerns (Suggested: Split into focused controllers)",
  "context": "Line 42 in src/auth/login.ts",
  "affectedFiles": ["src/auth/login.ts"]
}
```

Severity mapping: error→high, warning→medium, suggestion→low.

Correction prompts are only generated for issues with `confidence: high` or `confidence: medium`. Issues with `confidence: none` are included in the review report but do not produce correction prompts — they require human judgment and must be resolved manually before merging.

## Status rules

- **pass**: Zero issues
- **warn**: Issues found, none are errors
- **fail**: At least one error-severity issue
- **skip**: see the canonical definition in [`knowledge/review-agent-output-contract.md`](../../knowledge/review-agent-output-contract.md#status-values)

`dispatchFailures` entries carry no `status` at all — the agent never ran, so
none of the four values above apply. See the `dispatchFailures` field
description above.

## Model tier values

Each agent declares a `Model tier` field that controls which model runs it:

| Tier | Model | Use for |
| ------ | ------- | --------- |
| `small` | Haiku | Pattern matching, thresholds, naming checks |
| `mid` | Sonnet | Structural analysis, test quality, mutation detection |
| `frontier` | Opus | Security analysis, domain modeling, semantic reasoning |

## Context needs values

Each agent declares a `Context needs` field that controls what input it receives:

| Value | Input | When to use |
| ------- | ------- | ------------- |
| `diff-only` | Git diff output only | Pattern-matching agents (naming, FP) |
| `full-file` | Complete file contents | Agents needing function-level context |
| `project-structure` | Full files + directory tree | Agents reasoning about architecture |

## Review Findings prompt (interactive — step 6)

When actionable issues exist, present this prompt before any fix action. **This
prompt is bypassed under `--json` (or `--yes`)**: those runs are contractually
non-interactive and default to report-only (no code modified) — see SKILL.md
step 6, exception (a).

```text
## Review Findings

Found N actionable issues (N errors, N warnings) that can be
auto-fixed, plus N issues requiring human review.

Actionable issues by agent:
- structure-review: 3 (2 error, 1 warning)
- naming-review: 2 (2 warning)
- js-fp-review: 1 (1 error)

Options:
1. **Fix** — Auto-fix actionable issues and re-run review
   (up to 5 iterations until clean)
2. **Report only** — Save all findings to a report without
   modifying any code
```

## Review-Fix Loop iteration log (step 6a-iv)

```text
## Review-Fix Loop

| Iteration | Actionable Issues | Fixed | Remaining | Agents Re-run |
|-----------|-------------------|-------|-----------|---------------|
| 1         | 7                 | 6     | 1         | 3             |
| 2         | 1                 | 1     | 0         | 1             |

Loop converged in 2 iterations.
```

If the loop did not converge:

```text
Loop stopped after 5 iterations. 2 issues remain:
- [security-review] SQL injection at src/db/query.ts:42 [auto-fix failed — human review required]
- [domain-review] Abstraction leak at src/api/handler.ts:15 [confidence: none — human review required]
```

## Code Review Summary report (step 7, prose mode)

```text
# Code Review Summary

| Agent              | Status | Issues | Fixed | Model Tier |
|--------------------|--------|--------|-------|------------|
| test-review        | PASS   | 0      | —     | mid        |
| structure-review   | PASS   | 2      | 2     | mid        |
| security-review    | WARN   | 1      | 0     | frontier   |
| ...                | ...    | ...    | ...   | ...        |

Overall: WARN after 2 fix iterations (N agents passed, N warned, N failed)
Total issues found: N | Auto-fixed: N | Human review required: N

## Dispatch Failures

| Agent | Attempts | Error |
|-------|----------|-------|
| arch-review | 2 | Tool result missing due to internal error |

Gate NOT written: 1 lens never ran and its retry also failed. Re-run
/code-review to retry the missing lens(es).
```

The **Dispatch Failures** section is present only when `dispatchFailures` is
non-empty (issue #1752) — omit it entirely on a clean run, but never omit it
when there is at least one entry, regardless of how the rest of the panel
scored.

After the summary, list remaining issues grouped by file, sorted by severity. Mark each with: `[confidence: none]`, `[auto-fix failed]`, or `[suggestion]`. Append the iteration table above.

## Override audit log entry (step 2, `--force` path)

Append to `.claude/metrics/override-audit.jsonl` (create if missing):

```json
{
  "timestamp": "<ISO 8601>",
  "branch": "<current branch>",
  "triggeredBy": "--force",
  "reason": "<value of --reason>",
  "targetFiles": ["<file list>"],
  "gatesSkipped": ["lint", "type-check", "secret-scan", "semgrep", "pipeline-red"]
}
```
