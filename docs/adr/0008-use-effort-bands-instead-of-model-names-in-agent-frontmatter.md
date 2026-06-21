# 8. Use effort bands instead of model names in agent frontmatter

Date: 2026-06-21

## Status

Accepted

Amends [4. Pre-dispatch model tier resolution enforced by a PreToolUse hook](0004-pre-dispatch-model-resolution.md)

## Context

[ADR 0004](0004-pre-dispatch-model-resolution.md) established that each agent
declares a tier alias (`haiku`, `sonnet`, `opus`) in its `model:` frontmatter,
and a PreToolUse hook resolves that alias to a concrete snapshot before
dispatch. The enforcement topology works. The **vocabulary** does not.

1. **The alias leaks the vendor's model lineup.** Naming the field `model:` and
   its values `haiku/sonnet/opus` bakes Anthropic's current three-tier naming
   into ~33 agent files plus templates. A different environment — a proxy with
   only two models, a single-model endpoint, a future four-model lineup — cannot
   be expressed without re-editing every agent.

2. **The abstraction is already half-leaked and inconsistent.** `/agent-add`
   and `/agent-create` already accept `--tier small|mid|frontier`, and
   `/agent-audit` declares the valid values are `small|mid|frontier` — yet the
   resolver's allowlist only accepts `haiku|sonnet|opus`, and
   `agents/test-modernization-review.md` ships `model: mid`, which the resolver
   rejects (the hook then fail-opens and dispatches the literal string `"mid"`
   as a model ID). The contradiction is a direct symptom of binding frontmatter
   to vendor model names.

3. **The fallback target was a fixed tier, not the user's actual session.** When
   a requested model is unavailable, the right fallback is the model the user is
   already running this session — not a hardcoded `haiku → sonnet → opus`
   cascade, and not a network probe of `/v1/models` (which only works on
   Anthropic-shape endpoints).

What an agent actually wants to express is **how much reasoning effort its task
needs** — a relative, vendor-neutral property of the task — and let the
environment decide which model serves that effort.

The full mechanism (the environment model ladder, the effort→ladder mapping, the
session-model fallback, and the SessionStart banner) is specified in
[`docs/specs/model-complexity-routing.md`](../specs/model-complexity-routing.md).
This ADR records the decision; the spec records the design.

## Decision

Replace the vendor-named `model:` tier alias with a vendor-neutral **effort
band** in agent frontmatter.

- Each agent declares `effort: low | medium | high` — a statement about the
  task's reasoning demand, not about any model.
- A per-environment, capability-ordered **model ladder**
  (`.claude/model-ladder.json`, hand-written) maps effort bands to the concrete
  models that exist in that environment. Absent a ladder, routing is a no-op and
  agents run on the harness's session model.
- The model the user selected at session start is the fallback when an effort
  band cannot be mapped, and the reference point for flagging upgrades. It is
  **not** a ceiling: a `high` agent runs on the top of the ladder even when the
  session started lower, and the SessionStart banner announces that.
- The opt-in `/v1/models` probe is removed; availability comes from the ladder.
- The resolver accepts the legacy `haiku/sonnet/opus` names for **one
  deprecation release** (mapped `haiku→low`, `sonnet→medium`, `opus→high`,
  warned by `/agent-audit`), then drops them at the next major. Everything the
  plugin ships migrates to `effort:` immediately.

Every agent — current and future — must declare a valid `effort:` band. This is
enforced by a structural test (`tests/agents/agent_effort_frontmatter_tests.bats`)
that fails CI if any agent file is missing the field or carries a value outside
the allowed set, so the contract cannot silently rot the way `model: mid` did.

## Consequences

**Easier:**

- Agents are portable across providers and model lineups; a new environment is
  described once in `.claude/model-ladder.json`, never by re-editing agents.
- Snapshot churn is contained to the ladder and `knowledge/model-routing.json`,
  not scattered across frontmatter.
- The `model: mid` latent bug is fixed as a side effect, and the
  `small/mid/frontier` ↔ `haiku/sonnet/opus` split is unified into one
  vocabulary.
- Fallback is to a model the user is provably already running, so dispatch
  cannot fail for lack of a reachable model.

**Harder / risks:**

- **Breaking change for downstream agent authors.** Anyone who wrote an agent
  with `model: sonnet` must migrate to `effort: medium`. Mitigated by the
  one-release legacy-acceptance window and a `feat!` major version bump with a
  migration note.
- **Atomicity.** Frontmatter, resolver, and tests must change together or a
  drift window opens where resolution fails. Mitigated by landing the rename,
  resolver change, and the effort-frontmatter test in one change set.
- **Effort is coarse (three bands).** A future four-model ladder may want a
  fourth band; the mapping rounds an effort band to a ladder position, so the
  band set and ladder length can drift apart. Mitigated by keeping the band set
  small and explicit, and revisiting only when a 4+ model ladder is common.
- **Upgrade cost visibility.** Because the session model is not a ceiling, a
  `high` agent can run above the session model. Mitigated by the SessionStart
  banner flagging every upgrade; deferred decision on whether to also warn
  per-dispatch.
