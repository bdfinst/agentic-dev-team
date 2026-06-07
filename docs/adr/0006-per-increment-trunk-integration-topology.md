# 6. Per-increment trunk integration topology for agent work

Date: 2026-06-07

## Status

Review

> Proposed for feedback (issue #112). This ADR records a *direction under
> consideration*, not an accepted decision. It is deliberately written before
> implementation so the thesis can be argued on its merits. Do not build from
> it until it is moved to **Accepted**.

## Context

The dev-team workflow is `/specs → /plan → /build → /pr`, with a human
approval gate between phases. Artifacts flow forward; nothing integrates until
the end of a build; the unit of integration is the completed plan.

External review (`docs/proposed-improvements-from-external-reviews.md`, #14;
`reports/agentic-dev-team-unknown-unknowns.md`, §1 and the Problem Dissolution)
named a tension: this is a stage-gated lifecycle, authored by someone whose
public work argues that stage gates *batch* risk rather than reduce it. The
sharper framing the reviews offer:

> The gates don't batch *work* — they batch *trust*. The human approves a plan,
> then trusts the machine through an entire build, integrating at the end.

Two observations make this concrete:

1. **`/plan` requires each step to leave the codebase *committable*, never
   *releasable*.** "Done means released" — the author's own long-standing test
   for process health — does not appear anywhere in the loop the agents follow.
2. **The system's whole premise is "merge is the moment of risk."** Four spec
   artifacts, four plan critics, three-stage inline review, a five-iteration
   fix loop, a pre-commit review gate, twenty review agents — all exist to
   *prove the code safe before it joins trunk*. That premise is optional when
   shipping is cheap and reversible (flags, canary, instant rollback,
   observability): the proof burden moves *after* the fact and most gates
   become monitors.

The unknown the repo never states: **what is the smallest deployable increment
of *trust* in an agent, and why is it "one approved plan" rather than "one
green TDD step / one flagged increment"?**

### Why this is an ADR and not a build

The reframe touches the deepest structural assumption in the plugin, depends on
infrastructure the plugin does not currently own (feature flags, rollback,
runtime observability), and — per the North Star — must demonstrate it reduces
real friction before it earns implementation effort. The right first artifact is
a written argument with explicit non-goals and a migration path, not code.

## Decision (proposed, under review)

Adopt **trust-batch-size** as the lens for where the human gate sits, and move
the workflow — incrementally, behind evidence — from *gating plans* toward
*gating exposures*:

1. **Each `/build` step integrates to trunk dark.** A step that `/plan` already
   requires to be committable also integrates behind a feature flag, rather than
   accumulating in a branch until the plan completes. The trust batch drops from
   "one feature" to "one increment."
2. **Review agents may run as post-merge monitors with auto-revert authority**,
   not only as pre-merge gates with a fix loop. When merging is dark and
   reversible, a failing monitor reverts the increment instead of blocking a
   human's merge. Which agents stay pre-merge gates vs. become post-merge
   monitors is itself a decision this ADR must enumerate (correctness/security
   likely stay gates; advisory/quality likely become monitors).
3. **The human approves *exposures* (flag flips), not *plans*.** The reviewable
   artifact becomes *running software per increment* — the third artifact the
   reviews note is more trustworthy than either 200 lines of plan or 2,000 lines
   of generated code.

This is a topology, not a switch: it coexists with the current gates and is
proven per-increment, not adopted wholesale.

## Required infrastructure (assumed or provided)

- **Feature-flag mechanism** the plugin can assume in a target repo (or scaffold
  via `/setup`), so each increment can integrate dark.
- **Rollback / auto-revert authority** for review monitors (revert a commit/PR
  by SHA), with an audit trail.
- **Runtime observability** to make post-merge monitoring meaningful — overlaps
  with the cost meter and `/session-review` digest.
- A decision on **what stays gate-based** (irreversible actions, schema/security
  surfaces) vs. what moves to monitor-and-revert.

## Consequences

**If accepted and it holds:**

- The question "is this agent's code safe to merge?" stops needing a perfect
  answer, because merging stops being the dangerous moment — risk shrinks
  because the blast radius did, not because review got better.
- The harness aligns with the CD thesis it was authored under; the human reviews
  behavior per increment instead of documents per phase.

**Costs and risks:**

- Requires flag/rollback/observability infra many target repos lack; without it
  the topology degrades to today's gates.
- Auto-revert authority for agents is a significant trust grant — needs tight
  scoping and an audit trail, or it becomes its own failure mode.
- Dark integration adds flag lifecycle (and flag debt) management.

## Non-goals

- **Not** removing the spec/plan artifacts or the review agents — relocating
  *when* trust is granted, not deleting the safety net.
- **Not** a wholesale replacement of the phase gates in one step.
- **Not** an implementation commitment. This ADR is a thesis to validate.

## Migration path (from today's phase gates)

1. Keep `/specs → /plan → /build → /pr` as-is.
2. Add optional flag-guarded integration for individual `/build` steps in repos
   that have flag infra.
3. Pilot one review agent as a post-merge monitor (advisory first, then with
   revert authority) and compare friction/escape rates against the pre-merge
   path.
4. Use `/session-review` evidence (which gates correlate with rework/bypass —
   the narrowed #111) to decide which gates are worth keeping pre-merge.
5. Revisit this ADR's status once there is evidence the current gates actually
   cause friction.

## Dependencies and references

- Evidence prerequisite: narrowed **#111** (which phases/gates correlate with
  rework/bypass, answered from the `/session-review` trend stream).
- Telemetry/observability: the cost meter (#102) and the session-digest.
- Source: `docs/proposed-improvements-from-external-reviews.md` (#14);
  `reports/agentic-dev-team-unknown-unknowns.md` (§1, Problem Dissolution).
- Tracking issue: #112.
