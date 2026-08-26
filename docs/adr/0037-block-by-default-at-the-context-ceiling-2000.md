# 37. Block by default at the context ceiling

Date: 2026-08-25

## Status

Accepted. Reverses the "warn by default, opt-in block" decision recorded in
[ADR 0011](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md);
that ADR otherwise stands — the mechanism, the transcript-measured occupancy,
the recovery-skill exemption, and the fail-open posture are all unchanged.

## Context

ADR 0011 chose warn-by-default deliberately, and the reasoning was sound at the
time:

> **Warn by default, opt-in block.** Chosen: mirrors `destructive-guard.sh` /
> `/careful` (warn on exit 0, block on exit 2). `DEV_TEAM_CONTEXT_STRICT=on`
> escalates to a hard block. A warn-default also means a wrong window only
> over-nudges, never bricks a session.

The hedge was against a *measurement* error: an unknown model, a bad window,
an occupancy read that was wrong. Warning rather than blocking meant such an
error cost a spurious nudge instead of a stalled session.

That risk has since been retired by other work. The window is auto-detected per
model family with a conservative 200K fallback for anything unrecognized, the
threshold is additionally capped at an absolute 150K, and the whole hook is
fail-open — a missing transcript, an unparseable usage line, or any internal
error exits 0. A wrong window can no longer brick a session, because a window
it cannot resolve does not produce a verdict at all.

What the hedge did not anticipate is that the *other* failure mode would
dominate. Session telemetry over 2,393 sessions:

| signal | measured |
|---|---|
| sessions past 500K occupancy | 76 |
| sessions past 900K occupancy | 18 |
| share of main-thread spend from those 18 | 29% |
| per-turn cost at 900K vs under 100K | ~3x |
| `handoff` invocations | 3 |
| `context-loading-protocol` invocations | 1 |
| compaction events | 30 |

The guard was firing. Its warnings named the ceiling, the binding bound, and
the recovery skill, and escalated through three action bands as occupancy
climbed. Sessions ran past 900K anyway.

This is the failure `CLAUDE.md` already names in another context: *a gate that
cannot fail is worse than no gate — it reads as a guarantee and delivers none.*
A ceiling documented as "enforced by `hooks/context_ceiling_guard.py`" that in
practice never stopped anything is worse than no ceiling, because it is cited
as a control while behaving as a suggestion.

## Decision

Blocking is the default posture. `DEV_TEAM_CONTEXT_STRICT=off` opts back down
to a warning; every other value, **including the historical opt-in spelling
`on`**, blocks.

Three properties make a blocking default safe, and each is now pinned by a
test rather than left as prose:

1. **Recovery skills are never gated.** `/handoff`,
   `/context-loading-protocol`, `/continue`, `/review-summary`, and
   `/session-review` pass at any occupancy. This exemption was cosmetic while
   the default was warn — nothing was blocked, so nothing could deadlock. It
   is now the only thing between an over-budget session and one that cannot
   act at all, including to recover.
2. **Fail-open is unchanged.** Unmeasurable context, a missing transcript, a
   malformed env var, or any internal error still exits 0. The guard blocks on
   what it *knows*, never on what it failed to read.
3. **Every block names `/handoff`.** The top action band drops the knob
   footer, so the recovery path could not live only there; a dedicated block
   footer carries it in every case. A block that does not state the way out
   gets the guard disabled wholesale rather than obeyed.

The opt-out is deliberately not boolean. Only the literal `off` (case- and
whitespace-insensitive) disables blocking, so a typo'd value resolves toward
enforcement. This is the opposite of the usual convention and is chosen for
the same reason as the decision itself: the expensive direction of failure
here is silently *not* enforcing.

## Consequences

**What gets better.** The ceiling becomes a control rather than a suggestion.
Recovery estimated at $1.5–2k/month on the measured corpus, though the estimate
rides on a default value and should be re-measured after a month of real use
rather than assumed.

