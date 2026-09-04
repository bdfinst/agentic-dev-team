# Validating the context ceiling

The context ceiling enforced by `hooks/context_ceiling_guard.py` is a
judgement call, and [ADR 0038](adr/0038-raise-the-absolute-context-ceiling-to-350k.md)
named the weakest part of the reasoning behind its current 350K value:

> The turn-count estimate above is the weakest link in this reasoning — it is
> an inference from a token ratio, not a recorded count. If per-session peak
> occupancy is ever instrumented directly, re-derive the threshold from the
> actual distribution.

`scripts/context_ceiling_report.py` is the instrument that replaces that
inference. It replays real session transcripts, reconstructs the occupancy the
guard *would have measured* at every capability load, and reports what each
candidate ceiling would have done.

This is maintainer tooling. It lives at the repo root and is **not shipped**
with the plugin — see [ADR 0014](adr/0014-python-for-cross-os-scripts.md) on
the scope split. For the shipped guard's own user-facing guide (what it
measures, how to read its warning, which knobs exist), see
[`plugins/dev-team/docs/context-management.md`](../plugins/dev-team/docs/context-management.md).

## Running it

```bash
# default corpus: ~/.claude/projects/**/*.jsonl
python3 scripts/context_ceiling_report.py

# narrower corpus, custom sweep, machine-readable output
python3 scripts/context_ceiling_report.py \
  --transcripts ~/.claude/projects/-home-me-myproject \
  --ceilings 150000,250000,350000,450000 \
  --json /tmp/ceiling-report.json
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--transcripts` | `~/.claude/projects` | Files or directories to replay; directories are searched recursively for `*.jsonl`. |
| `--ceilings` | `150000,…,600000` | Comma-separated candidate absolute ceilings to sweep. |
| `--ceiling-pct` | `40` | The percentage-of-window bound, matching `DEV_TEAM_CONTEXT_CEILING_PCT`. |
| `--near-done-turns` | `5` | Assistant turns remaining at or below which a blocked session counts as "near done". |
| `--append` | — | Append one metrics-only record to a trend stream, so rounds are comparable. |
| `--shipped` | `350000` | Which row to mark and summarize in the verdict. |
| `--json` | — | Also write the full per-session result for scripting. |

## Reading the sweep

A single "N% of sessions blocked" number cannot tell the two failure
directions apart, so the report prints a column for each:

| Column | Direction it detects | What a bad number looks like |
| --- | --- | --- |
| `near-done` | ceiling too **low** | a high share of blocked sessions were within a few turns of finishing — [ADR 0037](adr/0037-block-by-default-at-the-context-ceiling-2000.md)'s revisit trigger, verbatim |
| `turns left` | ceiling too **low** | blocks landing with a lot of work still to come, i.e. mid-flight rather than at the end |
| `tokens over` | ceiling too **high** | a large share of corpus prompt tokens was spent past the first block, i.e. the expensive tail ran anyway |

**Read `near-done` and `turns left` together — the first is a threshold and
cannot stand alone.** The first real corpus (306 sessions) made this concrete:
`near-done` sat at 0-6% across *every* candidate from 150K to 600K. Taken by
itself that reads as "no ceiling over-blocks anywhere", which would argue for
lowering the ceiling without limit. It only ever detected one shape — blocked
*at* the finish line. A session blocked at 20% done is not near-done, and
blocking it still costs a handoff and the re-establishment of everything it had
loaded. `turns left` is the median work remaining when the block landed, which
is the quantity `near-done` was standing in for. A near-done of 0 beside a
large turns-left means blocks are landing mid-flight.

A better ceiling lowers `near-done` without letting `tokens over` climb. The
report deliberately does not collapse these into a score or pick a number for
you — the cost of a wrong ceiling is asymmetric in a way no single statistic
captures, and the 150K→350K move happened precisely because a number got
adopted without that trade-off being visible.

Sample output, against a synthetic corpus:

The first real corpus — 306 sessions, 79 with a blockable call:

