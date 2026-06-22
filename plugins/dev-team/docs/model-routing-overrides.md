# Model Routing — Override Authoring Guide

Operator-facing guide to overriding effort-band → model resolution for your
environment. For the contract and architecture, see
[model-routing.md](model-routing.md).

You override routing by hand-writing one file: `.claude/model-ladder.json`.
There is nothing else to configure — no probe, no per-user cache, no env var.

## When you need a ladder

You do **not** need a ladder on a standard Anthropic API key — the shipped
default map already resolves every band to the right model. Write a ladder only
when your environment offers a **different or restricted set of models** than
the defaults: a corporate proxy with an allowlist, AWS Bedrock, Google Vertex,
or any deployment whose model IDs differ from `claude-haiku-4-5-20251001` /
`claude-sonnet-4-6` / `claude-opus-4-8`.

## The ladder schema

`.claude/model-ladder.json` (gitignored, per-environment) is a **JSON array of
model ID strings, ordered cheapest → most capable**:

```json
["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]
```

Rules:

- It must be a non-empty array of strings. Anything else (an object, an empty
  array, non-string elements, invalid JSON) is **ignored** — routing degrades
  to the shipped default map and never aborts dispatch.
- Order is capability-ascending. The resolver maps a band to an index with
  `index = round_half_up(weight·(N−1))`, weights `low=0`, `medium=0.5`,
  `high=1`, `N` = ladder length.

## Resolution precedence

For every sub-agent dispatch, the band resolves in this order:

1. **Valid ladder** → the model at the computed index.
2. **Shipped default map** (`knowledge/model-routing.json`) → used when there
   is no ladder, or the ladder is malformed/empty.
3. **Session-model fallback** → only for an explicit snapshot a present ladder
   does not contain (the requested model is unavailable here). The session
   model (captured at session start) is the fallback — never a ceiling.

Verify the effective outcome any time with `/model-routing-check`: it prints
the band → model map, the ladder (or a ready-to-edit starter when none
exists), the captured session model, and recent routing bumps.

## Worked ladders

### Restricted endpoint (no haiku)

Your proxy serves only sonnet and opus:

```json
["claude-sonnet-4-6", "claude-opus-4-8"]
```

Resolves: `low` → sonnet, `medium` → opus, `high` → opus (N=2; medium rounds
up to the top). Nothing routes to the unavailable haiku.

### Single-model environment

Only one model is reachable:

```json
["claude-sonnet-4-6"]
```

Resolves: every band → sonnet. `/model-routing-check` and the SessionStart
banner collapse to a single line noting all bands map to that one model.

### Bedrock / Vertex

Bedrock and Vertex expose Claude under provider-specific model IDs. List the
ones your deployment serves, cheapest → most capable — the ladder is
endpoint-agnostic, so the same mechanism works without any Bedrock/Vertex
special-casing:

```json
["anthropic.claude-haiku-4-5", "anthropic.claude-sonnet-4-6", "anthropic.claude-opus-4-8"]
```

Resolves like the N=3 default: `low`/`medium`/`high` → the 1st/2nd/3rd entry.

### Four-model ladder

If your environment adds a tier above opus:

```json
["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8", "claude-opusmax-9"]
```

Resolves (N=4, `round_half_up`): `low` → haiku, `medium` → opus (index 2),
`high` → opusmax. If a 4+ model ladder becomes common, the project adds a 4th
effort band rather than re-tuning the formula.

## Migration guarantee

With **no ladder file**, every effort band resolves to the **identical
snapshot** it did before the effort-band migration
(`low→claude-haiku-4-5-20251001`, `medium→claude-sonnet-4-6`,
`high→claude-opus-4-8`) — the shipped default map equals the old tier mapping.
Doing nothing changes nothing. (Pinned by AC0 in the routing tests.)

## Reverting

Delete `.claude/model-ladder.json`. The shipped default map resumes
immediately — absence of the ladder is the disabled state. There is no
separate "disable" flag.
