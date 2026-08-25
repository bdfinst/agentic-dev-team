---
name: harness-audit
description: >-
  Analyze review agent effectiveness, model routing, and orchestration complexity
  against actual usage data. Produces a report of harness components that may be
  candidates for simplification or removal. Use periodically to prevent harness
  staleness as model capabilities improve. Audits the dev-team plugin's OWN
  harness from runtime metrics — not your project repo's readiness (for that,
  use /agent-readiness).
argument-hint: "[--output <path>] [--pdf]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(date *, python3 *, jq *), Write
---

# Harness Audit

Role: orchestrator. This command analyzes harness effectiveness — it does not modify agents or configuration.

You have been invoked with the `/harness-audit` command.

> **Not `/agent-readiness`.** This audits the **dev-team plugin's own harness**
> (review-agent effectiveness, model tiers, orchestration) from accumulated
> runtime metrics in `metrics/`. `/agent-readiness` scores the **subject
> repository's** readiness for AI-assisted development from a static checkout.
> Different subject, different input, different output. The inward-facing
> companion here is `/session-review`, whose `session-digest.jsonl` this command
> consumes (Step 1).

**Portable executable, repo-relative data (#1653).** `eval_ablation.py` now ships under `plugins/dev-team/scripts/` — its `--find-latest`/`--jsonl` mode is a generic JSONL reader with no repo-shape assumption, unlike the module's `--mode knowledge`/`--mode agent` paths, which stay monorepo-only (they read `evals/` fixtures never shipped). The call below is therefore `${CLAUDE_PLUGIN_ROOT}`-qualified like any other shipped script; only the `--jsonl` argument stays bare — `metrics/eval-ablation.jsonl` is genuinely *this repo's own* runtime metrics stream, consistent with the note above that this command audits the dev-team plugin's own harness.

## Orchestrator constraints

1. **Do not modify agents or configuration.** Produce a report only. All remediation requires human action.
2. **Write the report to a file.** Present only the summary table and next-steps in chat — do not repeat the full report.
3. **Be concise.** Use tables and short sentences. No preambles, no filler.

## Parse Arguments

Arguments: $ARGUMENTS

- `--output <path>`: Write report to a specific path. Default: `.dev-team-reports/harness-audit-<date>.md`
- `--pdf`: After writing the report, render it to a sibling PDF via `hooks/lib/report_pdf.py`, resolving against the **actual** report path written this run (the `--output` override when given, else the default). See `knowledge/report-pdf-integration.md`. Additive; non-fatal if no engine is available.

## Steps

### 1. Check for metrics data

Read metrics JSONL files from `metrics/`. Full field reference for every
stream below: `${CLAUDE_PLUGIN_ROOT}/knowledge/telemetry-schema.md` — read it
instead of re-deriving a schema from the emitter. Five complementary streams
exist:

- `metrics/*-task-log.jsonl` — **self-reported** task logs (whatever the model
  chose to record about itself).
- `metrics/session-digest.jsonl` — **ground-truth** real-session digests from
  `/session-review` (#129): token/cost trends, `rework`/`accuracy` counts, and
  `utilization.never_observed_*`. Prefer this where it disagrees with the
  self-reports, and use `never_observed_*` to corroborate stale-component
  flags. Schema + join: see `docs/eval-system.md` → "Session-review trend
  digest".
- `~/.claude/metrics/artifact-usage.json` — **per-artifact usage index** written by the
  telemetry hook on each Skill invocation. Use `last_used_at` to identify
  artifacts that have never been observed (absent from the index) or are stale
  (absent or `last_used_at` > 30 days ago). Cross-reference with
  `never_observed_*` in `session-digest.jsonl` for corroboration. See
  `knowledge/artifact-lifecycle.md` for the lifecycle threshold definitions.
- `metrics/boundary-events.jsonl` — **boundary-level (policy-gateway) events**
  (#859): every guard hook's `block`/`warn`/`bypass` decision plus
  `intervention` keywords, each with the emitting `hook` and a `matched_rule`
  rule ID. Where `session-digest.jsonl`'s `rework` counts show outcomes
  without causes, join on `session_id` (when present on both streams) to
  attribute friction to a specific hook/rule instead of reasoning from counts
  alone.
- `metrics/eval-ablation.jsonl` — **causal** per-agent ablation evidence from
  `/agent-eval --ablation <agent>` (#868): a controlled baseline-vs-ablated
  integration-tier delta, not accumulated usage data. When a record exists
  for a drop-candidate agent, Step 3 cites its measured delta/verdict instead
  of relying on `review-value.jsonl` alone.

If no metrics data exists or insufficient data is available (fewer than 10 review runs logged), report:

> "Insufficient metrics data for a meaningful audit. Run the system for a period to accumulate review data, then re-run `/harness-audit`. Minimum: 10 logged review runs."

List what data is missing and exit.

### 2. Check for a stale baseline (re-baseline detection, #860)

Report-only — this step never edits `evals/baseline.json` or re-runs evals
itself; it only decides whether the report needs a **Re-baseline Required**
section.

1. Read `evals/baseline.json`. If the file is absent, skip this step
   entirely (nothing to compare).
2. Read its `model` field (written by `scripts/eval_variance.py
   --write-baseline --model <name>`, per the change-contract flow in
   `skills/feedback-learning/SKILL.md`). **Absent field = pre-migration
   baseline — do not prompt.** This is deliberate: a baseline recorded
   before the `model` field existed carries no false signal either way.
3. Read the current session's model from `metrics/session-digest.jsonl`
   (the most recent record's model field) or session metadata.
4. Compare. **On mismatch**, the report (Step 8) gains a **Re-baseline
   Required** section instructing the operator to re-run the eval suite and
   re-write the baseline (`/agent-eval` full suite + `eval_variance.py
   --write-baseline --model <current-model>`) before trusting any pre/post
   comparison elsewhere in this report or in a feedback-learning change
   contract. Flag explicitly that scaffolding kept alive by old-model scores
   (e.g. a removal candidate from Step 3 that "still fails" on the old
   model) may now be re-evaluable and possibly removable.
5. **On match** (or the field absent), no section is added — this is silent
   success, not a finding.

### 3. Analyze review agent effectiveness

For each review agent in the registry (`knowledge/agent-registry.md`):

1. **Finding rate**: How often does this agent produce findings (fail or warn) vs. pass?
2. **Zero-fail agents**: Flag agents that have never returned `fail` across all logged reviews. These are removal candidates — they may not be catching real issues.
3. **False positive rate**: If correction data exists (from `/apply-fixes`), check how often findings were dismissed vs. applied. Agents with >50% dismissed findings have a high false positive rate.
4. **Finding severity distribution**: Is the agent producing mostly minor findings? If >80% of findings are minor severity, consider whether the agent justifies its token cost. Compute this from the `severity_breakdown` object on `metrics/review-value.jsonl` rows (`{errors, warnings, suggestions}`, added in #1256) — aggregate per `agents_run` and treat `suggestions` as the minor bucket. Rows written before #1256 lack the field; count them as "no severity data" and exclude them from the ratio rather than assuming a mix (small-N honesty, consistent with Step 5). If **no** row carries `severity_breakdown`, report this analysis as dark ("severity breakdown unavailable — pre-#1256 metrics") rather than fabricating a distribution.

   ```bash
   log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
   [ -f "$log" ] && jq -s '
     map(select(.severity_breakdown != null))
     | group_by(.agents_run | sort | join(","))
     | map({
         agents:      (.[0].agents_run | sort | join(", ")),
         errors:      (map(.severity_breakdown.errors)      | add // 0),
         warnings:    (map(.severity_breakdown.warnings)    | add // 0),
         suggestions: (map(.severity_breakdown.suggestions) | add // 0)
       })
     | map(. + {total: (.errors + .warnings + .suggestions)})
     | map(select(.total > 0) | . + {minor_pct: (.suggestions / .total * 100 | round)})' \
     "$log"
   ```

### 4. Analyze review-value fix rates

**Check the sample's validity first (#2019).** Run this before reading a single rate, and report its verdict at the top of every section that cites per-lens value:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/review_value_coverage.py" --json
```

Both writers of `review-value.jsonl` are triggered by agent instruction, not by mechanism, so the rows collected skew toward rounds that found something — an agent that found nothing is markedly less likely to run a "record the review value" step. #1512 measured this directly: ~100% "found something" across a 10-record sample, which nearly justified pruning lenses that were working fine.

The script reconciles the value rows against `agent_dispatch_ledger`'s `boundary-events.jsonl` records, which a hook writes whether or not a round found anything. A verdict other than `usable` means the numbers below describe the *collection*, not the lenses:

| verdict | what it means for this section |
|---|---|
| `no-data` | no rows; report the analysis as dark |
| `unverifiable` | no dispatch records, so completeness cannot be checked |
| `undercollected` | rows are a non-random subset; rates are not attributable to lenses |
| `insufficient` | below the 100-row floor #1512 set |
| `biased` | quiet rounds are not reaching the log; no-op rates are unreadable |
| `usable` | rates may be cited |

**Never emit a drop candidate, tier-down, or gating recommendation from a non-`usable` sample.** Report the verdict and what would make the sample usable instead. This is the check that would have stopped #1512's ten biased records from being read as evidence.

Read `metrics/review-value.jsonl` (written by `/build` per #348, schema in `performance-metrics`). If the file is absent, note it and continue — this section is skippable.

For each **checkpoint type** (the `checkpoint` field: `step` or `slice`) and each **agent combination** (`agents_run` list, treated as a set-key), compute:

**Exclude read-only rows first (#1257).** Fix-rate ROI is only meaningful for
fix-applying `/build` checkpoints. A read-only review (`source: "code-review"`)
never applies fixes, so **every** row it produces has `issues_fixed: 0` and a 0%
fix rate — feeding those to the drop-candidate logic falsely flags a whole panel
that may be surfacing real defects (the 2026-07-20 run mislabeled all 7 agents
this way). The `jq` filters to the **fix-applying** sources — `build-checkpoint`
and, since #1962, `build-backstop` (both run the review-fix loop and can move
`issues_fixed`), treating an absent `source` as `build-checkpoint` for
back-compat — and drops `outcome: "skipped"` rows (a backstop suppressed by
`--backstop-review=skip` never ran, so counting it would dilute every rate with
a non-event), **before** grouping:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  map(select((.source // "build-checkpoint") | . == "build-checkpoint" or . == "build-backstop"))
  | map(select(.outcome != "skipped"))
  | group_by(.checkpoint + "|" + (.agents_run | sort | join(",")))
  | map({
      checkpoint:    .[0].checkpoint,
      agents:        (.[0].agents_run | sort | join(", ")),
      total:         length,
      no_op:         (map(select(.outcome=="no-op"))    | length),
      fixed:         (map(select(.outcome=="fixed"))     | length),
      escalated:     (map(select(.outcome=="escalated")) | length),
      fix_rate:      ((map(select(.outcome=="fixed")) | length) / length * 100 | round),
      issues_found:  (map(.issues_found)  | add // 0),
      issues_fixed:  (map(.issues_fixed)  | add // 0),
      fix_iterations:(map(.fix_iterations)| add // 0)
    })' \
  "$log"
```

#### Per-lens outcomes split by diff shape — the measurement a test-only gate waits on (#1964)

`/code-review`'s existing cost gates narrow by file *type* (change-shape),
diff *size* (change-size), and architectural *signal* (change-impact). None of
them exploits a fourth, structurally-guaranteed shape: under `/test-improve`'s
default `refactor-mode: no-refactor`, Phase 5's diff **cannot** contain
production code, because `/build` rejects it — yet the four opus-tier
`Scope: always` lenses run on it anyway, per Story and again at phase end.

Whether any of them can be dropped there is an empirical question, so answer
it before touching a gate. Group `diff_shape: "test-only"` rows by lens and
report the outcome split against the same lens's `mixed` rows:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  map(select((.source // "build-checkpoint") | . == "build-checkpoint" or . == "build-backstop"))
  | map(select(.outcome != "skipped" and .diff_shape != null))
  | map({shape: .diff_shape, outcome, lens: .agents_run[]})
  | group_by(.lens)
  | map({lens: .[0].lens,
         test_only:  (map(select(.shape=="test-only")) | length),
         test_only_no_op: (map(select(.shape=="test-only" and .outcome=="no-op")) | length),
         mixed:      (map(select(.shape=="mixed")) | length),
         mixed_no_op:(map(select(.shape=="mixed" and .outcome=="no-op")) | length)})
  | sort_by(-.test_only)' \
  "$log"
```

Report `test_only_no_op / test_only` per lens, alongside that lens's `mixed`
rate as the control — a lens that no-ops at the same rate on *both* shapes is
simply a quiet lens, not one this diff shape defeats, and gating it on shape
would be reading noise as signal. Only a lens that no-ops on test-only diffs
**and** earns its keep on mixed ones is a candidate for
`change_shape.py`'s `TEST_ONLY_SKIP_LENSES`, and each entry lands in its own
PR citing these numbers. State the row count: with few rows, the honest
finding is "not enough data yet", not a recommendation.

Two lenses are **not** candidates regardless of what the split shows, and the
report should say so rather than proposing them: `security-review` (tests
routinely embed credentials and injection payloads) and `correctness-review`
(an inverted assertion is exactly its subject).

#### Backstop redundancy — the measurement that gates `--backstop-review=skip` (#1962)

`/build`'s Step-6 backstop reviews files an inline checkpoint (sub-steps 4/6)
already reviewed in the same run, and under an enclosing orchestrator (e.g.
`/test-improve` Phase 5, which runs its own end-of-phase panel over the
cumulative diff) it is the third review layer over the same test code. Whether
that layer earns its cost is an empirical question, and `source:
"build-backstop"` rows are the answer. Report the backstop's own outcome split
next to the checkpoint split, restricted to builds where a checkpoint actually
ran first — a backstop on a `trivial`-only slice reviewed something nothing else
did, and including it would understate redundancy:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  (map(select((.source // "build-checkpoint") == "build-checkpoint"))
     | map(.plan + "|" + (.slice // "")) | unique) as $reviewed
  | map(select(.source == "build-backstop" and .outcome != "skipped"))
  | map(select(((.plan + "|" + (.slice // "")) | IN($reviewed[]))))
  | {backstop_runs_after_a_checkpoint: length,
     no_op:     (map(select(.outcome=="no-op"))     | length),
     fixed:     (map(select(.outcome=="fixed"))     | length),
     escalated: (map(select(.outcome=="escalated")) | length),
     issues_found: (map(.issues_found) | add // 0)}' \
  "$log"
```

Read it honestly, and state the sample size in the report: a backstop that is
**~all `no-op` after a checkpoint already ran** is the evidence that lets a
caller pass `--backstop-review=skip`; any non-trivial `fixed` count is evidence
it is catching what the checkpoints miss, and the flag should stay unused. A
handful of rows is not a finding — say so rather than recommending a flip off
noise. This is the same evidence-first discipline the architectural-impact gate
applies to widening `GATED_LENSES`: measure the lens, then narrow it.

For **read-only `code-review` rows**, report **finding-rate** (how often the
panel surfaced any issue) instead of fix-rate, and state plainly in the report
that these rows are excluded from the fix-rate drop-candidate logic because they
apply no fixes by design — a 0% fix rate there is expected, not a signal:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  map(select(.source == "code-review"))
  | map(. + {found: ((.issues_found // .findings_new) // 0)})
  | if length == 0 then "no read-only rows" else
    group_by(.agents_run | sort | join(","))
    | map({
        agents:       (.[0].agents_run | sort | join(", ")),
        total:        length,
        found_issues: (map(select(.found > 0)) | length),
        finding_rate: ((map(select(.found > 0)) | length) / length * 100 | round)
      })
    end' \
  "$log"
```

`(.issues_found // .findings_new)` covers both read-only row shapes: the
original whole-run `code-review` row (`issues_found`) and the per-round row
`/code-review` writes from #1624 (`findings_new`). Both are `source:
"code-review"`; only the round rows carry `round`/`dispatch_purpose`.

### 4a. Analyze re-review churn (#1624)

Rows carrying a `round` field are `/code-review`'s per-round instrumentation
(#1624) — one per dispatch round, with `fix_provenance_new` counting how many
of that round's new findings landed inside the previous round's fix delta.
**If no row carries `round`, report "no round data yet" and skip this
section** — do not infer churn from the dispatch ledger's frequency counts
alone, which is exactly the inference #1623 documents as unavailable.

**Churn ratio** — of the rounds that exist only because an earlier round's fix
was applied (`round >= 2`), what fraction found *nothing but* problems that
fix created? A high ratio means the loop is chasing its own tail:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  map(select(.round != null and .round >= 2))
  | if length == 0 then "no round data yet" else
    {
      rounds_after_first: length,
      pure_churn_rounds:  (map(select(.findings_new > 0 and .fix_provenance_new == .findings_new)) | length),
      churn_ratio:        ((map(select(.findings_new > 0 and .fix_provenance_new == .findings_new)) | length) / length * 100 | round),
      max_round_reached:  (map(.round) | max)
    }
    end' \
  "$log"
```

**Per-agent discovery-vs-verification split** — how much of each agent's
dispatch cost is spent confirming fixes rather than finding new problems.
Cross-reference against the `agent_dispatch_ledger` frequency table from
Step 3: an agent near the top of that table whose rounds are mostly
`verification` is a tier-down candidate for #1628's opt-in `verify_model:`,
not evidence of high discovery value:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  map(select(.dispatch_purpose != null))
  | map({purpose: .dispatch_purpose, agent: .agents_run[]})
  | group_by(.agent)
  | map({
      agent:        .[0].agent,
      discovery:    (map(select(.purpose=="discovery"))    | length),
      verification: (map(select(.purpose=="verification")) | length),
      closing:      (map(select(.purpose=="closing"))      | length)
    })' \
  "$log"
```

**Gate recidivism** — how often the review-corroboration gate blocked
because a fix invalidated the prior round's corroboration. This needs no new
stream; `boundary-events.jsonl` already records it. A session with repeated
blocks is the operator-visible symptom of the same churn.

#1886 moved this gate from `git commit` (`hook == "pre_commit_review"`) to
`gh pr create` (`hook == "pre_pr_review"`) — query BOTH hook names so a
session that spans the migration (or a fork still running the older cached
plugin version) is not silently undercounted:

```bash
log=".claude/metrics/boundary-events.jsonl"
[ -f "$log" ] && jq -rs '
  map(select((.hook == "pre_commit_review" or .hook == "pre_pr_review") and (.matched_rule | startswith("dispatch-evidence-"))))
  | group_by(.session_id)
  | map({session: (.[0].session_id // "unknown"), blocks: length, rules: (map(.matched_rule) | unique)})
  | sort_by(-.blocks)' \
  "$log"
```

Report all three together. State the sample size next to each number —
small-N honesty, consistent with Step 5. These metrics exist to tell whether
#1623's churn-reduction slices worked; a ratio computed from three rounds is
not evidence either way, and should be reported as such.

Flag **drop candidates**: any checkpoint+agents combination (from the
fix-applying rows only) with `fix_rate == 0` across **N ≥ 5** logged runs is a
drop candidate — it consistently adds overhead without catching defects.

Flag **high-value checkpoints**: `fix_rate ≥ 50%` — these are earning their cost and should be retained.

**Drop-candidate recommendations** (P2-S3):
For each drop candidate emit a recommendation in this form:
> `<checkpoint>/<agents>` fixed 0/<N> runs (fix rate 0%) — candidate to drop. To act: remove this checkpoint type from the relevant `/build` step-complexity tier or exclude these agents from the checkpoint's dispatch list. Do not auto-edit skills; present for human decision.

**Cite ablation evidence when available (#868).** `review-value.jsonl` alone is
observational — a zero fix-rate agent might have been shielded by another
agent, dispatched against the wrong changesets, or never given a defect to
catch. Before finalizing each per-agent drop-candidate recommendation, check
for causal evidence:

```bash
for agent in <each single-agent drop candidate>; do
  python3 "$CLAUDE_PLUGIN_ROOT/scripts/eval_ablation.py" --find-latest "$agent" \
    --jsonl metrics/eval-ablation.jsonl
done
```

- **Record found** — cite it in the recommendation instead of (or alongside)
  the fix-rate line: `<agent> — ablation run <recorded_at> (model
  <model>): delta {issues_caught: <n>, test_commands_passed: <n>, tokens:
  <n>}, verdict "<verdict>". <If verdict is "baseline failed —
  inconclusive": state the evidence is unusable and the fix-rate signal
  above is the only basis for this recommendation.>`
- **No record found** — state the evidence is correlational-only and name
  the exact command that would upgrade it: `No ablation evidence for
  <agent> — this recommendation is based on correlational usage data only.
  Run \`/agent-eval --ablation <agent>\` to get a controlled baseline-vs-
  ablated delta before acting.`

This applies only to drop candidates that resolve to a **single** review
agent (multi-agent checkpoint combinations have no single-agent ablation
record to cite — note that explicitly rather than guessing which member
agent a record might apply to).

Do not modify any skill or agent file. The report is the only artifact.

### 5. Lesson Validation — validated-outcome weighting (#866)

Close the loop on `/feedback-learning` lessons: does an adopted lesson
measurably help, or should it become a rollback candidate? This step is
**report-only**, consistent with the orchestrator constraints above — it
never edits an agent, skill, or CLAUDE.md file, and a `harmful` verdict is
always a *proposal*, never an automatic rollback.

Reads `metrics/config-changelog.jsonl` (written by `/feedback-learning`,
schema in [feedback-learning](../feedback-learning/SKILL.md) → Audit Trail)
and `metrics/session-digest.jsonl` (this command's existing Step 1 input).
Both are metrics-only — no prompt or code content, consistent with the
session-review privacy boundary.

Run the deterministic helper (pure stdlib, zero model tokens for the
computation):

```bash
changelog=".claude/metrics/config-changelog.jsonl"; [ -f "$changelog" ] || changelog="metrics/config-changelog.jsonl"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-audit/scripts/lesson_validate.py" \
  --changelog "$changelog" \
  --digest metrics/session-digest.jsonl \
  --apply -o memory/lesson-validation.json
```

- **`--apply`** appends new `type: "validation"` entries to
  `metrics/config-changelog.jsonl` for every newly-judged lesson — this is an
  **append-only** write (new lines only); it never rewrites or deletes an
  existing line. Verify this yourself if in doubt: a byte-for-byte diff of the
  file before and after the run must show only appended lines.
- Every **adopted lesson with structured evidence** (`amend`/`learn`/`remember`
  entries whose `evidence` field is an object, not the literal string
  `"unmeasurable"` and not absent) whose observation window has elapsed gets a
  verdict:
  - **validated** — the watched metric moved in the expected `direction`.
  - **neutral** — the window elapsed, adequate data exists, no meaningful
    movement either way.
  - **harmful** — the watched metric moved against the expected `direction`.
  - **insufficient data** — fewer than `window_sessions` digest records exist
    on either side of adoption. This is a data condition, **never** reported
    as `neutral` — small-N honesty over a false-precision judgment.
  - Comparison is **direction-only** on window means (v1 — no significance
    testing; the digest carries small-N aggregate counts where formal testing
    would be false precision).
- Entries marked `"unmeasurable"` and **legacy** entries (written before the
  `evidence` field existed, so the key is absent) are **surfaced as counts
  only** — they never receive a verdict and are never proposed for rollback
  on evidence grounds.
- Each **harmful** verdict emits a **rollback proposal** carrying the
  original entry's `timestamp`, `file_modified`, `section_modified`, and
  `previous_value` — enough for `/feedback-learning`'s existing
  [Rollback](../feedback-learning/SKILL.md#rollback) flow to act on it after
  a human approves. Never auto-apply.

Include a **Lesson Validation** section in the report (Step 8) summarizing
verdict counts, the unmeasurable/legacy counts, and the full list of rollback
proposals.

### 6. Analyze model routing

For each agent listed in `knowledge/agent-registry.md` (with its `model:`/`effort:` frontmatter, resolved natively by the harness per `agents/orchestrator.md` → Model/Effort Resolution — ADR 0026):

1. **Over-tiered agents**: Agents assigned to opus that consistently produce simple pattern-match findings may work equally well on sonnet or haiku.
2. **Under-tiered agents**: Agents on haiku that frequently miss issues caught by human review may need a higher tier.
3. **Cost distribution**: Which agents consume the most tokens? Are the most expensive agents also the most valuable?

### 7. Analyze orchestration complexity

Review the current pipeline for components that may be unnecessary overhead:

1. **Phase count**: Are all three phases (Research, Plan, Implement) needed for the types of tasks being run? If most tasks are simple, suggest a fast path.
2. **Review checkpoint frequency**: Are inline reviews running on every step? If most steps are trivial, the complexity classification (see `skills/plan/SKILL.md` § Complexity Classification) should be catching this.
3. **Unused skills**: Skills loaded but never applied in logged sessions.
4. **Context pollution per phase (#1520)**: Read the per-phase resident-vs-spend ratios from the phase markers (`phase-report`) and flag phases whose context lingered rather than being one-time cost — candidates for earlier mid-phase compaction or narrower subagent scoping. Skip if the log is absent.

   ```bash
   log=".claude/metrics/phase-markers.jsonl"; [ -f "$log" ] || log="metrics/phase-markers.jsonl"
   [ -f "$log" ] && python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py" phase-report --log "$log" --json
   ```

   A phase with a high `resident_to_spent_ratio` spent proportionally little fresh generation while carrying a large resident context — cite it in § Orchestration Simplification Opportunities as a compaction/scoping candidate. This is a session-scoped proxy (resident is sampled at the `/handoff` boundary — see `skills/cost-report/SKILL.md` § Context pollution), not exact per-phase accounting.

### 8. Produce report

When `--pdf` was passed, after writing the report render **the actual output
path** (the `--output` override when given, else `.dev-team-reports/harness-audit-<date>.md`)
to a sibling PDF per `knowledge/report-pdf-integration.md` (additive; non-fatal
if no engine):

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" <the-output-path>
```

Write the report to the output path using this structure:

```markdown
# Harness Audit Report

**Date**: <date>
**Metrics period**: <earliest to latest logged review>
**Review runs analyzed**: <count>

## Re-baseline Required

> Only present when Step 2 detects a model mismatch between
> `evals/baseline.json`'s `model` field and the current session's model.
> Omit this section entirely on a match or an absent/pre-migration field.

- **Baseline model**: <model recorded in evals/baseline.json>
- **Current session model**: <current model>
- **Action**: Re-run the eval suite and re-write the baseline
  (`/agent-eval` full suite, then `eval_variance.py --write-baseline
  --model <current-model>`) before trusting any pre/post comparison in this
  report or in a feedback-learning change contract.
- **Possibly stale scaffolding**: <any removal candidate below whose
  "zero fail" or "high false positive" verdict was measured on the old
  model — flag for re-evaluation, not automatic removal>

## Review Agent Effectiveness

### Removal Candidates (zero fail findings)
| Agent | Reviews | Pass rate | Recommendation |
|-------|---------|-----------|----------------|

### High False Positive Rate (>50% dismissed)
| Agent | Findings | Dismissed | Rate | Recommendation |
|-------|----------|-----------|------|----------------|

### Low-Value Agents (>80% minor severity)
| Agent | Findings | Minor % | Recommendation |
|-------|----------|---------|----------------|

## Review-Value Fix Rates (inline checkpoint ROI)

> Source: `metrics/review-value.jsonl`. Absent = no `/build` runs logged yet.

### Per-Checkpoint-Type Fix Rates
| Checkpoint | Agents | Runs | No-op | Fixed | Escalated | Fix rate |
|------------|--------|------|-------|-------|-----------|----------|

### Drop Candidates (fix rate 0%, N ≥ 5 runs)
| Checkpoint | Agents | Runs | Ablation evidence | Recommendation |
|------------|--------|------|--------------------|-----------------|

> To act on a drop candidate: remove the checkpoint type from the relevant `/build`
> step-complexity tier or exclude the agents from that checkpoint's dispatch list.
> Requires human decision — do not auto-edit skills.
>
> "Ablation evidence" column: the cited `metrics/eval-ablation.jsonl` verdict +
> date for single-agent candidates, or "correlational only — run
> `/agent-eval --ablation <agent>`" when no record exists.

### High-Value Checkpoints (fix rate ≥ 50%)
| Checkpoint | Agents | Runs | Fix rate | Issues fixed |
|------------|--------|------|----------|--------------|

## Lesson Validation (validated-outcome weighting, #866)

> Source: `metrics/config-changelog.jsonl` × `metrics/session-digest.jsonl`.
> Report-only — verdicts are appended as new `type: "validation"` entries;
> harmful verdicts are rollback *proposals*, never automatic.

### Verdicts
| Lesson (`timestamp`) | Metric | Direction | Verdict |
|---|---|---|---|

### Rollback Proposals (harmful verdicts — human approval required)
| Lesson (`timestamp`) | File | Section | Recommendation |
|---|---|---|---|

> To act on a rollback proposal: run `/feedback-learning` and confirm the
> rollback against the `timestamp` above. Never applied automatically.

### Unmeasurable / Legacy (surfaced, not judged)
- Unmeasurable lessons: <count>
- Legacy lessons (no `evidence` field): <count>

## Model Routing Recommendations

| Agent | Current tier | Suggested tier | Rationale |
|-------|-------------|----------------|-----------|

## Orchestration Simplification Opportunities

- <Finding and recommendation>
- <Context-pollution candidates (#1520): any phase with a high resident/spent ratio from `phase-report` — recommend earlier mid-phase compaction or narrower subagent scoping. Omit if no phase markers logged.>

## Summary

- Agents to consider removing: <count>
- Model tier changes suggested: <count>
- Orchestration simplifications: <count>
- Review-value drop candidates: <count>
- Review-value high-value checkpoints: <count>
- Re-baseline required: <yes/no>
- Lessons validated / neutral / harmful / insufficient data: <count> / <count> / <count> / <count>
- Rollback proposals (harmful verdicts): <count>

## Next Steps

<Actionable recommendations prioritized by impact>
```

### 9. Present results

Display a summary of the report and the file path. Do not repeat the full report in chat — the file is the artifact.

## Error Handling

- Missing metrics files: Report what's missing, suggest how to generate data
- Incomplete agent registry: Flag agents found in metrics but missing from the registry
- No actionable findings: Report that the harness appears well-calibrated — this is a valid outcome
