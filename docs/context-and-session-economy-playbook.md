# Session economy playbook

A recurring procedure for reading session logs *over time*, so the plugin keeps getting cheaper to run and re-does less work.

Every instrument this playbook uses already existed as a one-shot command.
What was missing was the loop: a cadence, a fixed order, a decision rule per
signal, and an append-only stream that makes one round comparable to the
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
| How much did *that run* cost? | [`/cost-report`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/cost-report/SKILL.md) |
| How did *that run* go, step by step? | [`/run-report`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/run-report/SKILL.md) |
| What should we change, based on recent sessions? | [`/session-review`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/session-review/SKILL.md) |
| Which agents/routing have gone stale? | [`/harness-audit`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/harness-audit/SKILL.md) |
| Which skills and agents are unused? | [`/artifact-lifecycle`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/artifact-lifecycle/SKILL.md) |
| Is autocompact configured for this repo? | [Context Management](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/docs/context-management.md) |

This playbook is the **longitudinal** layer over those: run them in a fixed
order on a fixed cadence, persist the comparable subset, and act on the deltas
rather than on any single round's absolute numbers.

## Cadence

**Monthly**, and additionally whenever one of these lands:

- a change to the autocompact threshold ([ADR 0043](adr/0043-replace-the-context-ceiling-guard-with-harness-autocompact.md));
- a model change (a new default model resizes every window);
- a batch of agent, skill, or hook changes large enough that you would not be
  able to attribute a later regression to it.

Monthly is deliberate rather than weekly. The stream is per-session
aggregates, and a week of one maintainer's work is too few sessions for a
percentage to mean anything — a 2-of-9 blocked rate reads as 22% and is noise.
A round that cannot distinguish signal from sample size is worse than no round,
because it invites action on both.

## The rounds

Run in this order. Each step's output is input to the next.

### 1. Refresh the session stream

```bash
python3 plugins/dev-team/scripts/session_report.py --profile maintainer \
  --plugin-root plugins/dev-team \
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

### 2. Read the deltas, not the levels

```bash
python3 -c "
import json, pathlib
p = pathlib.Path('.claude/metrics/session-digest.jsonl')
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
print(f'== session-digest: {len(rows)} rounds ==')
for r in rows[-2:]:
    print(' ', r.get('recorded_at'), json.dumps(r)[:160])
"
```

A single round's absolute numbers are close to meaningless — the corpus
changes shape every month. What carries information is the *direction* of a
metric across rounds against a change you can name.

### 3. Decide

One rule per signal. Each names the action and, where one exists, the ADR
whose revisit trigger it discharges.

| Signal | Direction | Action |
| --- | --- | --- |
| `rework.repeated_file_edits` / `repeated_verify_runs` rising | worse | Run `/session-review` for the *why*; this stream says only that it happened. |
| `gate.bypass_rate` rising | worse | A gate is being routed around. Fix the gate's cost or its correctness — never its enforcement. |
| `accuracy.user_correction_turns` rising | worse | Instructions are being misread. Candidate for a CLAUDE.md or skill-prose fix, not a code fix. |
| `utilization.never_observed_*` growing | drift | Feed to `/artifact-lifecycle`; a never-invoked artifact still costs registry tokens. |
| `rework.compaction_events` high | compaction threshold too high, or wrong lever | Lower `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` via `/setup`, or write a `/handoff` summary before long phases ([ADR 0043](adr/0043-replace-the-context-ceiling-guard-with-harness-autocompact.md)). |

**Change one thing per round.** Two changes between rounds and the next delta
attributes to neither. This is the whole reason the stream is append-only:
a round is only evidence if it can be pinned to a known before-state.

### 4. Write down what changed

Append a one-line note to the round's PR or the relevant ADR: the date, the
one change made, and the metric it was meant to move. Next round's step 2 is
reading for exactly that.

## What this playbook cannot tell you

Stated plainly, because a review procedure that implies more coverage than it
has is the same failure as a gate that cannot fail:

- **Causation.** The stream is observational. A metric that moves after a
  change is consistent with that change, not proof of it.
- **Sample size.** The stream records no confidence intervals, and a
  maintainer's month is a small n. Treat a single round's percentage move as a
  hypothesis, not a finding.
- **Session-total cost.** No instrument here bounds what a session spends in
  total; autocompact bounds context *occupancy*, which is a different
  quantity. `hooks/lib/cost_meter.py` is the instrument that measures the
  other one.
