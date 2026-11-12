# Benefit pre-registration

This document fixes, before any data is read, how each mechanism shipped by epics #2164 and #2172 is judged keep, tune, or retire. `scripts/benefit_eval_cli.py` reads the fenced block below and nothing else for thresholds. The prose around the block holds no second copy of its values.

**Status: proposal.** The maintainer confirms or edits every threshold, commits the result, and posts the document to #2200 before the first report run. A threshold changed after the post voids the post. Each entry carries a one-line `rationale` for its thresholds.

## Pre-registration block

```json prereg
{
  "version": 1,
  "metrics": [
    {
      "id": "skip-rate",
      "metric": "Delta-scoping skip rate: skipped (lens, file) pairs over candidate pairs",
      "instrument": "ledger-skips",
      "identity_class": "id-bearing",
      "baseline": "20.69% theoretical ceiling from the #2165 estimate; a measured rate above it signals a counting defect",
      "unit": "percent",
      "keep": ">= 10",
      "tune": "< 10",
      "retire": "< 3",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "candidate pairs",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "tune",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "share of repeat runs versus first runs",
        "files that changed between runs, which the ledger must re-review",
        "dispatch-hook rows are excluded: they count only pairs the consult left to dispatch"
      ],
      "computation": "metrics_ledger.skip_rate over ledger-skips rows with source=consult; prints the first-run and repeat-run rates, where a first run is a session's earliest consult inside the window (the rows do not record the backstop, so no per-backstop split is computed); the missing-scope-marker count is split by whether the session has a real consult row in the window, a heuristic because the event carries no dispatch source",
      "ceiling": 20.69,
      "rationale": "About half the ceiling is the smallest saving that pays for the ledger; under 3% the mechanism is not skipping in practice."
    },
    {
      "id": "findings-parity",
      "metric": "Findings parity: ledger-off actionable signatures missing from the ledger-on set",
      "instrument": "manual-input",
      "identity_class": "id-bearing",
      "baseline": "0 misses: the ledger-off run is the reference set",
      "unit": "missing signatures",
      "keep": "<= 0",
      "tune": "<= 2",
      "retire": ">= 3",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 3,
      "n_unit": "diffs",
      "null_rule": "Fewer than 3 hand-run diffs prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "tune",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "only 3 diffs: a rare finding can be missed by chance in either run",
        "model nondeterminism between the ledger-on and ledger-off runs"
      ],
      "computation": "manual-input: hand-run on 3 or more copies of past diffs; count ledger-off actionable signatures (finding_signature.is_actionable) absent from the ledger-on set; list the diff ids",
      "rationale": "Any miss is a regression and caps the delta-scoping verdict at tune; three misses across the diffs mean the ledger drops findings routinely."
    },
    {
      "id": "abort-yield",
      "metric": "Abort deferred-lens yield: share of lenses deferred by an abort that found something new",
      "instrument": "checkpoint-aborts",
      "identity_class": "id-bearing",
      "baseline": "none: first measurement; the question is whether deferred lenses mostly return clean",
      "unit": "percent",
      "keep": "<= 25",
      "tune": "> 25",
      "retire": "> 60",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "deferred lenses",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "few aborts in the window",
        "the fix loop changes the code the deferred lenses review"
      ],
      "computation": "metrics_ledger.abort_yield over checkpoint-aborts rows from aborted checkpoints; lenses deferred after a completed checkpoint are excluded; a deferred lens found something new when a later stop-hook row in the same session names it as the lens that tripped the abort rule; prints abort frequency beside it, aborted rows over abort-mode rows for each source on its own",
      "rationale": "At most a quarter finding something new means the abort mostly saves work; above 60% it only reorders the work."
    },
    {
      "id": "test-review-tp-change",
      "metric": "test-review true-positive change on the agent-eval fixtures, after minus before",
      "instrument": "manual-input",
      "identity_class": "id-bearing",
      "baseline": "true-positive rate of test-review before the pre-phase change, on the same fixtures",
      "unit": "percentage points",
      "keep": ">= 0",
      "tune": "< 0",
      "retire": "< -10",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "fixtures",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "small, fixed fixture set",
        "model version change between before and after",
        "eval run-to-run variance"
      ],
      "computation": "manual-input: /agent-eval true-positive rate before and after the pre-phase change; enter the difference and the run ids",
      "rationale": "A drop in true positives fails the mechanism whatever the token savings; a drop past 10 points is beyond tuning."
    },
    {
      "id": "test-review-token-delta",
      "metric": "test-review mean dispatch tokens, percent change after versus before the boundary",
      "instrument": "subagent-transcripts",
      "identity_class": "id-bearing",
      "baseline": "mean test-review dispatch tokens for dispatches that end before the boundary timestamp",
      "unit": "percent",
      "keep": "<= -15",
      "tune": "> -15",
      "retire": "> 0",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "dispatches",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict. A DIRECTIONAL line never feeds a verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "task mix differs before and after",
        "model or pricing change at the boundary",
        "a dispatch sits at its transcript's last record time, so a dispatch that straddles the boundary lands on one side",
        "tokens are the sum of every usage record in the transcript, the way the cost log counts them"
      ],
      "computation": "metrics_hooks.test_review_token_delta over the subagent transcripts of real sessions whose agent type is test-review (session_log): one dispatch per transcript, tokens summed over its usage records, split at the boundary timestamp; the cost-metering log is not used because its rows are cumulative snapshots per transcript, not dispatches; a before mean of 0 has no percent change, so the line prints insufficient with no delta",
      "rationale": "A 15% cut is the smallest change that stands out from dispatch-to-dispatch noise; an increase means the pre-phase costs more than it saves."
    },
    {
      "id": "expand-rate",
      "metric": "Tiered findings expand rate: share of rendered reports where --expand was used",
      "instrument": "none",
      "identity_class": "id-less",
      "id_less_handling": "unmeasurable",
      "baseline": "none: nothing is counted today",
      "unit": "percent",
      "keep": "<= 20",
      "tune": "> 20",
      "retire": "> 50",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "rendered reports",
      "null_rule": "No instrument: record unmeasurable with its follow-up issue. No verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "no instrument: render_tiered_findings.py persists no row"
      ],
      "computation": "unmeasurable: no persisted instrument; follow-up issue to file (one row per render with the expand flag)",
      "rationale": "Expanding in over a fifth of reports means the Tier-1 lines are too thin; above half the tiering saves no reading."
    },
    {
      "id": "report-size-cut",
      "metric": "Tiered findings report-size cut: percent smaller than the untiered report",
      "instrument": "none",
      "identity_class": "id-less",
      "id_less_handling": "unmeasurable",
      "baseline": "59.0% on the one round measured so far",
      "unit": "percent",
      "keep": ">= 40",
      "tune": "< 40",
      "retire": "< 15",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "rounds",
      "null_rule": "No instrument: record unmeasurable with its follow-up issue. No verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "no instrument: render sizes are printed, not stored",
        "one measured round so far"
      ],
      "computation": "unmeasurable: no persisted instrument; follow-up issue to file (store tiered and untiered sizes per render)",
      "rationale": "Keeping two thirds of the one-round cut over many rounds shows the saving holds beyond one example."
    },
    {
      "id": "injection-overhead",
      "metric": "Skill-context injection overhead: mean characters added per injection",
      "instrument": "skill-injection",
      "identity_class": "id-bearing",
      "baseline": "0 characters: a dispatch without injection",
      "unit": "characters",
      "keep": "<= 400",
      "tune": "> 400",
      "retire": "> 1200",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "injections",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "skills per injection vary with the agent-type mix"
      ],
      "computation": "metrics_hooks.injection_overhead: mean added_chars over skill-injection rows",
      "rationale": "About 100 tokens is near zero against a subagent prompt; above about 300 tokens a skill hint costs more than it should."
    },
    {
      "id": "injection-uptake",
      "metric": "Skill-context injection uptake: share of injections whose injected skill the subagent loaded",
      "instrument": "skill-injection",
      "identity_class": "id-bearing",
      "baseline": "Skill-call rate of the same agent types in transcripts before the boundary timestamp",
      "unit": "percent",
      "keep": ">= 50",
      "tune": "< 50",
      "retire": "< 10",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "injections",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "agents can load a skill unprompted, so uptake can overstate the injection's effect",
        "agent-type mix shifts across the boundary",
        "the stream carries no agent id, so the join is by session and agent type"
      ],
      "computation": "metrics_hooks.injection_uptake: per skill-injection row, a Skill call for an injected skill in that session's subagent transcript (session_log)",
      "rationale": "A skill loaded in half the dispatches earns its characters; under 10% the skills are not used and the hook is a retire candidate."
    },
    {
      "id": "guard-divergence",
      "metric": "Completion-guard divergence rate: share of subagent stops classified empty-final-turn or truncated-final-turn",
      "instrument": "subagent-stops",
      "identity_class": "id-bearing",
      "baseline": "none: first measurement; the earlier study was never run",
      "unit": "percent",
      "keep": ">= 2",
      "tune": "< 2",
      "retire": "< 0.5",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "subagent stops",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "agent-type mix",
        "unreadable stops are left out of the numerator and the denominator"
      ],
      "computation": "metrics_hooks.completion_guard_divergence: flagged rows over clean plus flagged rows in subagent-stops",
      "rationale": "Two percent flagged means the guard sees real divergence; under 0.5% it rarely fires, and a no-divergence result is a success that recommends keep-observational or retire."
    },
    {
      "id": "guard-false-positive",
      "metric": "Completion-guard false-positive rate in the hand-checked sample; gates blocking behavior",
      "instrument": "manual-input",
      "identity_class": "id-bearing",
      "baseline": "0%: a flagged dispatch whose final turn is complete is a false positive",
      "unit": "percent",
      "keep": "<= 5",
      "tune": "> 5",
      "retire": "> 30",
      "direction": "<=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "flagged dispatches hand-checked",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "the hand-check is one person's judgment",
        "the sample is seeded, not spread across the window"
      ],
      "computation": "manual-input: false positives over the sample from metrics_hooks.completion_guard_sample (20 flagged dispatches, or all if fewer); list the session ids",
      "rationale": "One false positive in a 20-dispatch sample (5%) is the loosest rate that still allows blocking; above 30% the classifier is not worth keeping."
    },
    {
      "id": "contradicted-rate",
      "metric": "source-verification contradicted verdicts per invocation",
      "instrument": "artifact-usage",
      "identity_class": "id-less",
      "id_less_handling": "UNVERIFIED",
      "baseline": "none: new skill",
      "unit": "contradicted verdicts per invocation",
      "keep": ">= 0.2",
      "tune": "< 0.2",
      "retire": "< 0.05",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "invocations",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict. An UNVERIFIED line never feeds a verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "verdict tallies are entered by hand",
        "the wired consumers decide what gets invoked",
        "artifact-usage keeps cumulative counts with no session ids and no direct-versus-consumer split"
      ],
      "computation": "metrics_cost.verdict_rate: invocations from artifact-usage; contradicted verdict tallies from the manual-input file",
      "rationale": "At 10 invocations, 0.2 means two caught wrong claims; one catch over the whole window is not enough to keep the skill."
    },
    {
      "id": "pbt-mutants-killed",
      "metric": "property-based-testing mutants killed beyond the target's existing tests, mean per target",
      "instrument": "manual-input",
      "identity_class": "id-bearing",
      "baseline": "mutants killed by the same target's existing tests",
      "unit": "mutants per target",
      "keep": ">= 1",
      "tune": "< 1",
      "retire": "<= 0",
      "direction": ">=",
      "inclusivity": "inclusive",
      "minimum_n": 10,
      "n_unit": "targets",
      "null_rule": "N below minimum N prints NULL (N=n) without the value and records no verdict.",
      "parity_cap": "none",
      "window": "Opens when #2199 merges. Closes at the later of 10 real sessions or 14 days. If minimum N is unmet at 28 days, the metric is NULL.",
      "confounds": [
        "the operator chooses the targets",
        "mutation tool version"
      ],
      "computation": "manual-input: /mutation-testing kills by the generated properties minus kills by the existing tests, per target; list the session ids",
      "rationale": "One extra kill per target is a concrete gain over existing tests; none across 10 targets means the skill adds nothing."
    }
  ]
}
```

