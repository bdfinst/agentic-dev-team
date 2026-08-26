# 39. Only Skill loads are worth blocking at the context ceiling

Date: 2026-08-26

## Status

Accepted

Amends [11. Enforce the context ceiling with a transcript-measured PreToolUse
hook](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md),
which grouped `Agent` and `Skill` as a single class of "capability loads".
[ADR 0037](0037-block-by-default-at-the-context-ceiling-2000.md)'s blocking
default and [ADR 0038](0038-raise-the-absolute-context-ceiling-to-350k.md)'s
350K threshold are both unchanged.

## Context

ADR 0011 chose what to gate before there was anything to block. Its reasoning:

> **Capability loads (`Agent` + `Skill`).** Chosen: these are exactly the
> "don't load speculatively" operations the protocol governs, far less
> frequent than Read, and safe to block because recovery never needs a fresh
> agent.

Grouping them was reasonable while the guard only warned — a warning on either
one says the same useful thing, and "capability load" is a fair description of
both. Under ADR 0037's blocking default the grouping stopped being harmless,
because the two tools do **opposite things to the quantity this guard
measures**:

- A **`Skill` invocation** loads `SKILL.md` into the main thread. It grows
  main-thread occupancy directly, and declining it prevents that growth. A
  block does what it says.
- An **`Agent`/`Task` dispatch** runs in a *separate* context and returns only
  its result. It is the cheapest available way to do a unit of work without
  growing this context. Blocking it does not stop the work — the orchestrator
  still has `Read`, `Edit`, `Bash`, and the task still needs doing, so the work
  happens **inline instead**, growing occupancy by more than the delegation
  would have.

So on a 1M-window session sitting at 400K, the guard's block on a review
dispatch does not save 400K from growing; it converts a ~2K result summary into
tens of thousands of tokens of inline file reading. The guard makes the number
it is protecting worse.

This repo already settled the underlying question, on the other side of the
same hook. #2054 excluded sidechain rows from `_measure_occupancy` because *a
subagent's context is not this thread's context* — that is why a subagent turn
recorded inline must not be read as main-thread occupancy. The gating side was
never updated to match. If a subagent's tokens are not main-thread occupancy,
then blocking a subagent dispatch to protect main-thread occupancy is
incoherent.

**The honest cost of this change.** Blocking `Agent` did do one useful thing
incidentally: it was a second chokepoint that could force a session to stop and
run `/handoff`, and dropping it means an over-budget session has one fewer place
where it must confront the ceiling. That is a real reduction in pressure, and it
is accepted deliberately, for two reasons. First, the pressure was bought by
making the session more expensive, which is the opposite of what ADR 0037 set
out to achieve. Second, using an occupancy ceiling as a proxy for session-total
cost conflates two different quantities with two different correct thresholds —
the same category error [ADR 0038](0038-raise-the-absolute-context-ceiling-to-350k.md)
corrected when it found 150K had been borrowed from a system measuring something
else. If session-total cost needs a control, it needs its own instrument
(`hooks/lib/cost_meter.py` already measures the right quantity), not a
side effect smuggled into a guard on a different number.

## Decision

Of the gated tools, only `Skill` blocks. `Agent` and `Task` still fire the
guard — the occupancy diagnostic and the escalating action bands are unchanged
— but they warn and proceed, carrying a `[not blocked: delegation]` footer
explaining why, so the non-block does not read as the guard failing to fire.

`DEV_TEAM_CONTEXT_GATE_AGENT=block` restores the previous behavior.

That opt-in is deliberately **not** spelled the way `DEV_TEAM_CONTEXT_STRICT`
is. `STRICT` treats every unrecognized value as "block", because its expensive
direction of failure is silently not enforcing. Here the expensive direction is
the reverse — blocking a dispatch that should not be blocked — so only the
literal `block` opts in and anything else resolves toward the new default. The
two variables point opposite ways on purpose.

`scripts/context_ceiling_report.py` follows the same split, reading
`_BLOCKING_TOOLS` from the guard rather than restating it: its block columns
count `Skill` invocations only, agent dispatches are reported as advisory
fires, and a session whose only gated calls are dispatches is excluded from the
block-rate denominator entirely, since it can never be blocked at any ceiling.
Leaving the report counting both would have overstated every candidate's block
rate and argued for a higher ceiling than the evidence supports.

## Consequences

**What gets better.** The guard stops making main-thread occupancy worse in the
one case where it had that effect, and delegation — the behavior the Context
Loading Protocol actually wants from an over-budget orchestrator — is no longer
penalized at exactly the moment it is most valuable.

**What gets worse.** One chokepoint fewer for forcing a handoff, as above. An
operator who wants it back sets `DEV_TEAM_CONTEXT_GATE_AGENT=block`.

**What this does not change.** Blocking remains the default posture for
`Skill`, only `off` opts out of it, recovery skills remain ungated, fail-open
is unchanged, and the 350K threshold is untouched.

**Revisit trigger.** If measurement shows sessions routinely running far past
the ceiling *by dispatching agents* — visible as a high `advisory_fires` count
against a low block rate in the ceiling report — then delegation is being used
to evade the ceiling rather than to economize, and the right answer is a
session-total cost control, not re-blocking dispatches.

## Notes

Issue #2062. Found during the context-guard review that also produced #2054,
#2056, and #2060; held back from each of those because it changes *what* the
guard gates rather than what it measures or where its threshold sits.
