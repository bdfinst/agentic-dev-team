# Telemetry Schema Reference

Every `metrics/*.jsonl` and `metrics/*.json` file the dev-team plugin writes,
in one place, so `session-analysis`, `/session-review`, `/harness-audit`,
`/cost-report`, and future cross-machine aggregation (#178) compose against
stable, named schemas instead of reverse-engineering emitters.

**Privacy stance (non-negotiable, all streams):** rule IDs, counts, hashes,
and enums only — never command text, prompt text, file contents, or free-text
reasons beyond what a stream explicitly documents below as human-authored
(e.g. `config-changelog.jsonl`'s `description`, which is a deliberate,
human/agent-reviewed audit note, not incidental free text). Where a stream
predates this doc and already carries a `reason` field with freeform text
(e.g. `refactor-freeze.jsonl`'s internal-error diagnostics), that is existing,
unchanged precedent — not a new exception.

Each section below names: fields, types, emitter, consent gating, and
consumers. A companion test
(`tests/hooks/test_boundary_events.py::test_schema_doc_covers_all_metrics_paths`)
cross-checks every `metrics/*.jsonl` / `metrics/*.json` path string referenced
in shipped code against this doc's coverage and fails on omission.

---

## `boundary-events.jsonl`

**Added by #859.** The boundary-level (policy-gateway) channel: every guard
hook's block/warn/bypass decision, plus human-intervention keywords. Extended
by #906 with a fifth decision, `revert`, for hooks that don't warn or block
but actively correct state after the fact.

| Field | Type | Values / source |
|---|---|---|
| `ts` | string | ISO-8601 UTC `%Y-%m-%dT%H:%M:%SZ` |
| `hook` | string | Emitting hook's module name, e.g. `destructive_guard`, `verify_guard`, `pre_commit_review`, `telemetry` |
| `tool` | string | Hooked tool/event: `Bash`, `Write`, `Edit`, `Skill`, `Agent`, `UserPromptSubmit` |
| `decision` | string enum | `block` \| `warn` \| `bypass` \| `intervention` \| `revert` |
| `matched_rule` | string | Rule ID from a closed vocabulary (pattern ID, hook-defined constant, bypass flag name, or intervention keyword) — never free text |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |
| `session_id` | string, optional | Opaque per-session ID, when present in the hook payload — enables joins with `session-digest.jsonl` |

- **Emitter:** `hooks/lib/boundary_events.py::emit_boundary_event()`, called from `destructive_guard.py`, `verify_guard.py`, `pre_commit_review.py`, `telemetry.py` (intervention keywords), and the mechanically-adopted guards (`pre_tool_guard.py`, `context_ceiling_guard.py`, `bash_retry_guard.py`, `refactor_test_freeze_guard.py`, `refactor_test_bash_guard.py`, `refactor_test_revert_guard.py` (decision `revert`, #906), `contract_version_guard.py`, `mutation_testing_smoke_gate.py`, `mutation_gate.py`, `tdd_guard.py`).
- **Consent:** ALWAYS-ON — not gated by `DEV_TEAM_TELEMETRY`. Local-only, rule-IDs-only safety/accountability channel; no observability holes by design.
- **Fail-open:** every exception in the emit helper is swallowed — never changes the calling hook's exit code, stdout, or stderr.
- **Consumers:** `skills/session-review/SKILL.md`, `skills/harness-audit/SKILL.md`, `agents/session-analysis.md`, `skills/cost-report/`, future `agent-telemetry` cross-machine aggregation (#178).

---

## `telemetry.jsonl`

Opt-in usage beacon: which slash commands / skills get invoked, and whether
the pre-commit review gate fired or was bypassed.

| Field | Type | Values / source |
|---|---|---|
| `ts` | string | ISO-8601 UTC |
| `event` | string enum | `command` \| `skill` \| `gate` |
| `name` | string | Grammar-matched slash-command name, skill name, or `pre-commit-review` |
| `outcome` | string | `invoked` \| `fired` \| `bypassed` |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |

- **Emitter:** `hooks/telemetry.py::_emit()`.
- **Consent:** opt-in — `DEV_TEAM_TELEMETRY=on` env var, or `<cwd>/.claude/telemetry.json` `{"enabled": true}`. Off by default; nothing recorded, nothing leaves the machine.
- **Consumers:** `skills/telemetry/SKILL.md`, `scripts/session_extract.py`.

---

## `cost-metering.jsonl`

Per-session token/cost summary, incrementally accumulated from the
transcript on each `Stop` hook fire.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `transcript` | string | Transcript file basename (not full path) |
| `total` | object | Aggregated token counts + `cost_usd` + `messages` across the session |
| `by_model` | object | Per-model slim breakdown: `cost_usd`, `input_tokens`, `output_tokens` |
| `by_thread` | object | Per-thread slim breakdown, same shape as `by_model` |
| `by_agent_type` | object | Per-agent-type slim breakdown, same shape as `by_model`: `main` for main-loop turns; sidechain turns keyed by subagent type via `attributionAgent` or the Task-dispatch join; honest `unattributed` bucket when neither signal exists (#1094) |

- **Emitter:** `hooks/cost_meter.py` (wrapper) → `hooks/lib/cost_meter.py::cmd_record()`.
- **Consent:** unconditional (local-only cost accounting).
- **Consumers:** `skills/cost-report/SKILL.md`, `skills/harness-audit/SKILL.md`, `cmd_regression`/`cmd_pace` in the same library.

---

## `artifact-usage.json`

Not JSONL — a single JSON object keyed by skill/agent name, upserted on
every invocation.

| Field | Type | Values / source |
|---|---|---|
| `<skill_name>.use_count` | integer | Cumulative invocation count |
| `<skill_name>.last_used_at` | string | ISO-8601 UTC of the most recent invocation |
| `<skill_name>.lifecycle` | string | `active` (set on creation; other lifecycle states are assigned externally by `/artifact-lifecycle`) |

- **Emitter:** `hooks/telemetry.py::_upsert_artifact_usage()` (atomic rewrite via tempfile + `os.replace`).
- **Consent:** follows `telemetry.jsonl`'s opt-in gate, with an independent explicit-off switch: `.claude/telemetry.json` `{"enabled": false}` disables usage tracking specifically.
- **Consumers:** `skills/artifact-lifecycle/SKILL.md`.

---

## `gate-bypass-audit.jsonl`

Accountability record for `git commit --no-verify`/`-n` bypasses of the
pre-commit review gate.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `branch` | string | Current git branch |
| `triggeredBy` | string | Bypass flag name (`--no-verify` or `-n`) |
| `reason` | string | Value of `GATE_BYPASS_REASON` — human/agent-authored, required to be non-empty |
| `stagedFileCount` | integer | Count of staged files at bypass time |
| `pluginVersion` | string | From `.claude-plugin/plugin.json` |

- **Emitter:** `hooks/pre_commit_review.py::_record_bypass_audit()`.
- **Consent:** unconditional — accountability record for an actively-chosen bypass, not passive usage telemetry.
- **Consumers:** `skills/code-review/SKILL.md`, `docs/code-review-process.md`.

---

## `gate-bypass.jsonl`

Accountability record for `MUTATION_SMOKE_GATE_SKIP=1` bypasses of the
mutation-testing smoke gate. Distinct stream from `gate-bypass-audit.jsonl`
above (different gate, different hook).

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC (`Z`-suffixed) |
| `hook` | string | Always `mutation-testing-smoke-gate` |
| `command_hash` | string | First 16 hex chars of `sha256(raw_command)` — the raw command is never logged |
| `cwd` | string | Payload cwd |

- **Emitter:** `hooks/mutation_testing_smoke_gate.py::log_bypass_audit()`.
- **Consent:** unconditional.
- **Consumers:** `skills/mutation-testing/SKILL.md`.

---

## `config-changelog.jsonl`

Audit trail for `/feedback-learning` config changes and human-oversight
protocol events (approval / override / pause / stop).

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `type` | string enum | `amend` \| `approval` \| `override` \| `pause` \| `stop` (feedback-learning change types, or oversight event types) |
| `trigger` | string | `user` (who/what triggered the change) |
| `description` | string | Human/agent-authored summary of what happened and why (deliberate audit note, not incidental free text) |
| `file_modified` | string, optional | Config file touched (feedback-learning changes) |
| `section_modified` | string, optional | Section within the file |
| `previous_value` / `new_value` | string, optional | Before/after values |
| `approved_by` | string, optional | Who approved the change |

- **Emitter:** `/feedback-learning` skill (model-authored append) and `/human-oversight-protocol` skill.
- **Consent:** unconditional (append-only governance record).
- **Consumers:** `skills/feedback-learning/SKILL.md`, `skills/human-oversight-protocol/SKILL.md`, `skills/governance-compliance/SKILL.md`.

---

## `session-digest.jsonl`

Trend digest from `/session-review` (backed by `scripts/session_extract.py`):
aggregate counts only, no file names, prompts, command strings, or code.

| Field | Type | Values / source |
|---|---|---|
| `recorded_at` | string | UTC ISO-8601 of the run |
| `sessions`, `transcripts` | integer | How many sessions/transcripts the digest covered |
| `tokens` | object | Input/output/cache token totals |
| `cost_usd`, `cache_hit_ratio` | number | Session cost and cache-read efficiency |
| `rework` | object | `failed_edits`, `repeated_file_edits`, `retried_bash_commands`, `repeated_verify_runs`, `permission_denials`, `compaction_events` |
| `accuracy` | object | `tool_calls`, `tool_error_rate`, `user_correction_turns` |
| `utilization` | object | `skills_invoked`, `agents_invoked`, `never_observed_skills`, `never_observed_agents` |

- **Emitter:** `/session-review` skill via `scripts/session_extract.py`.
- **Consent:** unconditional (aggregate counts only, no file/prompt/command content).
- **Consumers:** `skills/harness-audit/SKILL.md` (joins with self-reported task logs), `agents/session-analysis.md`.

---

## `review-value.jsonl`

Whether a `/build` inline review checkpoint actually changed anything —
counts and outcomes only, never code or file content.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `plan` | string | Plan file path |
| `slice` | string | Slice number |
| `step` | string | Step number (`N.M`) or `all` |
| `checkpoint` | string enum | `step` \| `slice` |
| `complexity` | string enum | `standard` \| `complex` |
| `agents_run` | array of string | Review agents dispatched |
| `issues_found`, `issues_fixed`, `fix_iterations` | integer | Counts |
| `outcome` | string enum | `no-op` \| `fixed` \| `escalated` |

- **Emitter:** `/build` skill (model-authored append, sub-step 7). Disable with `DEV_TEAM_REVIEW_VALUE=off`.
- **Consent:** unconditional when enabled (no code/file content recorded).
- **Consumers:** `skills/cost-report/SKILL.md`, `skills/harness-audit/SKILL.md`.

---

## `verify-log.jsonl`

Evidence that `/verify` actually ran (or was legitimately skipped) before a
`/build` slice with a runtime surface was marked complete. Schema modeled on
`review-value.jsonl`.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `plan` | string | Plan file path |
| `slice` | string | Slice number |
| `branch` | string | Current git branch |
| `files` | array of string | Changed runtime files in scope |
| `outcome` | string enum | `ran` \| `skipped` \| `failed-then-fixed` |
| `reason` | string, optional | Set when `outcome` is `skipped` (e.g. `"tests-only"`, `"docs-only"`) |

- **Emitter:** `/build` skill (model-authored append, sub-step 4.9).
- **Consent:** unconditional.
- **Consumers:** `scripts/progress_guardian.py --pre-pr` (fails closed on a runtime-surface change with no matching entry), `skills/performance-metrics/SKILL.md`.

---

## `override-audit.jsonl`

Audit trail for `/code-review --force --reason "<text>"`, which skips all
gates and the documentation-only short-circuit.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 |
| `branch` | string | Current git branch |
| `triggeredBy` | string | Always `--force` |
| `reason` | string | Value of `--reason` (required, human/agent-authored) |
| `targetFiles` | array of string | Files the forced review targeted |
| `gatesSkipped` | array of string | e.g. `["lint", "type-check", "secret-scan", "semgrep", "pipeline-red"]` |

- **Emitter:** `/code-review` skill (model-authored append, step 2).
- **Consent:** unconditional.
- **Consumers:** `skills/code-review/SKILL.md`, `docs/code-review-process.md`.

---

## `eval-variance.jsonl`

Multi-trial pass@k stability trend for `/agent-eval` fixtures.

| Field | Type | Values / source |
|---|---|---|
| `recorded_at` | string | ISO-8601 UTC |
| `schema` | string | `eval-variance/v1` |
| `trials` | integer | Number of trials in this run |
| `pairs_evaluated` | integer | Fixture/agent pairs evaluated |
| `flaky_count` | integer | Pairs that neither always passed nor always failed |
| `mean_pass_at_k` | number | Mean pass@k across evaluated agents |

- **Emitter:** `scripts/eval_variance.py --append`.
- **Consent:** unconditional (eval infra, not user-session telemetry).
- **Consumers:** `skills/agent-eval/SKILL.md`.

---

## `eval-ablation.jsonl`

Causal per-agent ablation evidence from `/agent-eval --ablation <agent>` (#868):
a controlled baseline-vs-ablated integration-tier delta (issues caught,
`testCommands` results, token cost), not accumulated usage data.

| Field | Type | Values / source |
|---|---|---|
| `schema` | string | `eval-ablation/v1` |
| `recorded_at` | string | ISO-8601 UTC |
| `ablated_agent` | string | Target agent name |
| `fixtures` | array of strings | Integration fixtures exercised |
| `model` | string | Model version(s) used for orchestrator/builder dispatch — deltas are model-dependent, always recorded |
| `baseline` | object | `{issues_caught, test_commands: [{command, exit_code}], tokens, grade}` — full roster arm |
| `ablated` | object | Same shape as `baseline` — roster-minus-target-agent arm |
| `delta` | object | `{issues_caught, test_commands_passed, tokens}` (ablated − baseline) |
| `verdict` | string | e.g. `"no measured impact — supports drop"` / `"agent is load-bearing — retain"` / `"baseline failed — inconclusive"` |

- **Emitter:** `scripts/eval_ablation.py --mode agent`.
- **Consent:** unconditional (eval infra, not user-session telemetry); opt-in/label-gated dispatch per the live-eval cost policy (#134) — the record is only ever written after an explicit operator-confirmed live run.
- **Consumers:** `skills/harness-audit/SKILL.md` (Step 3 drop-candidate recommendations cite the measured delta/verdict when a record exists).

---

## `refactor-freeze.jsonl`

Audit log for the tests-frozen-during-REFACTOR invariant (`#813`) — both the
enforcement decision and any fail-open diagnostic. Extended by `#906` with
`bash-freeze`, the preventive PreToolUse(Bash) sibling of `freeze`.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 |
| `hook` | string | `freeze` \| `bash-freeze` \| `revert` |
| `event` | string enum | `block` \| `fail-open` \| `revert` \| `remove` |
| `file` | string, optional | File path involved |
| `step` | string, optional | Plan step label |
| `reason` | string, optional | Fail-open diagnostic (existing precedent — internal-error text, not a rule ID; unchanged by #859) |

- **Emitter:** `hooks/refactor_test_freeze_guard.py::audit()`, `hooks/refactor_test_revert_guard.py` and `hooks/refactor_test_bash_guard.py` (both via the same `audit()` import).
- **Consent:** unconditional (fails open, audits itself).
- **Consumers:** none automated yet; inspected manually when the freeze invariant is investigated.

---

## `contract-version-guard-audit.jsonl`

Audit log for release-please's bypass of the security-primitives-contract
version-bump requirement.

| Field | Type | Values / source |
|---|---|---|
| `ts` | string | ISO-8601 UTC |
| `bypass` | boolean | Always `true` |
| `reason` | string | Always `release-please-actor` |
| `github_actor` | string | `$GITHUB_ACTOR` env value |
| `git_email` | string | `$GIT_AUTHOR_EMAIL` env value |

- **Emitter:** `hooks/contract_version_guard.py::_log_bypass()`.
- **Consent:** unconditional.
- **Consumers:** none automated yet; CI-only diagnostic trail.

---

## `learning-loop-state.json`

Not JSONL — a single current-value JSON file: a counter gating when
`session_learning_trigger.py` dispatches background session analysis.

| Field | Type | Values / source |
|---|---|---|
| `counter` | integer | Turns since the last dispatch |

- **Emitter:** `hooks/session_learning_trigger.py::_write_state()`.
- **Consent:** unconditional (internal scheduling state, no content).
- **Consumers:** `hooks/session_learning_trigger.py` itself (read on next fire).

---

## `pending-review.jsonl`

Queued findings from the background session-analysis dispatch, before
`/session-review` consumes them.

| Field | Type | Values / source |
|---|---|---|
| `queued_at` | string | ISO-8601 UTC |
| `source` | string | Always `session-learning-trigger` |
| `session_id` | string, optional | Session ID when available |
| `findings` | array of object | Each: `lever`, `evidence`, `target_artifact`, `proposed_change`, `route` |

- **Emitter:** background `claude --print` run dispatched by `hooks/session_learning_trigger.py::_dispatch_background_analysis()`, writing via `session-analysis` agent output.
- **Consent:** unconditional (dispatch happens automatically; content is model-authored analysis, not raw session data).
- **Consumers:** `/session-review` skill.

---

## `metrics/{date}-task-log.jsonl` (e.g. `2026-02-20-task-log.jsonl`)

Self-reported per-task completion log, one file per calendar date.

| Field | Type | Values / source |
|---|---|---|
| `timestamp` | string | ISO-8601 |
| (task-specific fields) | — | Tokens, cost, agents used, rework cycles, hallucination events — see `skills/performance-metrics/SKILL.md` for the full field list |

- **Emitter:** `/performance-metrics` skill (model-authored append at task completion).
- **Consent:** unconditional (self-reported, no raw content).
- **Consumers:** `skills/harness-audit/SKILL.md` (self-reported half of the harness-audit join, alongside `session-digest.jsonl`'s real-session half), `skills/governance-compliance/SKILL.md`.

---

## Adding a new stream

1. Name it `metrics/<name>.jsonl` (or `.json` for a single-current-value
   file) — one stream per concern, matching existing precedent.
2. Append-only, compact JSON (`separators=(",", ":")`) + trailing newline for
   JSONL streams.
3. Rule IDs / counts / enums only — never command text, prompt text, file
   contents, or incidental free text.
4. Add a section to this file with the same shape as the ones above
   (fields/types, emitter, consent gating, consumers) in the same PR that
   introduces the emitter — the coverage test in
   `tests/hooks/test_boundary_events.py` enforces this.

---

## `autoship-log.jsonl`

One entry per `/autoship` round, recording the outcome and cost of each automated ship attempt.

| Field | Type | Values / source |
|---|---|---|
| `logged_at` | string | ISO-8601 (UTC) — stamped by `autoship_log.py` |
| `round` | integer | Monotonically increasing round counter |
| `issues_attempted` | integer | Number of issues dispatched this round |
| `issues_shipped` | integer | Issues that reached a merged PR |
| `issues_blocked` | integer | Issues that required stakeholder input |
| `total_cost_usd` | number | Cumulative USD spend for this round |
| `outcome` | string | `"success"` \| `"convergence_failure"` \| `"cost_cap_reached"` \| `"unrecognized"` |

- **Emitter:** `hooks/lib/autoship_log.py` called from the `/autoship` skill.
- **Consent:** unconditional (cost/count aggregates only — no prompt text or file contents).
- **Consumers:** `/cost-report`, `/telemetry` (aggregate reporting).

---

## `workflow-states.jsonl`

**Added by #1166.** Event-sourced workflow lifecycle stream for orchestrated
flows (`/ship`, `/autoship`, `/build`): persists only state-*transition*
events. Current state and per-state dwell time are always **derived** by
replaying the stream for a given `session_id` — never stored — per the
event-sourcing discipline in the competitive analysis this issue is drawn
from. Canonical (informational, not enforced) lifecycle: `SPEC -> PLAN ->
BUILD -> REVIEW -> COMMIT -> PR`.

| Field | Type | Values / source |
|---|---|---|
| `ts` | string | ISO-8601 UTC `%Y-%m-%dT%H:%M:%SZ` |
| `workflow` | string | Orchestrated flow name, e.g. `ship`, `autoship`, `build` |
| `prior_state` | string, optional (`null` for the initial transition) | State the workflow was in before this transition |
| `new_state` | string | State the workflow is entering |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |
| `session_id` | string, optional | Opaque per-session ID — enables joins with `boundary-events.jsonl` and `cost-metering.jsonl` |

- **Emitter:** `hooks/lib/workflow_state.py::emit_state_transition()`, invoked via its `record` CLI subcommand as a model-authored append at each phase boundary in `/ship`, `/autoship`, and `/build` (same convention as `review-value.jsonl`/`verify-log.jsonl`).
- **Consent:** unconditional (workflow/state names + counts only — no prompt text or file contents).
- **Derivation:** `hooks/lib/workflow_state.py::derive_current_state()` and `compute_dwell_times()` (also exposed via the `report` CLI subcommand) replay a session's transitions — never a stored snapshot.
- **Consumers:** `skills/run-report/SKILL.md` (#1167), `skills/session-review/SKILL.md`, `skills/harness-audit/SKILL.md`, `skills/cost-report/SKILL.md`.
