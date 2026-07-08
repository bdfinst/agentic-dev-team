# 19. Orchestrate the phase pipeline, choreograph the safety layer

Date: 2026-07-08

## Status

Accepted

## Context

Microservice architecture distinguishes two coordination styles.
**Orchestration**: a central coordinator holds the full-flow view, decides
what runs next, and can compensate when a step fails. **Choreography**:
independent components react to events with no central coordinator; each
knows only its own trigger and its own action.

The dev-team plugin already runs both patterns side by side without having
named the split:

- **Orchestrated**: `agents/orchestrator.md` (`Role: orchestrator`) and the
  higher-level skills that declare the same role
  (`code-review`, `competitive-analysis`, and other multi-agent skills)
  dispatch specialized agents by task classification, sequence
  Research → Plan → Implement phases, and decide what happens after each
  agent returns — retry, escalate, or move to the next phase. There is one
  place that holds the flow.
- **Choreographed**: the `PreToolUse`/`PostToolUse` hooks
  (`plugins/dev-team/hooks/*.py` — `context_ceiling_guard.py`,
  `destructive_guard.py`, `pre_tool_guard.py`,
  `mutation_testing_smoke_gate.py`, `tdd_guard.py`,
  `refactor_test_freeze_guard.py`, and the rest of the ~25-file hook roster)
  each fire independently off a tool-call event. None of them knows the
  others exist, none of them knows what phase the session is in, and none of
  them can compensate for another hook's decision. They just react.

Neither pattern is "the architecture" — the plugin is both, layered. The
question this ADR answers is not "which pattern should we use" but "what
decides which pattern a given piece of coordination gets." Applying the
orchestration/choreography distinction concretely surfaced the operative
rule already implicit in the existing design:

- Coordination that needs a **full-flow view** to make its decision — what
  phase are we in, what did the last agent return, does this warrant a
  retry or a human escalation, which specialized agents does this task
  classification need — has nowhere to live except a central coordinator.
  Distributing that logic into independent reactive components would mean
  no component has enough context to make the call, and failures could only
  be diagnosed by reconstructing state no single place held.
- Coordination that is a **narrow, local, always-applicable check** —
  "is this a destructive bash command," "did context cross the ceiling,"
  "does this diff touch a frozen refactor file" — needs no knowledge of the
  broader flow to decide, and benefits from running the same way regardless
  of which orchestrator or skill triggered the tool call. Routing every one
  of these checks through the central orchestrator would mean the
  orchestrator carries every guard's logic and every future guard requires
  an orchestrator change, when the check has no actual dependency on
  orchestration state.

That is: orchestration cost buys coordinated, context-aware decisions;
choreography cost buys independent, uniformly-applied guards that scale by
adding a file, not by editing a central dispatcher. The plugin already
sorted its coordination logic along this line — this ADR names the line so
future additions land on the correct side of it on purpose, not by
accident.

## Decision

Coordination logic in this plugin is orchestrated if, and only if, making
the right call requires cross-phase or cross-agent context that no single
reactive component holds. Everything else — a check that is local to one
tool call and whose answer doesn't depend on what phase, task, or agent
triggered it — is choreographed as a hook, never folded into the
orchestrator or a `role: orchestrator` skill.

Concretely, when adding new coordination:

- **Add to the orchestrator or an orchestrator-role skill** when the logic
  needs to know what happened in a prior phase or agent call, needs to
  decide what runs next among several options, or needs the ability to
  compensate (retry, escalate, roll back) based on another component's
  outcome. Example: deciding which review agents to dispatch based on
  changed file types, or deciding whether a failed phase should retry or
  escalate to the human.
- **Add as a `PreToolUse`/`PostToolUse` hook** when the logic is a
  self-contained check against a single tool call's inputs or the
  session's own measurable state (context size, file path, command
  string), and the same answer applies no matter which orchestrator, skill,
  or phase triggered the call. Example: `destructive_guard.py` blocking an
  `rm -rf` regardless of which agent issued it.
- A hook must never assume it runs after or before another specific hook,
  and must never reach into orchestrator state to make its decision — if it
  needs that, it is miscategorized and belongs in the orchestrated layer
  instead.
- An orchestrator-role skill must not reimplement a check a hook already
  covers uniformly (e.g. re-checking for destructive commands inside
  `/build`) — that duplicates enforcement in a place that can drift out of
  sync with the hook.

## Consequences

- Future contributors get a concrete test for "does this new guard go in a
  hook or in the orchestrator" instead of guessing by precedent: ask
  whether the decision needs cross-phase/cross-agent context.
- The hook layer stays composable — each hook can be added, removed, or
  reordered independently, and none of them can be broken by another hook's
  internal changes, because none of them depend on each other.
- The orchestrated layer stays the single place to look for "what happens
  next" logic — anyone tracing a phase transition or a retry/escalation
  decision knows to look at `agents/orchestrator.md` or the relevant
  `role: orchestrator` skill, not to go hunting through the hook roster.
- Risk: as the hook roster grows (already ~25 files), a hook author could
  be tempted to smuggle in a small piece of cross-cutting state (e.g. a
  hook that reads what phase a skill is in from a shared file) to avoid an
  orchestrator change. That reintroduces implicit coordination between
  supposedly-independent hooks and defeats the point of this split — reviews
  of new hooks should watch for it.
- This ADR does not require refactoring any existing hook or orchestrator
  logic — the current split already matches this rule; it formalizes the
  boundary so it holds going forward rather than eroding as new
  coordination needs appear.
