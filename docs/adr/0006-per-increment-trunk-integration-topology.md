# 6. Per-increment trunk integration topology for agent work

Date: 2026-06-07

## Status

Rejected

> Proposed for feedback (issue #112). This ADR records a *direction under
> consideration*, not an accepted decision. It is deliberately written before
> implementation so the thesis can be argued on its merits. Do not build from
> it until it is moved to **Accepted**.
>
> **Progress since first draft:** the flagging-method blocker (how to pick a
> flag mechanism across many stacks) is **resolved in principle** — see the
> Flag Capability Contract in *Required infrastructure*. The friction
> evidence prerequisite (#111) returned its first signal: bypassing the
> review gate correlated with ~2.6× the rework. Moving to **Accepted** still
> needs the cross-repo validation spike (see *Migration path*, step 3).

> **2026-07-20 — Rejected.** This ADR never left Proposed/Review; it was never
> moved to **Accepted** and no part of the topology was built. Its own gate for
> acceptance — the step-3 cross-repo validation spike in *Migration path*
> (validate the Flag Capability Contract across a vendor repo, a greenfield
> OpenFeature + flagd-file repo, and a no-flag degraded repo) — never landed,
> so the integrate-dark-per-increment thesis was never evidenced. In the
> interim its premises have been overtaken:
>
> - [ADR 0013](0013-llm-driven-orchestration-over-deterministic-workflow-scripts.md)
>   settled orchestration as LLM-driven rather than the deterministic
>   integrate-dark / monitor-and-revert topology this ADR assumed.
> - [ADR 0017](0017-single-build-cadence-remove-classic-tdd-opt-in.md) collapsed
>   `/build` to a single cadence, removing the "one green TDD step / one flagged
>   increment" trust-unit this ADR was framed around.
> - [ADR 0022](0022-reject-delegation-only-sweep-dispatch.md) established the
>   measure-a-win-before-shipping rule for dispatch changes, and recorded in
>   passing that the shipped PreToolUse hook layer did not load at all until
>   #1178 — the auto-revert/monitor enforcement substrate this topology depends
>   on had no working hook layer to build on.
>
> The Gate-vs-monitor split above is also stale: two of the agents it names
> (`test-modernization-review`, and the `/test-modernize` phase it gate-kept) no
> longer exist in the agents/skills trees. Rejected rather than superseded — no
> single later ADR replaces it; the direction was abandoned unbuilt. Body
> preserved verbatim above for the historical record.

## Context

The dev-team workflow is `/specs → /plan → /build → /pr`, with a human
approval gate between phases. Artifacts flow forward; nothing integrates until
the end of a build; the unit of integration is the completed plan.

External review (issue #98 and its children, #14;
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
   monitors is enumerated in *Gate-vs-monitor split* below.
3. **The human approves *exposures* (flag flips), not *plans*.** The reviewable
   artifact becomes *running software per increment* — the third artifact the
   reviews note is more trustworthy than either 200 lines of plan or 2,000 lines
   of generated code.

This is a topology, not a switch: it coexists with the current gates and is
proven per-increment, not adopted wholesale.

### Gate-vs-monitor split

The decision item above promises an enumeration of which review agents stay
**pre-merge gates** and which become **post-merge monitors**. The criterion is
*cost of a wrong merge when the increment lands dark*:

- **Stay a pre-merge gate** when a defect is unsafe or expensive to ship even
  behind an off-by-default flag — it touches an irreversible/security surface,
  corrupts shared state regardless of the flag, lands the *wrong behavior*, or
  removes the safety net the monitors themselves depend on.
- **Become a post-merge monitor** (run after the dark merge; revert the
  increment on failure) when the concern is advisory or quality-oriented and a
  per-increment revert is a cheap, complete remedy — especially where a runtime
  signal post-merge is *more* meaningful than a static pre-merge guess.

| Review agent | Disposition | Why |
|---|---|---|
| `security-review` | **Pre-merge gate** | Injection/auth/data-exposure and secrets in history are irreversible even behind a flag. |
| `concurrency-review` | **Pre-merge gate** | Races and shared-state corruption can bite via shared code paths the flag doesn't guard. |
| `spec-compliance-review` | **Pre-merge gate** | A wrong-behavior increment wastes the exposure; already gates before quality agents run. |
| `test-review` | **Pre-merge gate** | The test safety net is what makes a monitor's auto-revert signal trustworthy; it cannot itself be a monitor. |
| `arch-review` | **Post-merge monitor** | ADR/layer-boundary drift is structural and reversible per-increment; *borderline* — compounding drift may argue for keeping it a gate in repos without strong tests. |
| `performance-review` | **Post-merge monitor** | Resource/algorithmic regressions are best measured against the runtime observability the topology already assumes, not guessed statically. |
| `complexity-review` | **Post-merge monitor** | Advisory; cheap to revert. |
| `structure-review` | **Post-merge monitor** | Advisory; cheap to revert. |
| `naming-review` | **Post-merge monitor** | Advisory; cheap to revert. |
| `domain-review` | **Post-merge monitor** | Advisory; cheap to revert. |
| `refactor-opportunity-review` | **Post-merge monitor** | Advisory by definition (runs in the REFACTOR phase). |
| `js-fp-review` | **Post-merge monitor** | Style/quality; cheap to revert. |
| `svelte-review` | **Post-merge monitor** | Framework-quality; cheap to revert. |
| `a11y-review` | **Post-merge monitor** | Quality; reversible and observable post-exposure. |
| `test-smell-review` | **Post-merge monitor** | Test-quality advisory; cheap to revert. |
| `doc-review` | **Post-merge monitor** | Documentation drift; never blocks behavior. |
| `token-efficiency-review` | **Post-merge monitor** | Efficiency advisory; cheap to revert. |

Two agents fall **outside this topology** because they gate *workflow phases*
or *repo metadata*, not per-increment trunk merges: `test-modernization-review`
(gate-keeps `/test-modernize` phase boundaries) and `claude-setup-review`
(audits CLAUDE.md and agent-frontmatter schema). They keep their current roles.

This split is itself a hypothesis to validate per-increment, not a frozen
assignment; `arch-review` in particular should be re-evaluated against the #111
trend data (step 4 of the migration path).

## Required infrastructure (assumed or provided)

- **Feature-flag mechanism** the plugin can assume in a target repo (or scaffold
  via `/setup`), so each increment can integrate dark. Resolved via the **Flag
  Capability Contract**, below — the plugin standardizes on an abstraction, not
  a vendor.
- **Rollback / auto-revert authority** for review monitors (revert a commit/PR
  by SHA), with an audit trail.
- **Runtime observability** to make post-merge monitoring meaningful — overlaps
  with the cost meter and `/session-review` digest.
- A decision on **what stays gate-based** (irreversible actions, schema/security
  surfaces) vs. what moves to monitor-and-revert — enumerated in
  *Gate-vs-monitor split*, above.

### Flag Capability Contract (resolves the flagging-method blocker)

The original blocker — *"how do we pick a flag method when users have many
technologies and runtime environments?"* — assumed the plugin must choose a
vendor. It should not. It standardizes on a thin **contract** and detects/falls
back to a provider, mirroring the pattern the plugin already uses for test
stacks (`knowledge/test-stack-profiles/`) and security primitives
(`knowledge/security-primitives-contract.md`). The topology needs only four
operations:

- `is_enabled(flag, context) -> bool`
- `create(flag, default=off)`
- `flip(flag, exposure)` — the human-approved *exposure* gesture
- `remove(flag)` — flag-debt cleanup

`/setup` selects a provider in four tiers (priority order):

| Tier | Provider | When |
|---|---|---|
| 1 | Existing repo flag system (LaunchDarkly, Unleash, OpenFeature SDK, Flagsmith) | Detected from deps/imports — **adopt, don't replace** |
| 2 | **OpenFeature** as the default neutral adapter | No flags, but wants vendor-neutral infra |
| 3 | Scaffolded minimal flag (committed `flags.json`) | Wants dark integration, zero new infra |
| 4 | No-flag / degraded mode | Nothing, won't scaffold — topology falls back to today's phase gates (a first-class supported state) |

Targeting **OpenFeature** (CNCF, vendor-neutral) as the default dissolves the
"multiple technologies" problem instead of betting on a vendor: the plugin
programs against one API; the repo binds any backend.

**Lightest 100%-OSS default (collapses tiers 2–3):** the OpenFeature SDK plus
**flagd's in-process provider reading a committed `flags.json`** — no daemon, no
SaaS, no network; all Apache-2.0/CNCF. Its decisive fit with this ADR is that
**flip = commit**: toggling a flag edits `flags.json` and commits it, which is
git-auditable, PR-reviewable, and *is itself* the "human approves the exposure"
artifact — no separate audit-trail system required. A `/build` step integrates
dark by guarding its code behind `is_enabled(flag)` with `defaultVariant: off`;
the exposure is a later, human-approved commit flipping it `on`. Adopting
flagd-as-daemon or a vendor later changes only the provider binding.

> Version caveat for the spike: OpenFeature/flagd contrib package names and the
> file-resolver config have drifted across SDK releases — pin the SDK + flagd
> contrib versions per language and verify the file-source config against the
> pinned release before scaffolding.

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
   that have flag infra, programming against the Flag Capability Contract.
3. **Validate the contract across three repos** — one with an existing vendor
   (e.g. LaunchDarkly/Unleash), one greenfield OpenFeature + flagd-file, one
   no-flag degraded — pinning the OpenFeature/flagd versions. This spike is what
   turns the blocker from resolved-in-principle into evidenced and is the gate
   for moving this ADR to **Accepted**.
4. Pilot one review agent as a post-merge monitor (advisory first, then with
   revert authority) and compare friction/escape rates against the pre-merge
   path; re-evaluate the borderline `arch-review` disposition here.
5. Use `/session-review` evidence (which gates correlate with rework/bypass —
   the narrowed #111, which has already returned a first signal) to confirm the
   gate-vs-monitor split.
6. Revisit this ADR's status once the spike (step 3) lands and the per-increment
   pilot (step 4) shows the topology reduces real friction.

## Dependencies and references

- Evidence prerequisite: narrowed **#111** (which phases/gates correlate with
  rework/bypass, answered from the `/session-review` trend stream).
- Telemetry/observability: the cost meter (#102) and the session-digest.
- Source: issue #98 and its children (#14);
  `reports/agentic-dev-team-unknown-unknowns.md` (§1, Problem Dissolution).
- Tracking issue: #112.
