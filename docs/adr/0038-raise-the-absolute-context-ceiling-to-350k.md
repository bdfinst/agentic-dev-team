# 38. Raise the absolute context ceiling from 150K to 350K

Date: 2026-08-26

## Status

Accepted

Amends [37. Block by default at the context ceiling](0037-block-by-default-at-the-context-ceiling-2000.md).
That ADR's decision — blocking by default — stands unchanged. This one moves
the threshold it blocks at, using the knob ADR 0037 itself named as the
correct response.

## Context

ADR 0037 flipped the posture from warn to block and left the threshold where
it was. That threshold, `DEV_TEAM_CONTEXT_ABS_CEILING`, has been 150,000
tokens since #786. Flipping the posture changed what a wrong threshold costs,
and the number was never re-derived against that new cost.

**The number was borrowed, not measured.** `docs/context-management.md`
sourced it as "the Claude API's own compaction default is 150K absolute
tokens even on 1M-window models." That is a different system's default,
adopted for its authority rather than derived from this plugin's behavior —
and notably not the harness this plugin actually runs under, which
[ADR 0016](0016-rely-on-harness-native-compaction-the-plugin-performs-structured-summarization-only.md)
records as auto-compacting at ~83.5% of the window (~835K on 1M). The plugin
pinned its enforcement point to a constant from a system it had explicitly
decided not to rely on.

**The evidence in ADR 0037 does not reach the threshold.** Its telemetry
measures where sessions ran and what they cost:

| signal | measured |
|---|---|
| sessions past 500K occupancy | 76 of 2,393 (3.2%) |
| sessions past 900K occupancy | 18 of 2,393 (0.75%) |
| share of main-thread spend from those 18 | 29% |
| per-turn cost at 900K vs under 100K | ~3x |

That is strong evidence an enforced ceiling is needed. It contains no
evidence that 150K is where it belongs — the cost signal only becomes
visible at 500K. Any threshold between roughly 200K and 450K catches all 76
of those sessions and all 18 of the expensive ones. Setting the block at 150K
to solve a problem measured at 500K+ over-corrects by roughly 3x.

**On this repo's own corpus, 150K is below the working point, not above it.**
From `memory/session-digest.json` — the 32 `agentic-dev-team` sessions —
total prompt-side tokens (`input + cache_read + cache_creation`) are
1,386,189,996 against 4,388,981 output tokens, a 316:1 ratio. Dividing by
assistant-turn count gives average per-turn occupancy:

| assumed assistant turns | turns/session | avg occupancy |
|---|---|---|
| 3,718 (= recorded `tool_calls`, a hard lower bound) | 116 | 373K |
| 5,000 | 156 | 277K |
| 7,000 | 219 | 198K |
| 10,000 | 312 | 139K |

Turn count is not recorded directly, so this is an estimate — but
`tool_calls` floors it, and 312 assistant turns per session is already
implausibly high. The realistic range puts average per-turn occupancy at
200–370K, i.e. **1.3–2.5x the threshold that ADR 0037 made blocking**. The
figure also includes subagent turns, which are smaller and drag the average
down, so main-thread occupancy is higher still.

A ceiling below the median working point does not gate the tail; it gates the
ordinary case. Every routine multi-agent session stops at its next `/build`,
`/code-review`, or `/pr`, and the only escape is `DEV_TEAM_CONTEXT_STRICT=off`
or `DEV_TEAM_CONTEXT_CEILING=off` — at which point the protection against the
900K tail leaves with it. That is this repo's own *a gate that cannot fail is
worse than no gate* arriving from the opposite direction: a gate tight enough
that switching it off becomes the normal workflow enforces nothing, and does
it while reading as a control.

ADR 0037 anticipated exactly this and named the remedy: *"If the block rate
turns out to be dominated by sessions that were legitimately near-done …
the right response is to raise `DEV_TEAM_CONTEXT_ABS_CEILING`, not to return
to warn-by-default."* This ADR is that response, taken from the measured
distribution rather than after a month of accumulated friction.

## Decision

`DEV_TEAM_CONTEXT_ABS_CEILING` defaults to **350,000** tokens.

