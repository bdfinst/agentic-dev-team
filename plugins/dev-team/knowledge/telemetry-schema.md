# Telemetry Schema Reference

Every `.claude/metrics/*.jsonl` and `.claude/metrics/*.json` file the dev-team plugin writes,
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
cross-checks every `.claude/metrics/*.jsonl` / `.claude/metrics/*.json` path string referenced
in shipped code against this doc's coverage and fails on omission.

---

## `boundary-events.jsonl`

**Added by #859.** The boundary-level (policy-gateway) channel: every guard
hook's block/warn/bypass decision, plus human-intervention keywords. Extended
by #906 with a fifth decision, `revert`, for hooks that don't warn or block
but actively correct state after the fact. Extended again by #1461 with a
sixth decision, `record` — a **non-verdict, observational** entry: it does
not block, warn, bypass, intervene, or revert anything, it merely notes that
a genuine, registered review-agent dispatch occurred. Emitted by
`hooks/agent_dispatch_ledger.py` on every `Agent`/`Task` dispatch whose
`subagent_type` is a real, registered `agents/*-review.md` name (never a
fabricated/unregistered one — those are never written to the ledger at all).
This is a **high-frequency** entry (one per genuine review-agent dispatch,
not a rare guard trip like the other five decisions) — a consumer counting
"policy decisions" or "guard verdicts" from this stream must explicitly
exclude `record` rows, or it will badly overcount routine dispatch activity
as gate verdicts. `hooks/pre_pr_review.py`'s `.pr-review-passed` gate (#1886;
formerly `hooks/pre_commit_review.py`'s `.review-passed` gate on `git
commit` — that hook is now a documented no-op) reads this stream (via
`hooks/lib/review_gate_corroboration.py`) to corroborate that a
hash-matching gate write was backed by real, independent Agent-tool
dispatch — see that module's own docstring for its fail-**closed** posture,
the deliberate opposite of this stream's own fail-open write side.
Extended again by #1763 with a seventh decision, `dispatch-failure` — also
**non-verdict, observational**, mirroring `record`'s precedent, but the
opposite polarity: it notes that a dispatched review agent still failed to
return a contract-valid result after one retry. Emitted via
`hooks/lib/boundary_events.py`'s CLI (`--event dispatch-failure --agent
<name> --subject-hash <hash>`) from `skills/code-review/SKILL.md` Step 4;
`<name>` is validated against the registered review-agent set at write time
(with the same plugin-prefix normalization as `record`) — an unregistered
name is silently not recorded. Unlike `record`, `dispatch-failure` is
consumed only as NEGATIVE evidence: the gate veto in
`hooks/lib/review_gate_corroboration.py` / `hooks/pre_pr_review.py` (#1886;
`_dispatch_failure_verdict`, #1763) treats it as a reason to reject a
`.pr-review-passed` write, never as corroboration for one. A forged/hand-run
`dispatch-failure` event can only
ever cause a false rejection, never a false pass — the opposite forgery
direction from `record`, which is why this decision (unlike `record`) is
safely reachable from the CLI's closed `--event` vocabulary.

| Field | Type | Values / source |
| --- | --- | --- |
| `ts` | string | ISO-8601 UTC `%Y-%m-%dT%H:%M:%SZ` |
| `hook` | string | Emitting hook's module name, e.g. `destructive_guard`, `verify_guard`, `pre_pr_review` (the review-corroboration gate, #1886; `pre_commit_review` is now a documented no-op and emits nothing), `telemetry`, `agent_dispatch_ledger` — or `code-review` for the CLI-emitted events (`--event doc-only`/`single-agent`/`dispatch-failure`), which carry the invoking skill's name rather than a hook module name |
| `tool` | string | Hooked tool/event: `Bash`, `Write`, `Edit`, `Skill`, `Agent`, `UserPromptSubmit` |
| `decision` | string enum | `block` \| `warn` \| `bypass` \| `intervention` \| `revert` \| `record` \| `dispatch-failure` |
| `matched_rule` | string | Rule ID from a closed vocabulary (pattern ID, hook-defined constant, bypass flag name, intervention keyword, or — for `record`/`dispatch-failure` — the dispatched review-agent's registered name) — never free text |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |
| `session_id` | string, optional | Opaque per-session ID, when present in the hook payload — enables joins with `session-digest.jsonl` |
| `subject_hash` | string, optional | `review_gate_hash()` value (#1461) binding this event to the staged content it corroborates. A hex digest, not free text |
| `subject_hash_normalized` | string, optional | `normalized_gate_hash()` value (#1627) — the same binding computed after doc-hunk and indentation normalization. Stamped by `agent_dispatch_ledger.py` alongside `subject_hash`, and read by the gate's cosmetic-delta carry-forward lens. Absent on events written before #1627, which therefore never match on the normalized path. **The digest ALGORITHM has changed twice since** — #1638 (heredoc-body marking plus whole-file `--unified=100000` context) and #1660/#1661/#1662/#1663 (further grammars, a hunk-start guard, and a payload cap), each of which changes the computed VALUE for any changeset touching an affected extension. An event recorded by an earlier plugin version therefore never matches after an upgrade. This fails closed — one lost carry-forward, one extra dispatch — and is not a correctness bug, but it is why a version bump can look like a spurious re-review |

**`cosmetic-delta-carry-forward` (#1627, historical).** `pre_commit_review.py`
used to emit this `bypass`-decision event every time the OLD commit-time gate
passed a commit whose raw staged hash mismatched but whose normalized hash
matched. #1886 moved the gate to `gh pr create` and deliberately did NOT
carry this lens forward — the friction it existed to relieve (a whitespace-only
re-stage forcing a fresh review-agent dispatch before the NEXT commit) was a
direct consequence of gating every commit; a gate that fires once, at
PR-creation time, against the branch's cumulative diff, does not have that
problem. `hooks/pre_pr_review.py` never emits this event. Existing rows in
`boundary-events.jsonl` from before the migration remain valid history.

- **Emitter:** `hooks/lib/boundary_events.py::emit_boundary_event()`, called from `destructive_guard.py`, `verify_guard.py`, `pre_pr_review.py` (#1886), `telemetry.py` (intervention keywords), `agent_dispatch_ledger.py` (decision `record`, #1461), the mechanically-adopted guards (`pre_tool_guard.py`, `context_ceiling_guard.py`, `bash_retry_guard.py`, `refactor_test_freeze_guard.py`, `refactor_test_bash_guard.py`, `refactor_test_revert_guard.py` (decision `revert`, #906), `contract_version_guard.py`, `mutation_testing_smoke_gate.py`, `mutation_gate.py`, `tdd_guard.py`), and `boundary_events.py`'s own CLI (`--event dispatch-failure`, decision `dispatch-failure`, #1763) invoked from `skills/code-review/SKILL.md` Step 4. `--event gate-ran --verdict {allow,block,errored}` (decision `record`, `matched_rule` of `gate-ran-<verdict>`, #2037) is invoked from the repo-root `.husky/pre-commit` git hook — the real, git-native pre-commit gate (distinct from `pre_pr_review.py`, a Claude-Code-level PreToolUse hook gating `gh pr create`) — at every exit point, success or failure alike, so `scripts/session_extract.py` can correlate a commit-attempt Bash record against a nearby `gate_ran` event and classify the previously-unmeasured "the gate silently never ran" population (`gate_ran_absent`) apart from a genuine internal failure (`gate_ran_errored`). This event carries no `session_id` in practice — a real git hook has no Claude Code session_id to attach — so correlation is by time proximity, not session join; see `scripts/session_extract.py`'s "gate-run correlation (#2037)" section.
- **Consent:** ALWAYS-ON — not gated by `DEV_TEAM_TELEMETRY`. Local-only, rule-IDs-only safety/accountability channel; no observability holes by design.
- **Fail-open:** every exception in the emit helper is swallowed — never changes the calling hook's exit code, stdout, or stderr.
- **Consumers:** `skills/session-review/SKILL.md`, `skills/harness-audit/SKILL.md`, `agents/session-analysis.md`, `skills/cost-report/`, `skills/run-report/SKILL.md` (#1167), `hooks/lib/review_gate_corroboration.py` (#1461 `record` rows; #1763 also reads `dispatch-failure` rows as negative evidence for the gate veto), future `agent-telemetry` cross-machine aggregation (#178).

---

## `telemetry.jsonl`

Opt-in usage beacon: which slash commands / skills get invoked, and whether
the pre-commit review gate fired or was bypassed.

| Field | Type | Values / source |
| --- | --- | --- |
| `ts` | string | ISO-8601 UTC |
| `event` | string enum | `command` \| `skill` \| `gate` |
| `name` | string | Grammar-matched slash-command name, skill name, or `pre-pr-review` (#1886 — the gate moved from `git commit` to `gh pr create`) |
| `outcome` | string | `invoked` \| `fired` \| `bypassed` |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |

- **Emitter:** `hooks/telemetry.py::_emit()`. Written to `~/.claude/metrics/telemetry.jsonl` — home-scoped, out of the project entirely (#1405/#1406), never a project's own `metrics/`.
- **Consent:** opt-in — `~/.claude/telemetry.json` `{"enabled": true}`, home-scoped only. `DEV_TEAM_TELEMETRY` and a project-scoped `<cwd>/.claude/telemetry.json` are now inert (one-time-per-session stderr notice only, no effect on consent). Off by default; nothing recorded, nothing leaves the machine.
- **Consumers:** `skills/telemetry/SKILL.md`, `scripts/session_extract.py`.

---

## `cost-metering.jsonl`

Per-session token/cost summary, incrementally accumulated from the
transcript on each `Stop` hook fire.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `transcript` | string | Transcript file basename (not full path) |
| `total` | object | Aggregated token counts + `cost_usd` + `messages` across the session |
| `by_model` | object | Per-model slim breakdown: `cost_usd`, `input_tokens`, `output_tokens` |
| `by_thread` | object | Per-thread slim breakdown, same shape as `by_model` |
| `by_agent_type` | object | Per-agent-type slim breakdown, same shape as `by_model`: `main` for main-loop turns; sidechain turns keyed by subagent type via `attributionAgent` or the Task-dispatch join; honest `unattributed` bucket when neither signal exists (#1094) |

- **Emitter:** `hooks/cost_meter.py` (wrapper) → `hooks/lib/cost_meter.py::cmd_record()`.
- **Consent:** gated by `telemetry_consent.is_enabled()` (`~/.claude/telemetry.json` `{"enabled": true}`, home-scoped) — no longer unconditional as of Slice 2 (#1406).
- **Consumers:** `skills/cost-report/SKILL.md`, `skills/harness-audit/SKILL.md`, `cmd_regression`/`cmd_pace` in the same library, `skills/run-report/SKILL.md` (#1167, best-effort only — see that skill's Join limitations section: this stream has no `session_id` field).

---

## `phase-markers.jsonl`

Per-phase context-pollution markers (#1520), one row appended at each `/handoff`
(a phase boundary). Distinct stream from `cost-metering.jsonl` — deliberately
kept out of that log's incremental `record` state so this additive dimension
never touches the security-sensitive hot path.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `transcript` | string | Transcript file basename (not full path) |
| `phase` | string | Phase label — the first `/handoff` args token when sane, else `handoff` (or `unlabeled` for a direct library call) |
| `resident_tokens` | int | Main-loop context occupancy at the boundary: the most-recent non-sidechain turn's `input + cache_read + cache_creation` |
| `spent_output_cumulative` | int | Cumulative main-loop `output_tokens` across the session up to this boundary (monotonic; `phase-report` deltas it into per-phase spend) |

- **Emitter:** `hooks/phase_marker.py` (PostToolUse:Skill, filters to `handoff`) → `hooks/lib/cost_meter.py::cmd_phase_mark()`.
- **Consent:** gated by `telemetry_consent.is_enabled()`; shares the cost meter's `DEV_TEAM_COST_METER=off` opt-out.
- **Consumers:** `skills/cost-report/SKILL.md` (§ Context pollution, via `phase-report`), `skills/harness-audit/SKILL.md` (§ Analyze orchestration complexity).

---

## `artifact-usage.json`

Not JSONL — a single JSON object keyed by skill/agent name, upserted on
every invocation.

| Field | Type | Values / source |
| --- | --- | --- |
| `<skill_name>.use_count` | integer | Cumulative invocation count |
| `<skill_name>.last_used_at` | string | ISO-8601 UTC of the most recent invocation |
| `<skill_name>.lifecycle` | string | `active` (set on creation; other lifecycle states are assigned externally by `/artifact-lifecycle`) |

- **Emitter:** `hooks/telemetry.py::_upsert_artifact_usage()` (atomic rewrite via tempfile + `os.replace`). Written to `~/.claude/metrics/artifact-usage.json` — home-scoped, out of the project entirely (#1405/#1406), never a project's own `metrics/`.
- **Consent:** follows `telemetry.jsonl`'s opt-in gate (`~/.claude/telemetry.json` `{"enabled": true}`, home-scoped). The project-scoped explicit-off switch this section used to document (a project-level `.claude/telemetry.json` `{"enabled": false}` disabling usage tracking specifically) no longer exists — project-scoped `.claude/telemetry.json` is inert entirely, same as `telemetry.jsonl`'s row above.
- **Consumers:** `skills/artifact-lifecycle/SKILL.md`.

---

## `gate-bypass-audit.jsonl`

Accountability record for a bypass of the review-corroboration gate. #1886
moved the gate from `git commit` to `gh pr create`; this stream now carries
`hooks/pre_pr_review.py`'s `PR_GATE_BYPASS_REASON` bypasses.
`hooks/pre_commit_review.py` is now a documented no-op and no longer writes
to this stream — historical rows from before the migration
(`triggeredBy: "--no-verify"`/`"-n"`) remain valid history but no new ones
are produced.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `branch` | string | Current git branch |
| `triggeredBy` | string | `PR_GATE_BYPASS_REASON` (current); `--no-verify`/`-n` (historical, pre-#1886) |
| `reason` | string | Value of `PR_GATE_BYPASS_REASON` (current) / `GATE_BYPASS_REASON` (historical) — human/agent-authored, required to be non-empty |
| `stagedFileCount` | integer | Count of files in the branch diff at bypass time (historical rows: staged files at commit time) |
| `pluginVersion` | string | From `.claude-plugin/plugin.json` |

- **Emitter:** `hooks/pre_pr_review.py::_record_bypass_audit()` (#1886). `hooks/pre_commit_review.py::_record_bypass_audit()` was the historical emitter, now removed along with the rest of that module's gating logic.
- **Consent:** unconditional — accountability record for an actively-chosen bypass, not passive usage telemetry.
- **Consumers:** `skills/code-review/SKILL.md`, `docs/code-review-process.md`.

---

## `gate-bypass.jsonl`

Accountability record for `MUTATION_SMOKE_GATE_SKIP=1` bypasses of the
mutation-testing smoke gate. Distinct stream from `gate-bypass-audit.jsonl`
above (different gate, different hook).

| Field | Type | Values / source |
| --- | --- | --- |
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
| --- | --- | --- |
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
| --- | --- | --- |
| `recorded_at` | string | UTC ISO-8601 of the run |
| `plugin_version` | string | The `dev-team` plugin's `.claude-plugin/plugin.json` version active when this record was produced (`"unknown"` if the manifest couldn't be read), #1471. Lets consumers tell a friction already fixed in a newer version apart from one that's still current — see `--version-scope` below |
| `sessions`, `transcripts` | integer | How many sessions/transcripts the digest covered |
| `tokens` | object | Input/output/cache token totals |
| `cost_usd`, `cache_hit_ratio` | number | Session cost and cache-read efficiency |
| `rework` | object | `failed_edits`, `repeated_file_edits`, `retried_bash_commands`, `repeated_verify_runs`, `permission_denials`, `compaction_events` |
| `accuracy` | object | `tool_calls`, `tool_error_rate`, `user_correction_turns` |
| `utilization` | object | `skills_invoked`, `agents_invoked` (agent RUNS), `agent_dispatches` (Agent/Task tool calls), `never_observed_skills`, `never_observed_agents` |

`session-digest/v2` (#1994) counts dispatched agents' own transcripts for the
first time, so token/tool-call/rework totals jump against v1, and
`retried_bash_commands` / `repeated_verify_runs` moved from a session-keyed to
a per-thread basis. Records from the two eras are not comparable; split on
`schema` before trending.

- **Emitter:** `/session-review` skill via `scripts/session_extract.py`.
- **Consent:** unconditional (aggregate counts only, no file/prompt/command content).
- **Enforcement (#2045):** every name/label-shaped field this stream (and the
  shipped `extract_session_report.py` downstream report) emits passes
  through `plugins/dev-team/scripts/lib/session_log/redact.redact()` — the
  one function both extractors route file basenames, project labels, skill
  names, agent names, and model ids through before writing them out.
  Previously this line's promise was a convention restated independently at
  each call site; `redact()` is the single enforcement point, pinned by
  `tests/scripts/test_session_report_golden.py::test_no_sentinel_leaks_in_either_golden`
  against a corpus seeding real prompt text, source code, a full shell
  command string, and absolute POSIX/Windows paths.
- **Consumers:** `skills/harness-audit/SKILL.md` (joins with self-reported task logs), `agents/session-analysis.md`.
- **Version tagging (#1471):** `plugin_version` is also carried on the per-session `session-sync/v1`/`session-sync/v2` records synced by `--sync-out` (used by `--rollup`/`--escalate`/`--correlate`) and on the single-shot digest itself — every one of these tags reflects the plugin version active on the machine *at extraction time*, not the version that was necessarily active during the original raw session (transcripts carry no version tag of their own to correlate against).
- **Version scoping (#1480):** `session_extract.py --rollup`/`--escalate`/`--correlate` accept `--version-scope {all,current-and-previous}` (default `all`, unbounded history). `current-and-previous` drops any record whose `plugin_version` isn't the currently-installed version or the version immediately before it *as observed in the digests being read* (there is no release-history lookup) — records with no `plugin_version` at all (pre-#1471 data) are dropped too, since they can't be proven current. The result gains a `version_window` field (the concrete versions included; `[]` when unscoped). `/session-review` defaults to local-only; its `--cross-machine` opt-in always applies `current-and-previous` scoping (see its SKILL.md) — the skill itself never exposes an unscoped cross-machine mode. Unbounded history across every version remains available only via a direct `session_extract.py --rollup ... --version-scope all` invocation (the CLI default), outside the skill.

---

## `review-value.jsonl`

Whether a `/build` inline review checkpoint actually changed anything —
counts and outcomes only, never code or file content.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `plan` | string | Plan file path |
| `slice` | string | Slice number |
| `step` | string | Step number (`N.M`) or `all` |
| `checkpoint` | string enum | `step` \| `slice` \| `backstop` (the Step-6 backstop pass, #1962) |
| `complexity` | string enum | `standard` \| `complex` |
| `agents_run` | array of string | Review agents dispatched |
| `issues_found`, `issues_fixed`, `fix_iterations` | integer | Counts |
| `severity_breakdown` | object | `{errors, warnings, suggestions}` counts (same enum as `/code-review`); the three sum to `issues_found`. Lets `/harness-audit` Step 3 flag mostly-minor lenses (#1256). Absent on pre-#1256 rows |
| `source` | string enum | Row provenance: `build-checkpoint` (fix-applying `/build` inline checkpoint) \| `build-backstop` (fix-applying `/build` Step-6 backstop pass, #1962) \| `code-review` (read-only standalone review) \| `harness` (the `evals/code-review-benchmark/` replay harness — #2051, see below). **Absent = `build-checkpoint`** (back-compat). `/harness-audit` Step 4 excludes `code-review` rows from fix-rate drop-candidate logic (#1257); `build-backstop` rows are fix-applying and stay in it |
| `diff_shape` | string enum | Shape of the reviewed diff: `test-only` (every changed file provably a test per `knowledge/test-file-indicators.md`) \| `mixed` (anything else). Classified by `skills/code-review/scripts/change_shape.py`'s `isTestOnly`, never by eye; include-biased, so `test-only` is never over-claimed. Lets `/harness-audit` split per-lens outcomes by diff shape — the evidence a test-only lens gate waits on (#1964). Absent on pre-#1964 rows |
| `outcome` | string enum | `no-op` \| `fixed` \| `escalated` \| `skipped` (backstop only — suppressed by `--backstop-review=skip`; never counted in a rate, #1962) |

- **Emitter:** `/build` skill (model-authored append, sub-step 7) writes `source: "build-checkpoint"` for inline checkpoints and, from Step 6, `source: "build-backstop"` for the backstop pass (#1962). Disable with `DEV_TEAM_REVIEW_VALUE=off`.
- **Consent:** unconditional when enabled (no code/file content recorded).
- **Consumers:** `skills/cost-report/SKILL.md`, `skills/harness-audit/SKILL.md`.
- **Provenance (#1257):** fix-rate ROI is only meaningful for fix-applying rows. A read-only review that never applies fixes (`source: "code-review"`) always has `issues_fixed: 0`; Step 4 must not read that as a zero-value drop candidate — it reports finding-rate for those instead.

### Round rows — `source: "code-review"` with a `round` field (#1624)

`/code-review` appends one row **per dispatch round** (round 1 = the initial
panel; each fix-loop iteration's re-dispatch set is one further round), so

# 1623's "is this agent's dispatch frequency value or churn?" becomes

answerable. Written by `skills/code-review/scripts/review_round_log.py`.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `source` | string enum | Always `code-review` for these rows |
| `round` | integer | 1 = initial panel; each fix-loop re-dispatch set increments. **Presence of this field is what distinguishes a round row** from the original whole-run `code-review` row |
| `agents_run` | array of string | Registered review agents dispatched this round (sorted, deduped) |
| `findings_new` | integer | Findings whose signature was not present in a prior round (signature identity: #1625). The round-row analogue of `issues_found` |
| `findings_carried` | integer | Prior-round signatures that survived this round's fix attempt |
| `severity_breakdown` | object | `{errors, warnings, suggestions}` over `findings_new`; same enum as the `/build` rows |
| `fix_provenance_new` | integer | How many of `findings_new` fall inside the line ranges the **previous** round's fix touched — the judgment-free "the fix introduced it" signal. Computed by unified-diff interval math, never by model judgment. Always `0` for `round: 1` (no preceding fix) |
| `dispatch_purpose` | string enum | `discovery` (a panel looking for new problems) \| `verification` (confirming a specific fix, #1628) \| `closing` (the scoped gate-closing pass, #1626) |
| `outcome` | string enum | `no-op` \| `fixed` \| `escalated` — same enum as the `/build` rows |

- **Emitter:** `/code-review` (steps 5b-i and 6a) via `review_round_log.py`.
- **Consent:** **unconditional** — written to `.claude/metrics/` like `boundary-events.jsonl`, *not* gated behind `~/.claude/telemetry.json` the way `/build`'s rows are. Rationale (#1624 design item 2): this is the same class of local, counts-only operational stream the commit gate itself already depends on, and consent-gating it would make #1623's success criteria depend on consent being enabled per dev machine. Rows carry counts, agent names, and enum values only — no file paths, code, or finding text.
- **Consumers:** `skills/harness-audit/SKILL.md` Step 4a (churn ratio, per-agent discovery-vs-verification split, gate recidivism).
- **Backstop rows (#1962).** `source: "build-backstop"` marks `/build`'s Step-6 pass — the one review layer whose files an inline checkpoint already reviewed in the same run. It is fix-applying (the `--internal` panel runs the review-fix loop), so it belongs in fix-rate analysis alongside `build-checkpoint`; what it exists to answer is whether that duplicated layer is ~all `no-op`, which is the evidence `/build`'s `--backstop-review=skip` flag waits on. `outcome: "skipped"` marks a backstop suppressed by that flag: recorded so the suppression is visible in the same stream, and excluded from every rate because it never ran.
- **Reconciling the `source` values.** `build-checkpoint` and `build-backstop` rows are fix-applying and carry `plan`/`slice`/`step`/`checkpoint`/`complexity`/`issues_found`/`issues_fixed`/`fix_iterations`. `code-review` rows are read-only; those with a `round` field use the round schema above. A consumer wanting "how many issues did this row surface" should read `(.issues_found // .findings_new)`, which covers all three shapes.

### Harness rows — `source: "harness"` (#2051)

Written by `evals/code-review-benchmark/runner.emit_review_value_rows()` —
the `/code-review` **replay harness** (#821), not a live session. One row
per lens per dispatch, written straight from the parsed `/code-review
--json` payload's `agents[]` list — by mechanism, not by agent instruction
— so every dispatched lens gets a row regardless of outcome, including a
lens that found nothing. This is the fix for the collection bias #2019/
#1512 documented in the live writers above.

| Field | Type | Values / source |
| --- | --- | --- |
| `agents_run` | array of string | Always exactly one lens name — one row per lens, not per dispatch batch |
| `issues_found` | integer | Count of that lens's issues this dispatch |
| `severity_breakdown` | object | `{errors, warnings, suggestions}`, same enum as the live rows |
| `outcome` | string | Always `"no-op"` — the harness is read-only and never applies a fix |
| `diff_shape` | string enum | `test-only` \| `mixed`, same classifier as the live rows; the recorded-diff adapter (below) is what actually supplies real `test-only` cases |
| `dataset` | string | `defects4j` \| `bugsjs` \| `recorded-diff` |
| `project`, `bug_id` | string | The benchmark case's identifiers (not a `/build` plan/slice/step — a structurally different key space) |

- **Emitter:** `runner.emit_review_value_rows()`, called from `runner.run_case()` and `runner.run_recorded_diff_case()` after a dispatch's `--json` payload parses successfully. Never called for an unparseable dispatch — that failure is already captured by the harness's own `skipped.jsonl`.
- **File location, deliberately not `.claude/metrics/`.** Rows land in the harness's own results directory (`evals/code-review-benchmark/results/review-value.jsonl` by default, `--results-dir` elsewhere) — never the live metrics tree. This is a structural guarantee against pooling, on top of the `source: "harness"` label itself: even a caller reading the wrong file could not accidentally merge harness rows into the live population, because they are not in the same file.
- **Consumers:** `skills/harness-audit/SKILL.md` §4b, which reads this stream as a separate, explicitly-labelled population and must never merge it into Step 3/4's live-row computations.
- **Recorded-diff adapter (#2051).** `adapters/recorded_diff_adapter.py` supplies `dataset: "recorded-diff"` cases from saved diffs (most usefully real `/test-improve` Phase-5 diffs) — the only source that can give this stream a genuine `diff_shape: "test-only"` row, since Defects4J/BugsJS are real production bug fixes and structurally cannot be test-only.

---

## `contract-failures.jsonl`

Diagnostic record for a review-agent output that fails the shared JSON
contract (`knowledge/review-agent-output-contract.md`) — the gap #1998
closes. Session-report analysis found 18.2% of review-agent outputs
discarded silently, with no record of which agent, what it returned, or
why it didn't parse; today's alternative to this stream is nothing.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `agent` | string | Name of the review agent whose output failed validation |
| `shape` | string enum | `empty` \| `truncated` \| `malformed-json` \| `schema-drift` \| `not-json` — the closed set `validate_review_output.FAILURE_SHAPES` exports. `validate_review_output.py` also recognizes `clean`/`fenced`/`prose-preamble` (`SUCCESS_SHAPES`), but those three name *successful* extraction (the JSON was found and matched the contract) and so never appear as `shape` in a failure row — a successfully-extracted object that then fails schema validation is logged as `schema-drift`, not the extraction shape that found it. `malformed-json` is distinct from `truncated`: a balanced `{...}` object (unquoted keys, a trailing comma, a Python-repr dict) that still fails to parse is `malformed-json`; a `{` that never balances back to depth zero before EOF is `truncated` |
| `extraction` | string enum, nullable | Set whenever a JSON-shaped candidate was actually recovered before failing — i.e. `shape` is `schema-drift` or `malformed-json` — naming which of `clean`/`fenced`/`prose-preamble` recovered it, so that information survives the downgrade instead of being discarded. `null` for `empty`/`truncated`/`not-json` — no candidate was ever recovered for those |
| `error` | string | The specific validation/parse error (e.g. a `JSONDecodeError` message, or `status='ok' not one of [...]`), after the same secret-redaction pass as `raw_prefix` and capped at 256 characters — `_validate_schema` interpolates agent-controlled values into this string, so it needs the same two controls |
| `raw_prefix` | string | First 200 characters of the agent's raw output, **after** a secret-redaction pass (`validate_review_output._redact()`: this repo's canonical hardcoded-key pattern from `knowledge/owasp-detection.md`, plus common vendor token prefixes). Deliberate, capped exception to this file's "never incidental free text" default (mirroring `gate-bypass-audit.jsonl`'s `reason` field) — without seeing what was actually returned, the failure shapes #1998 exists to classify cannot be told apart. AI-authored review-agent output, which may quote repository source verbatim — including any secret present in the reviewed diff, since a lens's own job is to find and quote such things — so this is a transitive channel for repo content, not a claim that the text is free of it; the redaction pass is the actual control, the 200-char cap only bounds volume |

- **Emitter:** `skills/code-review/scripts/validate_review_output.py::log_failure()`, called once per non-contract-valid agent result during `/code-review` step 4's dispatch-failure handling.
- **Consent:** unconditional, matching `boundary-events.jsonl` — this is the same class of local, counts-and-diagnostics operational stream the commit gate itself already depends on.
- **Consumers:** `skills/code-review/scripts/contract_failure_report.py`, which joins this stream against `boundary-events.jsonl`'s dispatch counts to report a real per-agent failure *rate* (not just a count) for #1980/#1982 to read before citing any `$/finding` figure.

---

## `verify-log.jsonl`

Evidence that the project's own test/verification tooling actually exercised
the change end-to-end (or was legitimately skipped) before a `/build` slice
with a runtime surface was marked complete. Schema modeled on
`review-value.jsonl`.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC |
| `plan` | string | Plan file path |
| `slice` | string | Slice number |
| `branch` | string | Current git branch |
| `files` | array of string | Changed runtime files in scope |
| `outcome` | string enum | `ran` \| `skipped` \| `failed-then-fixed` |
| `reason` | string, optional | Set when `outcome` is `skipped` (e.g. `"tests-only"`, `"docs-only"`) |

- **Emitter:** `/build` skill (model-authored append, sub-step 4.9).
- **Consent:** unconditional.
- **Consumers:** `${CLAUDE_PLUGIN_ROOT}/scripts/progress_guardian.py --pre-pr` (fails closed on a runtime-surface change with no matching entry), `skills/performance-metrics/SKILL.md`.

---

## `override-audit.jsonl`

Audit trail for `/code-review --force --reason "<text>"`, which skips all
gates and the documentation-only short-circuit.

| Field | Type | Values / source |
| --- | --- | --- |
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
| --- | --- | --- |
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
| --- | --- | --- |
| `schema` | string | `eval-ablation/v1` |
| `recorded_at` | string | ISO-8601 UTC |
| `ablated_agent` | string | Target agent name |
| `fixtures` | array of strings | Integration fixtures exercised |
| `model` | string | Model version(s) used for orchestrator/builder dispatch — deltas are model-dependent, always recorded |
| `baseline` | object | `{issues_caught, test_commands: [{command, exit_code}], tokens, grade}` — full roster arm |
| `ablated` | object | Same shape as `baseline` — roster-minus-target-agent arm |
| `delta` | object | `{issues_caught, test_commands_passed, tokens}` (ablated − baseline) |
| `verdict` | string | e.g. `"no measured impact — supports drop"` / `"agent is load-bearing — retain"` / `"baseline failed — inconclusive"` |

- **Emitter:** `plugins/dev-team/scripts/eval_ablation.py --mode agent` (moved from `scripts/` in #1653).
- **Consent:** unconditional (eval infra, not user-session telemetry); opt-in/label-gated dispatch per the live-eval cost policy (#134) — the record is only ever written after an explicit operator-confirmed live run.
- **Consumers:** `skills/harness-audit/SKILL.md` (Step 3 drop-candidate recommendations cite the measured delta/verdict when a record exists).

---

## `refactor-freeze.jsonl`

Audit log for the tests-frozen-during-REFACTOR invariant (`#813`) — both the
enforcement decision and any fail-open diagnostic. Extended by `#906` with
`bash-freeze`, the preventive PreToolUse(Bash) sibling of `freeze`.

| Field | Type | Values / source |
| --- | --- | --- |
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
| --- | --- | --- |
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
| --- | --- | --- |
| `queued_at` | string | ISO-8601 UTC |
| `source` | string | Always `session-learning-trigger` |
| `session_id` | string, optional | Session ID when available |
| `findings` | array of object | Each: `lever`, `evidence`, `target_artifact`, `proposed_change`, `route` |

- **Emitter:** background `claude --print` run dispatched by `hooks/session_learning_trigger.py::_dispatch_background_analysis()`, writing via `session-analysis` agent output.
- **Consent:** unconditional (dispatch happens automatically; content is model-authored analysis, not raw session data).
- **Consumers:** `/session-review` skill.

---

## `.claude/metrics/{date}-task-log.jsonl` (e.g. `2026-02-20-task-log.jsonl`)

Self-reported per-task completion log, one file per calendar date.

| Field | Type | Values / source |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 |
| (task-specific fields) | — | Tokens, cost, agents used, rework cycles, hallucination events — see `skills/performance-metrics/SKILL.md` for the full field list |

- **Emitter:** `/performance-metrics` skill (model-authored append at task completion), via `hooks/task_completion_metrics.py`.
- **Consent:** gated by `telemetry_consent.is_enabled()` (`~/.claude/telemetry.json` `{"enabled": true}`, home-scoped) — no longer unconditional as of Slice 2 (#1406).
- **Consumers:** `skills/harness-audit/SKILL.md` (self-reported half of the harness-audit join, alongside `session-digest.jsonl`'s real-session half), `skills/governance-compliance/SKILL.md`.

---

## `gherkin-derive-effectiveness.jsonl`

Per-scenario roll-up correlating a `/gherkin-derive`-discovered surface with
whatever coverage/mutation-delta data the calling workflow already measured,
so there is a signal on whether BDD-derived scenarios track real
coverage/mutation movement (issue #1296). One record per scenario per
roll-up run — not deduplicated across runs, since coverage/mutation deltas
are re-measured every convergence iteration.

| Field | Type | Values / source |
| --- | --- | --- |
| `surface` | string, nullable | The discovered surface name/path from `gherkin.md`'s surface-inventory table |
| `discovery_source` | string, nullable | `openapi` \| `route` \| `test` \| `signature` (per `/gherkin-derive` Step 2), as recorded in the inventory |
| `provenance` | string, nullable | `specification` \| `characterization`, as recorded in the inventory |
| `binding_mode` | string, nullable | `none` \| `xunit-with-annotations` \| `bdd-runner` |
| `bound_story` | number or string, nullable | The Story/issue id from `gherkin-bindings.json`, when that file exists for the run (only produced by `/gherkin-public`) |
| `coverage_delta` | object, nullable | `{line_pct, branch_pct}` — workflow-level delta between the two coverage snapshots passed to the roll-up, not an isolated per-scenario attribution (no finer-grained mapping exists today) |
| `mutation_delta` | object, nullable | `{survivors_after_delta}` — workflow-level survivor-count delta, same caveat as `coverage_delta` |

- **Emitter:** `plugins/dev-team/scripts/gherkin_effectiveness_rollup.py`, invoked from `/quality-targets-converge` Step 6b after each convergence iteration's re-measure, when `gherkin.md` exists for the workflow slug.
- **Consent:** unconditional (derived metrics only; no prompt/file-content capture).
- **Consumers:** none yet — this is the roll-up a future `/harness-audit`-style review reads to compare BDD-derived vs. hand-written test effectiveness.

---

## Adding a new stream

1. Name it `.claude/metrics/<name>.jsonl` (or `.json` for a single-current-value
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

One record per `/autoship` dispatch-unit outcome (a solo issue or a batch),
plus one `round_summary` event per round. Every record is appended via the
shared `hooks/lib/autoship_log.py` appender (its `--json`/`--json-file`
CLI), which stamps `logged_at` regardless of which of the three shapes
below the caller passes it — the library itself is schema-agnostic; the
shape is entirely determined by `/autoship`'s own SKILL.md (Steps 3f/4).

**Solo entry** — one record per solo-dispatched issue:

| Field | Type | Values / source |
| --- | --- | --- |
| `logged_at` | string | ISO-8601 (UTC) — stamped by `autoship_log.py` |
| `round_id` | string | ISO-8601 timestamp generated once at round start (before Step 1) |
| `issue` | integer | The dispatched issue number |
| `status` | string enum | `shipped` \| `failed` \| `unrecognized` \| `blocked` |
| `blocked_reason` | string, nullable | The extracted stakeholder question (`blocked`), the Step-3d.1-synthesized classifier-verdict string (`failed`/`unrecognized`), or `null` for `shipped` |

**Batch entry** — one record per batch dispatch unit, never one per member
issue, applying identically across every outcome (`shipped`, `blocked`,
`failed`, and `unrecognized` alike):

| Field | Type | Values / source |
| --- | --- | --- |
| `logged_at` | string | ISO-8601 (UTC) — stamped by `autoship_log.py` |
| `round_id` | string | Same round-start timestamp as any solo entry logged the same round |
| `batch_id` | string | e.g. `grp-101` — `autoship_group.py`'s deterministic batch id |
| `issues` | array of integer | Every member issue number |
| `status` | string enum | `shipped` \| `failed` \| `unrecognized` \| `blocked` |
| `blocked_reason` | string, nullable | Same convention as the solo entry's field, applied to the whole batch |

**`round_summary` event** — one per round, appended after Step 3's
per-dispatch-unit loop ends (skipped in `--dry-run`):

| Field | Type | Values / source |
| --- | --- | --- |
| `logged_at` | string | ISO-8601 (UTC) — stamped by `autoship_log.py` |
| `round_id` | string | Same round-start timestamp as this round's solo/batch entries |
| `event` | string | Always `"round_summary"` — distinguishes this record from a solo/batch entry above |
| `processed_units` / `processed_issues` | integer | Dispatch units Step 3c actually dispatched this round / their total member-issue count |
| `discovered_units` / `discovered_issues` | integer | Every dispatch unit `autoship_queue.py` produced this round (`queue` + `deferred` combined) / their total member-issue count |
| `deferred_units` / `deferred_issues` | integer | Dispatch units left in `deferred` / their total member-issue count (a solo unit counts as 1) |
| `blocked_pending_confirmation_units` / `blocked_pending_confirmation_issues` | integer | Proposed batches Step 2c actually blocked pending human confirmation this round / their total member-issue count — always present, `0` when Step 2b/2c never ran or blocked nothing |
| `cost_usd` | number | Accumulated round cost |
| `status` | string enum | `complete` \| `cost_cap_reached` \| `dry_run` \| `no_eligible_issues` \| `no_unit_fits_cap` \| `blocked_pending_confirmation` |

- **Emitter:** `hooks/lib/autoship_log.py` called from the `/autoship` skill (Step 3f for solo/batch entries, Step 4 for the `round_summary` event).
- **Consent:** unconditional (cost/count aggregates and enum values only — no prompt text or file contents).
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
| --- | --- | --- |
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

---

## `iteration-journal.jsonl`

**Added by #1168.** Hard per-iteration decision journal for the autonomous
`/autoship`/`/ship` loops: one entry per round/iteration recording what was
attempted, its outcome, and the next action — the accountability record an
autonomous run needs to be debuggable after the fact. Unlike
`workflow-states.jsonl`'s phase transitions, this stream is not derived; each
entry is a durable, once-written decision note.

| Field | Type | Values / source |
| --- | --- | --- |
| `ts` | string | ISO-8601 UTC `%Y-%m-%dT%H:%M:%SZ` |
| `round_id` | string | Identifier for the current round/iteration (`/autoship`'s round_id, or `/ship`'s issue identifier) |
| `attempted` | string | Short structured note — what was attempted this iteration (deliberate, agent-authored rationale, not incidental free text — same precedent as `config-changelog.jsonl`'s `description`) |
| `outcome` | string | Short structured note — what happened |
| `next_action` | string | Short structured note — what happens next |
| `plugin_version` | string | From `.claude-plugin/plugin.json` |
| `session_id` | string, optional | Opaque per-session ID — enables joins with `boundary-events.jsonl` / `cost-metering.jsonl` |

- **Emitter:** `hooks/lib/iteration_journal_gate.py::record_iteration_entry()`, invoked via its `record` CLI subcommand as a model-authored append in `/autoship`'s per-issue loop (Step 3) and `/ship`'s per-phase loop, before the corresponding `check` subcommand gates advancement.
- **Gate:** `hooks/lib/iteration_journal_gate.py::check_iteration_journal()` (`check` CLI subcommand) hard-blocks advancement to the next issue/iteration — exit 1 — unless >=1 entry exists for the current `round_id`; a block also emits a `boundary-events.jsonl` event (`hook: iteration_journal_gate`, `decision: block`, `matched_rule: iteration-journal-missing`). This is a skill-level check-before-advance (mirroring `verify-log.jsonl`'s `progress_guardian.py --pre-pr` pattern), not a `settings.json` PreToolUse/PostToolUse registration — `/autoship`'s and `/ship`'s loop advancement is model-authored control flow inside a skill, not a tool call the harness intercepts at a distinct boundary. Complements, does not replace, the advisory plan-step-keyed `progress-guardian` agent.
- **Consent:** unconditional (a deliberate per-iteration accountability record, not passive usage telemetry).
- **Consumers:** `skills/autoship/SKILL.md`, `skills/ship/SKILL.md`, joinable with `skills/run-report/SKILL.md` (#1167) via `round_id`/`session_id`.

---

## `xunit-v3-shim-decisions.json`

**Added by #1791.** Not JSONL — a single current-value JSON object keyed by test
project name, holding the operator's chosen remediation when xunit.v3
constructs block the Stryker v2 shim. This is the enforcement record, not
telemetry: `stryker_xunit_shim_guard.py` blocks every `dotnet-stryker` run
against a blocked project until an entry covering the current blocker set
exists, which is what makes the always-ask gate a guarantee rather than hook
stdout an agent may paraphrase or skip.

Each value:

| Field | Type | Values / source |
| --- | --- | --- |
| `project` | string | Test project name (the real test `.csproj` stem) |
| `choice` | string | `port` \| `exclude` \| `skip` \| `degrade` — the four documented remediations; any other value is rejected at write time |
| `fingerprint` | string, required | 16-hex digest over the blocker set's `file::construct` pairs (line numbers deliberately excluded). Scopes the decision to the blockers the operator actually saw; a mismatch — or an absent value, which would make the entry a blanket answer — re-asks |
| `files` | array of string | Flagged files the choice covers, project-relative |
| `note` | string, nullable | Operator rationale, when given |
| `recorded_at` | string | ISO-8601 UTC `%Y-%m-%dT%H:%M:%SZ` |

- **Emitter:** `hooks/lib/xunit_v3_operator_gate.py::record_decision()`, invoked
  via its `record` CLI subcommand after the operator answers the gate.
- **Gate:** `hooks/lib/xunit_v3_operator_gate.py::decision_for()`, read by
  `hooks/stryker_xunit_shim_guard.py` (PreToolUse on `Bash`). No covering entry
  → exit 2 with the operator question as the block body. Fails closed on every
  axis: a fingerprint mismatch, an absent fingerprint, and a stored `choice`
  outside the four all re-ask rather than letting a run proceed unasked.
- **Consent:** unconditional (an explicit operator decision record, not passive
  usage telemetry).
- **Consumers:** `hooks/stryker_xunit_shim_guard.py`,
  `skills/mutation-testing/scripts/mutation_feasibility_gate.py` (same question
  payload), `skills/stryker-xunit-v2-shim/SKILL.md` Step 1a. No path override
  (#1870 dropped `DEV_TEAM_XUNIT3_SHIM_DECISION_FILE` entirely — no legitimate
  caller needs runtime relocation of the store).
- **Audit trail (#1870):** every `record_decision()` write and every
  `decision_for()` honor (a stored decision covering the current question,
  about to drive the guard's outcome) also emits a `boundary-events.jsonl`
  entry — `matched_rule` of `xunit-v3-shim-decision-record-<choice>` or
  `xunit-v3-shim-decision-honor-<choice>`, `subject_hash` bound to the
  question's `fingerprint` — so a self-recorded choice is visible in the same
  stream the review-gate corroboration mechanism is audited from.
