# Design: Complexity-based model routing with session-model fallback

**Status:** Draft — for review before planning
**Supersedes:** the probe-driven `tier_aliases` mechanism in `docs/model-routing.md`

## Problem

Two coupled limitations in today's model routing:

1. **Agents hardcode vendor tiers.** Every agent declares `model: haiku|sonnet|opus`
   in frontmatter. That bakes Anthropic's current 3-tier lineup into ~32 files.
   A different environment (a proxy with only sonnet+opus, a single-model
   endpoint, a future 4-model lineup) needs those files re-edited.

2. **No runtime fallback to a known-good model.** When an agent's requested
   snapshot isn't available in the environment, the resolver still emits it (or,
   for a hand-written `tier_aliases` chain, denies the dispatch). There is no
   path that says "this model isn't here — use the model the user is already
   running this session."

The probe (`hooks/lib/model-probe.sh`) was the prior answer to (2): query
`/v1/models` and pre-write a `tier_aliases` override. It only works on
Anthropic-shape endpoints, adds a network dependency, and still resolves to a
fixed tier rather than the session's actual model.

### The abstraction is already half-leaked (and inconsistent)

A vendor-neutral vocabulary is *partially* in place and currently contradicts
itself — a clean rename fixes this rather than introducing it:

- `/agent-add` and `/agent-create` accept `--tier small|mid|frontier` and map
  them to `haiku|sonnet|opus`.
- `/agent-audit` declares the valid `model:` values are `small`, `mid`,
  `frontier`.
- But the resolver's `_is_valid_tier` only accepts `haiku|sonnet|opus`, and
  `agents/test-modernization-review.md` ships `model: mid` in its frontmatter.
  The resolver rejects `mid`; the PreToolUse hook fail-opens, so that agent
  dispatches the literal string `"mid"` as a model ID. **This is a latent bug
  today** — a direct symptom of the half-leaked abstraction. The clean rename
  to `complexity:` bands resolves it as a side effect.

## Decision summary

| Decision | Choice |
| --- | --- |
| Agent frontmatter | Relative **complexity band** (`low \| medium \| high`), not a vendor tier |
| Availability source | A **hand-written ladder** (`.claude/model-ladder.json`). No probe. If absent, routing is a no-op. |
| Session model role | **Fallback** when a target isn't resolvable, and the **reference** for upgrade flags. **Not a ceiling.** |
| Agent above session model | **Allowed.** A `high` agent runs on opus even when the session started on sonnet. |
| User communication | **SessionStart banner only.** Enumerates the full band→model table and flags upgrades. Per-dispatch bumps are silent but logged. |
| Vocabulary | **`low \| medium \| high`** — task-complexity framing ("this task is simple"), not model-capability framing ("this model is small"). The agent describes *its own need*, decoupled from any model. |
| Migration | **Clean rename of everything we ship** to `complexity:` bands, with the resolver accepting legacy tier names for **one deprecation release** (warned by `/agent-audit`, not silent), then removed at the next major. Breaking for downstream agent authors → `feat!` / major bump + migration note. |

## The model ladder

A hand-written, capability-ordered list of the model IDs that actually exist in
this environment, cheapest → most capable:

```json
// .claude/model-ladder.json   (per-environment, gitignored)
{ "ladder": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"] }
```

- This file is the **single source of truth for what is available.** It replaces
  `.claude/model-overrides.json` and the probe.
- **If the file is absent, the resolver is a no-op** — every agent dispatches on
  the harness default (the session model). No network call, no remapping. This
  is the "no list → no probe" case.
- Works for any provider (Bedrock, Vertex, proxies): the user lists whatever
  model IDs their environment serves, in capability order.

## Resolution

### Complexity band → ladder position

For a ladder of length `N` (0-indexed), each band has a normalized weight:

| Band | Weight |
| --- | --- |
| low | 0.0 |
| medium | 0.5 |
| high | 1.0 |

```
index = round(weight * (N - 1))
target = ladder[index]
```

Worked examples:

| Ladder | low | medium | high |
| --- | --- | --- | --- |
| `[haiku, sonnet, opus]` (N=3) | haiku | sonnet | opus |
| `[sonnet, opus]` (N=2) | sonnet | opus | opus |
| `[sonnet]` (N=1) | sonnet | sonnet | sonnet |
| `[haiku, sonnet, opus, ultra]` (N=4) | haiku | opus | ultra |

> The N=3 case reproduces today's haiku/sonnet/opus exactly. The N=4 row shows
> the rounding edge (medium lands on index 2); if a 4+ model ladder becomes
> common we add a 4th band rather than re-tune the formula.

### Why the session model is not a ceiling