## Fields

The parser requires every field except `id_less_handling`, `ceiling`, and `rationale`. An empty required cell fails the parser (exit 2) and names the metric and the column.

| Field | Meaning |
| --- | --- |
| `id`, `metric` | Short name and the full metric statement |
| `instrument` | A stream name, `subagent-transcripts` (the subagent transcripts of real sessions), `manual-input` (a number you enter by hand), or `none` (nothing persists it); any other value fails the parser |
| `identity_class` | `id-bearing` if rows carry a session id you can check against a transcript; `id-less` if not |
| `id_less_handling` | For `id-less` only, exactly one of `UNVERIFIED` (print the number on an `UNVERIFIED (no session ids)` line that never feeds a verdict or the exit code) or `unmeasurable` (print `unmeasurable` and no number; file a follow-up issue). The report prints `unmeasurable` for any metric with that handling, whatever its stream |
| `baseline` | A reference for the person reading the report. The tool does not read or print it |
| `unit` | The unit of the number and of the thresholds |
| `keep`, `tune`, `retire` | Threshold as a direction (`<`, `<=`, `>`, `>=`) and a number, in the unit named by `unit` |
| `direction`, `inclusivity` | The within-condition for the keep threshold, so `keep` must use the `direction` operator; `<=` and `>=` are `inclusive`, `<` and `>` are `exclusive` |
| `minimum_n`, `n_unit` | Smallest N that counts as data, and what N counts |
| `null_rule` | What happens below minimum N |
| `parity_cap` | `tune` if a parity regression caps the verdict at tune; `none` otherwise. You apply the cap by hand |
| `window` | When the data counts |
| `confounds` | The list printed after `DIRECTIONAL` on a before-and-after comparison |
| `computation` | Where the number comes from (see the metric-to-computation map) |
| `ceiling` | Optional theoretical maximum. The report prints it for skip rate only, and flags `counting defect` when the measured rate is above it |
| `rationale` | One line on why the thresholds sit where they do |