**What gets worse.** Sessions that previously sailed past the ceiling now stop
and must run `/handoff`. That is the intended cost, but it is a real workflow
change for anyone accustomed to ignoring the warning, and the block arrives at
150K on a 1M-context model — early, by design, per the absolute cap.

**The escape hatches are unchanged and documented in the same places as
before**: `DEV_TEAM_CONTEXT_STRICT=off` for a warning,
`DEV_TEAM_CONTEXT_CEILING=off` to disable, `DEV_TEAM_CONTEXT_CEILING_PCT` and
`DEV_TEAM_CONTEXT_ABS_CEILING` to move the threshold.

**Revisit trigger.** If the block rate turns out to be dominated by sessions
that were legitimately near-done — blocked at 150K on work that would have
finished in another two turns — the right response is to raise
`DEV_TEAM_CONTEXT_ABS_CEILING`, not to return to warn-by-default. The
measurement above says the advisory posture does not work; a wrong threshold is
a different problem with a different knob.

## Notes

Issue #2000. The change is small — one conditional and a footer — but the
deliberate-failure test is the substance of it: this repo's rule is *when you
add a gate, make it fail on purpose once before you trust it*, and a flip that
left the guard still warning would report as fixed while changing nothing.

## Amendment (2026-08-26)

Two of this ADR's safety properties were asserted rather than implemented.
Both are now closed in code with deliberate-failure tests; the decision
itself — blocking by default — is unchanged.

**"A window it cannot resolve does not produce a verdict at all" was not
true.** The Context section above justified the flip partly on that claim.
`_resolve_window` does not decline to produce a verdict for an unresolvable
window: it returns the conservative 200K fallback tagged `default`, and the
guard went on to a full blocking verdict against it. Provenance reached the
message text and nothing else. So an unrecognized model id — on a model
whose real window may be 1M — hard-blocked every capability load from 80,000
tokens onward, at 8% of the real window. `_LARGE_WINDOW_RE` is version-pinned
by deliberate design ([ADR 0011](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md)'s
amendment), which means *every model released after it was last edited* lands
in that case until someone edits the pattern.

The fallback's original rationale is explicit that it was written for a
different posture: "over-nudging a 1M session is a minor false alarm." Under
warn-by-default it was. Under this ADR it is a session that cannot dispatch
an agent or invoke a skill. The asymmetry argument survives — an unknown
model is still never assumed large, so the guard still *reports* — but its
consequence is now downgraded: a `default`-provenance verdict warns with a
`[not blocked: window unverified]` footer naming `DEV_TEAM_CONTEXT_WINDOW`.
`override` and `detected` provenance block exactly as this ADR specifies.
This is the same principle as consequence 2 above, applied one layer out: the
guard blocks on what it knows, and it does not know an unrecognized model's
window.

**Occupancy could be measured from the wrong context.** `_measure_occupancy`
took the most recent usage-bearing transcript row unconditionally, including
rows marked `isSidechain` — subagent turns, whose usage describes the
subagent's context rather than the main thread's. Under the harness layout
that records sidechain turns inline, a 5K subagent turn recorded after a 190K
main turn made the guard measure 5K and allow the load: silent
non-enforcement, the exact failure this ADR exists to remove, arriving
through the measurement instead of the posture. The reverse also held — a
large subagent turn blocked a main thread at 10% of its window.
`scripts/session_extract.py` and `scripts/measure_full_file_duplication.py`
both already filtered on `isSidechain`; this hook was the transcript consumer
that did not. Both scans now skip sidechain rows.

Neither gap was caught by the #2000 test suite because every window-detection
test runs under `_base_env`, which pins `DEV_TEAM_CONTEXT_STRICT=off`. The
existing `test_unrecognized_model_falls_back_to_200000` asserts
`returncode == 0` — correct for warn mode, and silent about the shipped
default. The new cases run under `_posture_env`, which sets no posture
variable at all, and each was confirmed to fail with its fix reverted.