On a 1M window the effective ceiling becomes `min(400K, 350K)` = 350K, with
bands at 350K (nudge), 437.5K (run-now), and 525K (full-summary). On a 200K
window nothing changes: 40% = 80K, still well under the cap, still the
percentage bound.

350K is chosen to sit above the measured working range and below the measured
cost problem. It blocks every session in ADR 0037's expensive population — all
76 past 500K, all 18 past 900K — while leaving ordinary multi-agent work
unblocked. The remaining knobs are unchanged.

The docs are reconciled to the number that actually binds. "40% ceiling" is
what `CLAUDE.md` and three skills led with, but the percentage governs only
200K windows; on every model this plugin currently runs against, the absolute
cap binds and the shipped ceiling is a flat 350K, or 35% of the window. The
percentage remains the planning target for the Context Loading Protocol's
budget estimate, where it is applied before any measurement exists.

## Consequences

**What gets better.** The ceiling stops firing on ordinary sessions, which is
what keeps the escape hatches unused and the tail protection real. The
enforcement point is now derived from this plugin's own measurements instead
of another system's constant.

**What gets worse.** Sessions between 150K and 350K that genuinely would have
benefited from an earlier handoff no longer get a hard stop. They still get
nothing at all below 350K — the guard is silent under its ceiling by design —
so the earlier structured-summarization opportunity is lost for that band.
Operators who want the old behavior set `DEV_TEAM_CONTEXT_ABS_CEILING=150000`.

**What this does not change.** Blocking remains the default posture, only
`off` opts out, recovery skills remain ungated, and fail-open is unchanged.
Nothing here reopens the question ADR 0037 settled.

**Revisit trigger.** The turn-count estimate above is the weakest link in this
reasoning — it is an inference from a token ratio, not a recorded count. If
per-session peak occupancy is ever instrumented directly, re-derive the
threshold from the actual distribution and correct this number in either
direction. A second trigger, symmetric to ADR 0037's: if sessions again run
past 500K at a meaningful rate, the threshold is too high, not the posture
wrong.

## Notes

Found while reviewing the guard's size limit alongside two measurement
defects fixed separately — sidechain rows counted as main-thread occupancy,
and an unverified fallback window producing a full blocking verdict. Those
are correctness bugs in what the guard measures; this is a judgement call
about where the line goes, which is why it is a separate decision.

## Amendment (2026-08-26)

The revisit trigger above asked for per-session peak occupancy to be
instrumented directly, so the threshold could be re-derived from a recorded
distribution instead of a token-ratio inference. That instrument now exists:
`scripts/context_ceiling_report.py`, with
`tests/scripts/test_context_ceiling_report.py` pinning its measurement to the
guard's own.

Building it surfaced a flaw in the reasoning this ADR used, which does not
change the decision but does change how the next one should be argued. The
occupancy figures in the Context section are **per-turn averages**, and the
ceiling does not fire per turn — it fires only at a capability load. A session
can sit at 600K indefinitely without ever tripping the guard, if it never
dispatches an agent or invokes a skill while up there. So an
occupancy-derived threshold is derived from the wrong distribution: it
overstates how often any given ceiling actually binds. The tool therefore
conditions on gated calls rather than on occupancy, and its peak-occupancy
table carries an explicit warning against reading it as a block rate.

The direction of that error favors the decision this ADR made — the real
block rate at 150K is *lower* than the per-turn average implied, so the
over-correction argument is weaker than stated, while the evidence that 150K
was a borrowed rather than measured number is untouched. Treat the 350K value
as still resting mainly on the second argument until the report has been run
over a corpus large enough to return a verdict other than "inconclusive".

Re-deriving the threshold is now a command, not a project. Run it, read the
`near-done` and `tokens over` columns together, and amend this ADR with what
the corpus says.

## Amendment (2026-08-26, second) — the first measured corpus

`scripts/context_ceiling_report.py` has now been run over a real corpus: 306
sessions, 79 of them making at least one blockable call, 3,055 gated calls.
This is the measurement the revisit trigger above asked for, and it does not
confirm this ADR's reasoning. It retires part of it.

