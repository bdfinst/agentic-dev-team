# 27. Require and mechanically derive color on every agent

Date: 2026-07-22

## Status

Accepted

## Context

`color:` (display color in the task list/transcript, one of `red|blue|green|
yellow|purple|orange|pink|cyan` per `agent-contract.json`) is optional in the
official Claude Code sub-agent contract. Before this decision, 0 of the
fleet's 58 agents declared it. Issue #1334 asked for it to become a
this-repo convention, layered on top of the optional field — the same
category as the `effort: high` convention (ADR 0026) — but needed a concrete,
non-arbitrary assignment scheme, not just "pick something."

## Decision

Require `color:` on every agent, derived by a deterministic, mechanically
computed rule rather than a hand-maintained per-agent choice — so the value
can be asserted by a test gate instead of drifting silently. Priority order
(capability signals checked before the naming convention, so what an agent
*can do* outranks what it's *called*):

1. `tools:` contains `Agent` (bare or `Agent(...)`) → **purple** (orchestrator
   — can dispatch other agents).
2. Else `tools:` contains `Edit` or `Write` → **yellow** (changes files).
3. Else the agent's name ends `-review` or starts `plan-review-` → **green**
   (reviewer).
4. Else → **cyan** (all others).

Applied to the current fleet: 1 agent purple (`orchestrator`), 7 yellow, 32
green, 18 cyan — 58/58 resolve unambiguously, no ties. A new test gate
(`tests/agents/test_agent_color_frontmatter.py`) asserts every agent's
declared `color:` equals the rule-computed value, failing loudly (naming the
agent, its declared color, and the rule-computed color) on a mismatch or
omission. `agent-create`/`agent-add` suggest-and-confirm the computed color
the same way they already do `model:`/`effort:`, validating a human override
against only the four colors this rule can produce (not the full 8-color
contract enum) — since the test gate is exact-equality with no escape valve,
offering one of the other four colors there would pass the prompt and then
fail CI.

## Consequences

- **Easier**: a developer scanning the task list can tell orchestration vs.
  file-mutation vs. review vs. everything-else at a glance, without opening
  each agent's frontmatter; the assignment can never silently drift because
  it's asserted by a test, not remembered by convention.
- **Harder / risk**: the rule is a new, non-ADR-sourced-until-now convention
  that four colors (`red`, `blue`, `orange`, `pink`) of the official eight
  are currently unused by this scheme — if a future need calls for a fifth
  bucket, this ADR and the rule's priority list need to change together, and
  the 58 already-assigned agents may need re-deriving. This is deliberately
  cheap to do now (one rule, one test) and gets more expensive the longer the
  fleet grows on top of it unrevised.
- **Priority-order note**: checking capability before naming means a future
  agent that is both named like a reviewer (`*-review`) and mutates files
  (`Edit`/`Write`) resolves to yellow, not green — capability wins. This
  changes no current agent's bucket (verified: no agent today is both).
