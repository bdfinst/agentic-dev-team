# 21. Claude-only model routing — no multimodal or cross-provider tier

Date: 2026-07-18

## Status

Superceded by [26. Adopt native model:/effort: agent frontmatter, retire the band resolver](0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)

## Context

A competing skill (`multi-tier-models` in `upasana1105/claude-code-skills`)
routes execution-tier work **by modality across providers**: plain text goes
to Haiku, multimodal analysis to Gemini Flash, video to Gemini Omni, image
generation to Gemini Image. Against that lineup, dev-team's routing looks
narrow: `plugins/dev-team/knowledge/model-routing.json` maps effort bands to
Claude models only, and there is no multimodal-worker story anywhere in the
plugin. Until now that boundary existed **by omission** — nothing recorded
whether it was a gap to close or a scope line to hold.

Two facts make it a scope line, not a gap:

1. **The dispatch surface is Claude-shaped.** dev-team is a Claude Code
   plugin. Sub-agents dispatched through the Agent tool run on Claude models;
   the model-resolution hook (`plugins/dev-team/hooks/agent_model_resolve.py`,
   a PreToolUse hook per [ADR 0004](0004-pre-dispatch-model-resolution.md))
   can only rewrite `tool_input.model` to a model the harness can serve.
   There is **no hook-level cross-provider dispatch**: the hook cannot hand a
   sub-agent to Gemini, and no supported mechanism exists for it to acquire
   that ability. A "Gemini tier" in `model-routing.json` would be a value the
   resolver could emit but the harness could never run.
2. **The plugin has no multimodal workload.** Every agent and skill in the
   roster operates on text: code, diffs, docs, configs, logs, eval fixtures.
   No team workflow analyzes images or video, and none generates them. A
   modality-routing tier would route traffic that does not exist.

[ADR 0008](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)
already made frontmatter vendor-neutral (`effort:` bands, not model names),
so agents themselves carry no Claude coupling — the coupling lives entirely
in the resolution layer (`knowledge/model-routing.json` and the
per-environment ladder), which is exactly where a future lineup change would
be absorbed. That vocabulary decision is about *which model serves an effort
level*; this decision is about *which providers and modalities are in scope
at all*.

## Decision

Model routing is **intentionally Claude-only**. Effort bands resolve to
Claude models per `plugins/dev-team/knowledge/model-routing.json` (or a
per-environment ladder of Claude model IDs), and the plugin ships **no
multimodal tier** — no modality field in routing, no image/video worker
agents, no cross-provider dispatch.

This is a deliberate scope boundary, recorded so it is a decision rather
than an omission:

- Routing complexity stays proportional to routing reality: one axis
  (effort), one provider (what the harness can dispatch).
- Competitive comparisons against modality-routing skills should cite this
  ADR instead of re-litigating the boundary per analysis.

**Revisit triggers** — reopen this decision when either becomes true:

1. Claude Code gains first-class multi-provider sub-agents (the harness can
   natively dispatch a sub-agent to a non-Claude model, reachable from a
   PreToolUse hook's `updatedInput`), or
2. the plugin acquires a real multimodal workload — image or video analysis
   or generation as part of a team workflow (e.g. design-review of
   screenshots, video-based QA evidence), not a hypothetical.

Until one of those holds, proposals to add provider or modality tiers to
`model-routing.json` are out of scope by default.

## Consequences

**Easier:**

- The routing surface stays small and fully testable: band → model is a pure
  lookup the resolver can verify offline, with no provider-availability
  matrix, no per-provider auth, and no cross-provider cost normalization.
- ADR 0008's ladder mechanism remains the single extension point. If the
  harness ever serves non-Claude models natively, the ladder — a
  capability-ordered array of model IDs — is already shaped to hold them;
  nothing in agent frontmatter would change.
- Gap analyses have a citable answer for "why no Gemini/multimodal tier"
  instead of an apparent blind spot.

**Harder / risks:**

- Any genuinely multimodal need that appears before the revisit triggers
  fire must be handled outside the routing layer (a dedicated tool or MCP
  server, not a sub-agent tier) or wait. That friction is accepted: it is
  the cost of not shipping routing entries the harness cannot honor.
- The boundary depends on a harness fact (Claude-only sub-agent dispatch)
  that this repo does not control. If that fact changes quietly, this ADR
  could overstay; the revisit triggers name the observable events to watch
  rather than a date.