## Rules

**Verdict order.** The report prints `within` or `breach` against `keep` only. You apply `retire`, `keep` and `tune` by hand when you post the verdict: evaluate `retire` first; if it does not apply, evaluate `keep`; otherwise the verdict is `tune`. Each threshold's own operator decides its boundary: `>=` includes the limit and `<` excludes it.

**Within and breach.** The report prints `within` when the value meets the keep threshold using `direction`, and `breach` when it does not. A value exactly on the keep threshold is `within` when `inclusivity` is `inclusive` and `breach` when it is `exclusive`. `breach` is a threshold finding, not a verdict.

**Minimum N.** One rule for every metric: below `minimum_n`, the metric prints `NULL (N=n)` and no value. Findings parity counts diffs, so its `minimum_n` is lower than the rest, because you hand-run it. Every other metric uses the shared value in the block.

**Parity cap.** Any ledger-off actionable signature missing from the ledger-on set is a regression. File it as a bug. It forces the delta-scoping verdict to `tune` at best, whatever the skip rate.

**Id-less instruments.** `artifact-usage.json` carries no session ids. The report prints its numbers on an `UNVERIFIED (no session ids)` line. Such a line prints its status, but it never feeds a verdict and never changes the exit code. A metric with `unmeasurable` handling gets no number and a follow-up issue. The block declares no handling for `cost-metering.jsonl`, because no metric reads it.

