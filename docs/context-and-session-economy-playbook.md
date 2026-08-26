# Session economy playbook

A recurring procedure for reading session logs and context-ceiling data
*over time*, so the plugin keeps getting cheaper to run and re-does less work.

Every instrument this playbook uses already existed as a one-shot command.
What was missing was the loop: a cadence, a fixed order, a decision rule per
signal, and two append-only streams that make one round comparable to the
last. Without those, each review re-derived its own baseline and the question
"did anything we changed actually help?" had no mechanical answer.

This is maintainer tooling for developing *this* plugin. It is not shipped, and
it is not a workflow imposed on people who install dev-team on their own
projects.

## What this is not

Do not reach for this playbook to answer a question one instrument already
answers on its own:

| Question | Use |
| --- | --- |
| How much did *that run* cost? | [`/cost-report`](../plugins/dev-team/skills/cost-report/SKILL.md) |
| How did *that run* go, step by step? | [`/run-report`](../plugins/dev-team/skills/run-report/SKILL.md) |
| What should we change, based on recent sessions? | [`/session-review`](../plugins/dev-team/skills/session-review/SKILL.md) |
| Which agents/routing have gone stale? | [`/harness-audit`](../plugins/dev-team/skills/harness-audit/SKILL.md) |
| Which skills and agents are unused? | [`/artifact-lifecycle`](../plugins/dev-team/skills/artifact-lifecycle/SKILL.md) |
| Is the context ceiling in the right place *right now*? | [`context_ceiling_report.py`](context-ceiling-validation.md) |

This playbook is the **longitudinal** layer over those: run them in a fixed
order on a fixed cadence, persist the comparable subset, and act on the deltas
rather than on any single round's absolute numbers.

## Cadence

**Monthly**, and additionally whenever one of these lands:

- a change to the context ceiling, the guard, or what it gates;
- a model change (a new default model resizes every window, and an
  unrecognized id silently falls back to 200K — see [ADR 0011's
  amendment](adr/0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md));
- a batch of agent, skill, or hook changes large enough that you would not be
  able to attribute a later regression to it.

Monthly is deliberate rather than weekly. Both streams are per-session
aggregates, and a week of one maintainer's work is too few sessions for a
percentage to mean anything — a 2-of-9 blocked rate reads as 22% and is noise.
A round that cannot distinguish signal from sample size is worse than no round,
because it invites action on both.

## The rounds

Run in this order. Each step's output is input to the next.

### 1. Refresh the session stream

```bash
python3 scripts/session_extract.py --plugin-root plugins/dev-team \
  --append .claude/metrics/session-digest.jsonl
```

This is the same append `/session-review` performs at its step 5, extracted so
a round can refresh the stream without also producing a suggestions report.
Aggregate counts only — no file names, prompts, or code.

What it captures, and what each field is for:

| Group | Fields | Reads as |
| --- | --- | --- |
| `rework` | `repeated_file_edits`, `repeated_verify_runs`, `retried_bash_commands`, `failed_edits`, `permission_denials`, `compaction_events` | work done more than once — the thing to drive down |
| `token` | per-model input/output/cache totals | what it cost |
| `accuracy` | `tool_error_rate`, `user_correction_turns` | how often the loop went wrong |
| `gate` | `commit_attempts`, `commit_bypasses`, `bypass_rate` | whether the gates are being obeyed or routed around |
| `utilization` | `agents_invoked`, `skills_invoked`, `never_observed_*` | what is actually used |

### 2. Refresh the ceiling stream

```bash
python3 scripts/context_ceiling_report.py \
  --append .claude/metrics/context-ceiling.jsonl
```

Read the printed sweep now; the appended record is for next round. Full
column-by-column guide: [Validating the context
ceiling](context-ceiling-validation.md).

**If the verdict says `inconclusive`, stop treating the ceiling as reviewed
this round.** It means no session reached the ceiling at a blockable call, so
the corpus contains no evidence either way. Widen `--transcripts` across more
projects before concluding anything.

### 3. Read the deltas, not the levels

```bash
python3 -c "
import json, pathlib
for stream in ('session-digest', 'context-ceiling'):
    p = pathlib.Path('.claude/metrics') / f'{stream}.jsonl'
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    print(f'== {stream}: {len(rows)} rounds ==')
    for r in rows[-2:]:
        print(' ', r.get('recorded_at'), json.dumps(r)[:160])
"
```

A single round's absolute numbers are close to meaningless — the corpus
changes shape every month. What carries information is the *direction* of a
metric across rounds against a change you can name.

### 4. Decide

One rule per signal. Each names the action and, where one exists, the ADR
whose revisit trigger it discharges.

| Signal | Direction | Action |
| --- | --- | --- |
| `rework.repeated_file_edits` / `repeated_verify_runs` rising | worse | Run `/session-review` for the *why*; this stream says only that it happened. |
| `gate.bypass_rate` rising | worse | A gate is being routed around. Fix the gate's cost or its correctness — never its enforcement. |
| `accuracy.user_correction_turns` rising | worse | Instructions are being misread. Candidate for a CLAUDE.md or skill-prose fix, not a code fix. |
| `utilization.never_observed_*` growing | drift | Feed to `/artifact-lifecycle`; a never-invoked artifact still costs registry tokens. |
| ceiling `near-done` high at the shipped row | ceiling too low | Raise `DEV_TEAM_CONTEXT_ABS_CEILING` — [ADR 0037](adr/0037-block-by-default-at-the-context-ceiling-2000.md) is explicit that the answer is not a return to warn-by-default. |
| ceiling `tokens over` high at every candidate | ceiling too high, or wrong lever | Re-derive per [ADR 0038](adr/0038-raise-the-absolute-context-ceiling-to-350k.md), and amend it with what the corpus says. |
| ceiling `advisory_fires` high against a low block rate | delegation used to evade the ceiling | [ADR 0039](adr/0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md)'s revisit trigger: the answer is a session-total cost control, not re-blocking dispatches. |
| `unrecognized_model_sessions` non-zero | guard is guessing | A model id has outrun `_LARGE_WINDOW_RE`. Its verdicts warn instead of blocking, so the ceiling is unenforced for those sessions until the pattern is taught the new id. |

**Change one thing per round.** Two changes between rounds and the next delta
attributes to neither. This is the whole reason the streams are append-only:
a round is only evidence if it can be pinned to a known before-state.

### 5. Write down what changed

Append a one-line note to the round's PR or the relevant ADR: the date, the
one change made, and the metric it was meant to move. Next round's step 3 is
reading for exactly that.

## What this playbook cannot tell you

Stated plainly, because a review procedure that implies more coverage than it
has is the same failure as a gate that cannot fail:

- **Causation.** Both streams are observational. A metric that moves after a
  change is consistent with that change, not proof of it.
- **Sample size.** Neither stream records confidence intervals, and a
  maintainer's month is a small n. Treat a single round's percentage move as a
  hypothesis, not a finding.
- **Anything outside a gated call.** The ceiling stream is blind to occupancy
  that never met a blockable call, by construction. See [Validating the
  context ceiling](context-ceiling-validation.md).
- **Session-total cost.** No instrument here bounds what a session spends in
  total; the ceiling bounds main-thread *occupancy*, which is a different
  quantity. ADR 0039 records why the two must not be conflated, and
  `hooks/lib/cost_meter.py` is the instrument that measures the other one.