| candidate | sessions blocked | near-done (abs) | tokens past first block |
|---|---|---|---|
| 150,000 | 68.4% | 1 session | 71.3% |
| 200,000 | 53.2% | 1 | 58.4% |
| 250,000 | 41.8% | 2 | 51.0% |
| 300,000 | 34.2% | 1 | 47.5% |
| **350,000 (shipped)** | **26.6%** | **0** | **35.8%** |
| 450,000 / 600,000 | 21.5% | 0 | 31.3% |

(The last two rows are one candidate, not two: both clamp to 40% of a 1M
window. The trend record was dropping the field that says so; fixed alongside
this amendment.)

**The occupancy estimate this ADR rests on was wrong by 3-5x.** It reasoned
from a 316:1 prompt:output ratio to "200-370K average per-turn occupancy" and
concluded 150K sat below the median working point. Measured, the median
session's *peak* occupancy is **74,950** — half of all sessions never reach
half of the old ceiling, let alone the new one. The distribution is not
centered anywhere near either value; it is sharply skewed, p90 at 618K against
that 75K median, and only 26% of sessions make a blockable call at all. The
ceiling is simply irrelevant to three quarters of sessions.

**The over-blocking case for raising to 350K is not in the data.** This ADR
argued 150K would stop ordinary work. At 150K exactly **one** blocked session
was near done. At every candidate the near-done count is 0-2 sessions. Whatever
150K was doing wrong, it was not blocking sessions at the finish line.

**But the data cannot justify lowering it either, and that is a defect in the
instrument, not a finding.** `near_done_blocked_pct` is a *threshold* — it
detects one failure shape, "blocked at the finish line", and collapses
everything else into "fine". Read naively, a metric that sits at 0-6% across
every candidate from 150K to 600K argues for lowering the ceiling without
limit, which is plainly wrong: a session blocked at 20% done is not near-done,
yet blocking it still costs a handoff and the re-establishment of everything
it had loaded. The report now also emits
`median_remaining_turns_at_first_block`, which measures how much work a block
actually interrupts, precisely because the threshold alone could not adjudicate
this question.

**Decision: 350K stands, and the next move waits for the better metric.** Not
because the data endorses it — it does not — but because the two arguments that
could move it are both currently unsound. The argument that raised it is
retired. The argument for lowering it rests on a metric now known to be
insufficient for the purpose. Moving a threshold on a measure known to be the
wrong shape is exactly how 150K was arrived at, and repeating that with a
different number would not be progress.

What survives of this ADR unchanged is the narrower claim: 150K was borrowed
from the Claude API's managed-compaction default rather than derived from this
plugin's behavior, and a threshold nobody measured should not be treated as
one somebody chose. That remains true and remains the reason not to go back.

**Next round.** Re-run after the corpus has accumulated
`median_remaining_turns_at_first_block` at each candidate, per
[the session economy playbook](../context-and-session-economy-playbook.md). A
ceiling whose blocks land with few turns remaining is doing its job; one whose
blocks land mid-flight, however low its near-done rate, is not.

## Amendment (2026-08-26, third) — ADR 0039's revisit trigger has already fired

The same corpus fires the trigger
[ADR 0039](0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md)
set for itself — "a high `advisory_fires` count against a low block rate". At
the shipped 350K the ratio is **24:1**: 1,562 agent dispatches over the ceiling
against 65 blocks. Corpus-wide, **93% of all gated calls are delegations**
(2,841 of 3,055), not skill loads.

Read carefully, that number cuts both ways and only one reading is supported.

It is decisive validation of ADR 0039 itself: under the previous behavior every
one of those 1,562 dispatches would have been a hard block, on sessions that in
most cases had already passed the ceiling. The change did not soften a rare
edge case; it removed the guard's most frequent action by a factor of 24.

Whether it is *also* evasion — delegation used to keep working past a ceiling
rather than to economize — this corpus cannot say, because nothing here
distinguishes a dispatch that saved main-thread tokens from one that merely
deferred a handoff. ADR 0039 already names the answer if it turns out to be
evasion, and that answer is unchanged by this measurement: a session-total cost
control, measured by `hooks/lib/cost_meter.py`, not re-blocking dispatches.
Re-blocking would restore 1,562 blocks to buy a signal the occupancy guard was
never measuring.