**Directional comparisons.** A before-and-after number prints as `DIRECTIONAL (confounds: <the confounds list>)`. It prints its status, but it never feeds a verdict and never changes the exit code. The boundary is an ISO 8601 UTC timestamp ending in `Z`. Before is `ts < boundary` and after is `ts >= boundary`. An empty side prints `insufficient` and no delta, and so does a before mean of 0, unless the other side is below minimum N: then the line prints `NULL (N=n)` for that side.

**Statuses and exit codes.** The report evaluates each metric top to bottom and stops at the first match.

| Condition | Token | Exit |
| --- | --- | --- |
| N is 0 | `no rows in window` | 3 |
| N is below minimum N | `NULL (N=n)` | 3 |
| One directional side is empty | `insufficient` | 3 |
| The tally-based metric has invocations but no entered tally | `not entered` | 3 |
| Value fails the keep threshold | `breach` | 1 |
| Otherwise | `within` | 0 |

A hand-entered metric with no entry has N of 0 and prints `no rows in window`.

The exit code of a report comes from the lines that feed a verdict. A line on an id-less instrument and a `DIRECTIONAL` line print their own status and exit code, but do not change the run's code. Malformed input is always 2. An `unmeasurable` line adds exit 0.

The audit exits 1 for a `gap` or a `no instrument` metric, 2 for malformed input or a missing argument, and 0 otherwise. A parity regression is a manual finding in the #2200 comment, not an exit code.