"Available" (the ladder) and "session model" (the user's main-loop pick) are
independent. A `high` agent maps to the top of the ladder regardless of what the
session started on. If the ladder is `[haiku, sonnet, opus]` and the session is
sonnet, a `high` agent runs **opus** — the model is in the ladder, so it is
available; the session pick is just a default for the main loop, not a cap.

### The session-model fallback

Because complexity bands only ever resolve to ladder members, a band can never
request a nonexistent model — the original "use the session model if the
requested model doesn't exist" requirement is satisfied **structurally**.

The explicit fallback to the session model fires only for:

- a legacy/explicit `model: <concrete-snapshot>` in frontmatter whose snapshot
  is not in the ladder, or
- no ladder file at all (in which case "fall back to the session model" is a
  no-op — the harness already uses it).

## Communication: the SessionStart banner

The full band→model resolution is deterministic and known at session start
(ladder static, formula static, session model captured from the SessionStart
`model` field). So the banner shows the complete table and flags upgrades:

```
Model routing — session model: sonnet
  low     → haiku
  medium  → sonnet
  high    → opus     ⬆ above your session model
```

- "⬆ above your session model" appears on any band whose target is more capable
  than the session model — this is the "tell the user it's doing it" signal for
  the high-while-session-is-sonnet case.
- Per-dispatch resolution stays silent but appends a JSONL line to the bump log
  (`.claude/metrics/model-routing.log`) for `/model-routing-check`.

**Why the banner must live in SessionStart:** the PreToolUse payload does not
expose the session model and there is no env var for it (verified against the
Claude Code hooks reference). Only the SessionStart hook's stdin `model` field
carries it. The SessionStart hook persists it (e.g. `.claude/session-model`) so
the PreToolUse resolver can read it at dispatch time.

> The SessionStart `model` field can be absent after `/clear`, resume, or
> compact. When absent, reuse the last persisted value; if none, skip the banner
> and treat routing as no-op for the session.

## Components touched

| Component | Change |
| --- | --- |
| `agents/*.md` (33) | `model: <tier>` → `complexity: <band>` (all at once; fixes `model: mid` in `test-modernization-review.md`) |
| `templates/agents/*` (10) | same swap in the scaffolds |
| `agents/orchestrator.md` | Resolution Procedure rewritten around bands + ladder |
| `hooks/lib/model-resolve.sh` | band → ladder-position resolution; drop `tier_aliases` cascade; **accept legacy `haiku/sonnet/opus` for one deprecation release**, then remove |
| `hooks/agent-model-resolve.sh` | unchanged contract (rewrite `updatedInput` / pass-through); reads session-model fallback |
| `hooks/<sessionstart>.sh` | new/extended: capture session model, render banner via `systemMessage`, persist model |
| `hooks/lib/model-probe.sh` | **deleted** |
| `skills/agent-create`, `skills/agent-add`, `skills/agent-audit` | replace `small/mid/frontier` and `haiku/sonnet/opus` with `low/medium/high`; enforce the band list |
| `skills/init-dev-team/SKILL.md` + Linux script | remove the probe step (Step 4.5) |
| `skills/model-routing-check/SKILL.md` | show ladder, band→model table, session model, recent bumps |
| `knowledge/model-routing.json` | re-keyed by band (`low/medium/high → snapshot`) for the no-ladder default; legacy tier keys retained for the deprecation window |
| `docs/model-routing.md` | rewritten for the ladder/band model |
| `tests/hooks/*`, `tests/knowledge/*` | bats updated; probe tests removed; add legacy-acceptance + deprecation-warning tests |

## Open decisions for review

1. ~~Migration~~ **Settled:** clean rename to `low/medium/high` everywhere we
   ship; resolver accepts legacy `haiku/sonnet/opus` for one deprecation release
   (warned by `/agent-audit`), removed at the next major. Ships as `feat!`.
2. **Upgrade signal:** banner-only (current plan), or also a per-dispatch
   `systemMessage` the first time each upgraded band fires?
3. **Band count:** ship 3 bands (`low/medium/high`) now; revisit a 4th if a
   4-model ladder becomes common.

## Deprecation window

| Release | Resolver accepts | Agents/templates ship | `/agent-audit` on legacy |
| --- | --- | --- | --- |
| N (this change, `feat!`) | `low/medium/high` **+** `haiku/sonnet/opus` | `low/medium/high` | warns: "legacy tier name; migrate to complexity band" |
| N+1 (next major) | `low/medium/high` only | `low/medium/high` | errors |

Legacy acceptance maps `haiku→low`, `sonnet→medium`, `opus→high` at resolve
time. It is a read-time courtesy for downstream agent authors only — nothing we
author uses it.

## Non-goals

- Re-introducing any network probe.
- Per-dispatch availability checks (the ladder is the cached truth).
- Capping agents at the session model.
