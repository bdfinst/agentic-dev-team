# 28. Require skills: preload and memory: project on matching agents

Date: 2026-07-22

## Status

Accepted

## Context

`skills:` (preloaded skill list) and `memory:` (persistent memory scope) are
both optional fields in the official Claude Code sub-agent contract. Issue
#1335 asked for two this-repo conventions layered on top of them, the same
category as `effort: high` (ADR 0026) and `color:` (ADR 0027) — each
asserted by a test gate rather than left to per-agent judgment:

1. Any agent whose body documents a `## Skills` section should preload those
   skills via `skills:` frontmatter, rather than relying on the agent to
   discover and invoke them ad hoc mid-task.
2. Any agent that mutates files (`Edit`/`Write` in `tools:`) should retain
   cross-session memory (`memory: project`), so file-mutation decisions and
   their rationale persist past a single conversation.

## Decision

Require, and mechanically check, both fields:

- **`skills:`** — an agent with a `## Skills` section in its body must
  declare a non-empty `skills:` list, and every listed name must trace back
  to that section's own text (not merely appear somewhere else in the body,
  e.g. a Knowledge Files section). This is a one-directional gate: an agent
  with no `## Skills` section has nothing to preload and by default omits
  `skills:`, but the gate itself only checks agents that *have* a `##
  Skills` section — it does not scan for or reject a `skills:` list on an
  agent without one.
- **`memory:`** — an agent with `Edit` or `Write` in `tools:` must declare
  exactly `memory: project`. No other value and no omission is accepted for
  that agent — this is an exact-equality gate with no escape valve, matching
  ADR 0027's precedent for `color:`. This direction only: an agent with
  neither `Edit` nor `Write` is outside the gate's scope entirely (see the
  Scoping note in Consequences) — by default it omits `memory:`, but the
  gate does not check or restrict what such an agent declares here, unlike
  a generic `--memory user|project|local` flag used elsewhere.

Applied to the current fleet: 12/58 agents carry a `## Skills` section and
`skills:`; 7/58 carry `Edit`/`Write` and `memory: project`. A test gate
(`tests/agents/test_agent_fleet_conventions.py`) asserts both, via pure
`classify_skills_declaration()` / `classify_memory_declaration()` functions
(no filesystem access) so every violation branch — missing declaration,
unknown/untraceable name, wrong memory value, not-applicable — is
unit-tested independently of scanning real agent files.
`marketplace-dev`'s `agent-create`/`agent-add` suggest-and-confirm both
fields the same way they already do `model:`/`effort:`/`color:`: skills
from the generated body's `## Skills` section, memory as a fixed
`project` suggestion with no override for a file-mutating agent (since the
gate has no escape valve to override into).

## Consequences

- **Easier**: an agent with skills to invoke no longer has to discover and
  load them mid-task from scratch; the preload is checked in and
  auditable. A file-mutating agent's cross-session memory can never
  silently regress to unset — it's asserted by a test, not remembered by
  convention.
- **Harder / risk**: two more fields whose fleet-wide state can drift out of
  sync with an agent body edit (adding/removing a `## Skills` section, or
  adding/removing `Edit`/`Write`) if the test gate isn't run before commit.
  This is the same risk ADR 0027 already accepted for `color:`, mitigated
  the same way — a fast, pure-function-backed pytest gate rather than a
  periodic manual audit.
- **Scoping note**: the `memory:` gate only requires `project` for
  file-mutating agents; it says nothing about non-mutating agents choosing
  `user` or `local` memory for other reasons — that remains a free choice
  outside this rule's scope, unlike `color:`, which the mechanical rule
  fully determines for every agent.