## Metric-to-computation map

The `computation` cell of each entry is the map. It names one of three sources:

- **Stream and function.** A `metrics_*` module function in `scripts/lib/benefit_eval/` that reads the instrument.
- **Manual-input file.** `.claude/metrics/benefit-manual-input.json` is a JSON object keyed by metric `id`. Each value is `{"value": <number>, "n": <integer>, "sessions": ["<session id>"], "note": "<text>"}`. Enter each session id in full; the report checks it against the transcripts, counts one with no real transcript as `unverified`, and prints the first 8 characters of the others. A malformed file exits 2. The `test-review` true-positive change comes from `/agent-eval` output and the completion-guard false-positive rate from the hand-check of the seeded sample. Both go in this file, as do findings parity, the `contradicted` tallies, and the PBT mutant kills. For the `contradicted` tally, `value` is the count of contradicted verdicts and `n` is the verdicts reviewed; the rate divides `value` by invocations.
- **Unmeasurable.** No instrument persists the number. The audit reports `no instrument`, and you file a follow-up issue instead of adding an emitter.

Transcript-derived numbers join at the grain of session and agent type, because the `skill-injection` stream carries no agent id. The `test-review` token change reads one dispatch per subagent transcript, so it needs no stream.

## Glossary

- **Instrument:** a persisted stream or file that carries the rows a metric reads.
- **Metric:** one number computed from an instrument, with thresholds in the block.
- **Gap:** an instrument with no rows or fewer than 3 real sessions. A short gap waits for more sessions.
- **Manual:** the audit status of an instrument you enter by hand. It is not a finding.
- **No instrument:** a metric whose `instrument` is `none`. Record it as `unmeasurable` and file a follow-up issue.
- **Real session:** a session id with a transcript that `session_log` finds and that parses. Subagent transcripts do not count. Rows that fail this test are `unverified`, counted, and contribute zero to any number. An unparseable transcript is a counted skip. An empty transcript is not real and its rows are `unverified`, but it is not counted as a skip.
- **Insufficient:** one side of a before-and-after comparison has no rows. No delta exists.
- **Not entered:** the tally-based metric (the `contradicted` verdict rate) has invocations but the manual-input file has no tally for it. A hand-entered metric with no entry prints `no rows in window` instead.
- **Null:** the metric has rows but fewer than minimum N. The number is not trustworthy and gets no verdict.
- **Parity:** the check that delta-scoped review finds everything a full review finds.
- **Window:** the period whose rows count. For a before-and-after metric it bounds the after side.

## Operator runbook

1. Review each threshold in the block. Edit it if you disagree, then commit.
2. Run the audit: `python3 scripts/benefit_eval_cli.py audit`. Add `--json` for records. Exit 1 means a gap or a metric with no instrument; the two unmeasurable metrics make it exit 1 on every run, so read the status tokens.
3. Record each `no instrument` metric as `unmeasurable` with a follow-up issue. Wait for more sessions on a short gap. Record a gap still open when the window closes as `unmeasurable` too. If the audit finds neither, say so.
4. Post to #2200 as one comment: the block, the audit output, the window end date. Show session ids as their first 8 characters only. Note the comment's UTC creation time.
5. Wait for the window in each entry to close. An unmet minimum N at the null date stays `NULL`.
6. Hand-run parity on copies of past diffs, once with the ledger on and once with it moved aside. Use at least the parity minimum N from the block. Compare actionable signatures. Record the diff ids in the #2200 comment.
7. Run the report with `--prereg-posted <timestamp>`. Use the comment time from step 4, as an ISO 8601 UTC timestamp ending in `Z`. Add `--boundary <timestamp>`, the same format, for the before-and-after metric. Add `--window-start <timestamp>` with the time #2199 merged, and `--window-end <timestamp>` at the close of the window, in the same format; a row counts from the start up to but not including the end, and without them every row counts. Expect exit 2 without the first two; the report prints the post time beside its own run time. Run `report --help` for the other options. Attest that the comment came first; the tool does not check it.
8. Hand-post one verdict comment on #2164 and one on #2172. For each metric give the value, N, the threshold, the verdict, and the confounds on directional numbers.
9. Delete or archive the tooling after both verdicts post. If no verdict posts by the null date, delete it anyway.
