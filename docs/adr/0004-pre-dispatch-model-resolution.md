# 4. Pre-dispatch model tier resolution enforced by a PreToolUse hook

Date: 2026-06-01

## Status

Accepted

Amended by [8. Use effort bands instead of model names in agent frontmatter](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)

> **Path and command note (2026-07-20):** the bash-removal effort (ADR 0014, completed by ADR 0015) rewrote `hooks/agent-model-resolve.sh` and `hooks/lib/model-resolve.sh` as Python (`.py`) files. Separately, the `/init-dev-team` command referenced below was split into `/setup` and `/project-init`, and `/model-routing-check` is now a skill (`plugins/dev-team/skills/model-routing-check/`), not a `commands/*.md` command. This ADR is preserved verbatim as a historical record.

## Context

The plugin's agents declare a tier alias (`haiku`, `sonnet`, `opus`) in their
`model:` frontmatter. The Claude Code harness resolves each alias to a fixed
snapshot ID such as `claude-haiku-4-5-20251001`. This works on a personal
Anthropic API key but fails for two real user populations:

1. **Corporate proxies with restricted model allowlists** — `haiku` may not
   be reachable, and the dispatch fails opaquely.
2. **Anthropic snapshot deprecation** — pinned snapshot IDs scattered across
   agent frontmatter, CLAUDE.md, and the orchestrator's routing table all
   need updates whenever Anthropic retires a snapshot.

Two related design questions had non-obvious answers and shape this ADR.

### Q1. Pre-dispatch resolution vs. runtime `model_not_available` retry

The original issue (#37) suggested a "dispatch-side fallback" that catches
`model_not_available` at runtime and retries up the haiku → sonnet → opus
chain. Plan-review (pass 1) rejected this:

- The harness owns the dispatch surface. The plugin runs as hooks and
  markdown commands — neither can intercept the harness's `Agent` tool
  error path. There is no `OnToolError` hook contract; `PostToolUse` fires
  on completion, not on failure-with-retry.
- A "transparent" runtime fallback would have to live inside the harness
  itself, which the plugin cannot modify.

Two alternatives remained:

- **Pre-dispatch resolution.** Resolve the tier alias to a concrete snapshot
  *before* the `Agent` tool is invoked. Walks the cascade based on a
  per-user override cache populated either by a probe or by hand.
- **Document-only.** Ship clearer error messages and recovery docs, but no
  automatic resolution.

### Q2. Where does pre-dispatch resolution live?

Two locations were considered:

- **Orchestrator markdown instruction.** Add a "Resolution Procedure"
  section to `agents/orchestrator.md` that instructs the LLM to shell out
  to a resolver helper before each `Agent` call.
- **PreToolUse hook on the `Agent` matcher.** Register a hook in
  `settings.json` that intercepts every `Agent` tool call, reads
  `tool_input.model`, shells out to the resolver, and rewrites the model
  field (or refuses dispatch) via `hookSpecificOutput`.

Plan-review (pass 2) flagged the markdown-instruction approach as a
re-statement of the R1 problem the change was meant to solve: a model
under context pressure may skip the procedure, and the override silently
becomes a no-op.

## Decision

1. **Pre-dispatch resolution, not runtime retry.** Resolution happens
   before any `Agent` tool call reaches the harness. The plugin does not
   attempt to catch `model_not_available` at runtime — that error surface
   belongs to the harness, which the plugin cannot reach. When the
   resolver cannot satisfy a request (exhausted cascade, cycle, missing
   routing.json, malformed overrides), the hook refuses dispatch with
   `permissionDecision: "deny"` and an actionable
   `permissionDecisionReason`.

2. **Enforce via a PreToolUse hook, not orchestrator instruction.**
   `hooks/agent-model-resolve.sh` is registered in `settings.json` under
   `matcher: "Agent"`. It runs on every `Agent` tool call regardless of
   what the LLM is doing or whether the LLM remembers the procedure. The
   orchestrator markdown becomes documentation of behavior, not the
   enforcement surface.

3. **Single source of truth in `knowledge/model-routing.json`.** All tier
   → snapshot mappings ship in one shipped JSON file. Per-user overrides
   live in `.claude/model-overrides.json` (gitignored, populated by an
   opt-in probe in `/init-dev-team` or hand-written for restricted
   endpoints).

The resolver helper `hooks/lib/model-resolve.sh` is the single bash + jq
implementation called by both the PreToolUse hook and the
`/model-routing-check` diagnostic command.

## Consequences

**Positive.**

- Restricted-endpoint users get transparent tier resolution with no manual
  intervention — the same plugin code works on a personal Anthropic key, a
  corporate proxy, or Bedrock/Vertex.
- Future snapshot deprecations are a one-file change
  (`knowledge/model-routing.json`).
- Enforcement is mechanical; the LLM cannot bypass it under context
  pressure.
- The resolver is bats-testable in isolation via env-var path overrides
  (`MODEL_ROUTING_JSON`, `MODEL_OVERRIDES_JSON`, `MODEL_BUMP_LOG`).

**Negative.**

- Adds bash + jq cold-start overhead to every sub-agent dispatch
  (~10-15ms on Apple Silicon). The AC15 perf gate caps this at 50ms p99.
- The PreToolUse hook contract for `updatedInput` is not fully spelled out
  in the public Claude Code docs (the relevant section was truncated when
  we fetched it during Step 0 verification). We rely on the established
  pattern used by two other production plugins
  (`agentic-security-assessment`, `agentic-security-review`).
- The harness's runtime `model_not_available` path is still uncaught — if
  routing.json points at a snapshot the harness can't reach AND no
  override redirects the tier, the dispatch still fails. We accept this
  because: (a) plugin defaults track current Anthropic snapshots, and
  (b) corporate-proxy users have the override-cache escape hatch.

**Out of scope (recorded as future work).**

- Runtime retry inside the harness — would require harness changes
  outside the plugin's control.
- Probe support for non-Anthropic-shape endpoints (Bedrock, Vertex).
  Users on those endpoints write `.claude/model-overrides.json` by hand;
  documented in `docs/model-routing.md`.

See: `agents/orchestrator.md` → Resolution Procedure for the algorithm,
`docs/model-routing.md` for the contract and troubleshooting,
`commands/model-routing-check.md` for the diagnostic.