```text
  ceiling |  sessions |  blocked |  blocks |  median@1st |  near-done |  tokens over
------------------------------------------------------------------------------------
  150,000 |        79 |    68.4% |     145 |     188,662 |       1.9% |        71.3%
  250,000 |        79 |    41.8% |      92 |     333,142 |       6.1% |        51.0%
  350,000 |        79 |    26.6% |      65 |     399,708 |       0.0% |        35.8% *
  450,000 |        79 |    21.5% |      51 |     444,816 |       0.0% |        31.3%†
  600,000 |        79 |    21.5% |      51 |     444,816 |       0.0% |        31.3%†
```

Two things to notice, both of which drove changes to this tool. The last two
rows are identical because they are **one** candidate — 40% of a 1M window
clamps both to 400K, which is what `†` says. And `near-done` never rises above
6%, which is the reading that showed a threshold alone cannot adjudicate a
ceiling. See [ADR 0038's second
amendment](adr/0038-raise-the-absolute-context-ceiling-to-350k.md).

## Four properties worth knowing before acting on its output

**It counts blocks, and only `Skill` blocks.** Per [ADR
0039](adr/0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md),
an `Agent`/`Task` dispatch over the ceiling warns and proceeds, so the sweep's
block columns count skill invocations only; dispatches appear as
`advisory_fires`, and a session whose only gated calls are dispatches is left
out of the block-rate denominator entirely, since no ceiling could ever block
it. The split is read from the guard's `_BLOCKING_TOOLS` rather than restated,
so it cannot drift.

**It conditions on gated calls, not on occupancy.** The ceiling only binds at
an `Agent`/`Skill` call, so a session can sit far above any candidate and
never trip it. This is not a detail — it is the flaw the tool was built to
correct. ADR 0038's own occupancy figures are per-turn averages, and the guard
does not fire per turn, so reasoning from occupancy alone systematically
*overstates* how often a given ceiling binds. The report's peak-occupancy
table carries an explicit warning against reading it as a block rate.

**A candidate above `ceiling_pct` of the window does nothing.** The effective
threshold is `min(pct% of window, cap)`, so on a 1M window at the default 40%,
no cap above 400K changes anything. Those rows are marked `†` rather than
being left to look like genuine data points — a sweep row that silently equals
its neighbour reads as "the ceiling made no difference" when the truth is
"this candidate was never applied". Raise `--ceiling-pct` too if you want to
test past that point.

**An empty result is reported as inconclusive, never as confirmation.** If no
session in the corpus reached the ceiling at a gated call, the verdict says so
and asks for a larger corpus. "0 blocked" on data containing no evidence is
not evidence the ceiling is right — that is this repo's *a gate that cannot
fail is worse than no gate* rule applied to the measurement itself.

## Why it cannot drift from the guard

Every policy decision — which tools are gated, which skills are exempt, how a
model maps to a window, how occupancy is summed, what counts as a sidechain
row — is **imported** from
[`plugins/dev-team/hooks/context_ceiling_guard.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/hooks/context_ceiling_guard.py)
rather than restated. A validator that measured the ceiling even slightly
differently from the guard would be validating a threshold nobody ships.

[`tests/scripts/test_context_ceiling_report.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/tests/scripts/test_context_ceiling_report.py)
additionally pins the report's occupancy walk against the hook's own
`_measure_occupancy` on shared fixtures, in the same spirit as the hook
suite's utilization-formula equality test.

## Acting on the result

When the corpus is large enough to return a verdict other than "inconclusive",
amend [ADR 0038](adr/0038-raise-the-absolute-context-ceiling-to-350k.md) with
what it says. Both of that ADR's revisit triggers are now measurable rather
than hypothetical:

- `near-done` dominating the blocked population → the ceiling is too low; raise
  `DEV_TEAM_CONTEXT_ABS_CEILING`, per ADR 0037's explicit instruction not to
  return to warn-by-default instead.
- sessions again running far past the ceiling, with `tokens over` high at every
  candidate → the ceiling is too high, or the guard is not binding where the
  spend happens.
