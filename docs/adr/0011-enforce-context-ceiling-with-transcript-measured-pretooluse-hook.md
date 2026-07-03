# 11. Enforce the context ceiling with a transcript-measured PreToolUse hook

Date: 2026-06-25

## Status

Accepted

Refined by [16. Rely on harness-native compaction; the plugin performs structured summarization only](0016-rely-on-harness-native-compaction-the-plugin-performs-structured-summarization-only.md)

## Context

CLAUDE.md states a **40% Context Window Rule** and the `context-loading-protocol` skill instructs the orchestrator to keep total context under that ceiling and to load agents/skills on demand rather than speculatively. Until now nothing enforced it: the rule lived only as guidance the orchestrator was asked to self-apply, and the protocol's own budget step is an *estimate* (baseline + history estimate + file sizes). If the orchestrator ignored the rule, context grew unchecked until the harness's own summarization kicked in — independent of the protocol.

Three design questions had non-obvious answers:

1. **How to measure context occupancy.** Options:
   - **Model self-estimate.** Ask the orchestrator to track its own fill. Rejected: a model has no reliable readout of its own context size; this is exactly the proxy the rule already fails on.
   - **Transcript usage.** The session transcript's assistant-message `usage` records `input_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens` — the prompt side of the most recent turn is the ground-truth occupancy the harness saw. A hook can read it from `transcript_path`. Chosen: it is real, not estimated, which is what makes the ceiling *enforceable* rather than advisory. (Same transcript-usage source `cost-meter.sh` already relies on.)

2. **Warn or block.** Options:
   - **Block by default.** Strongest, but a mis-detected window (see below) would hard-block constantly, and blocking is hostile when the model cannot remove tokens itself.
   - **Warn by default, opt-in block.** Chosen: mirrors `destructive-guard.sh` / `/careful` (warn on exit 0, block on exit 2). `DEV_TEAM_CONTEXT_STRICT=on` escalates to a hard block. A warn-default also means a wrong window only over-nudges, never bricks a session.

3. **What to gate.** Options:
   - **All context-growing tools (incl. Read/Grep/Glob).** Broad, but noisy on frequent Reads and dangerous to block — you need Reads to summarize and recover.
   - **Capability loads (`Agent` + `Skill`).** Chosen: these are exactly the "don't load speculatively" operations the protocol governs, far less frequent than Read, and safe to block because recovery never needs a fresh agent. Recovery skills (`/context-summarization`, `/context-loading-protocol`, `/continue`, `/review-summary`, `/session-review`) are whitelisted so the path back under budget can't deadlock.

A known limitation surfaced during design: the transcript reports the base model id (`claude-opus-4-8`) with **no `[1m]` suffix** and carries no context-window field, so a 1M-context model cannot be auto-distinguished from the 200K base. The window must therefore be resolvable out-of-band. A model-id→window map was considered and rejected: every current Claude model shares the same 200000-token base window (so the map would carry no information), and pinning `claude-*` snapshot ids in plugin source is forbidden by repo policy (see ADR 8). The window is resolved from an env var with a 200000 default instead.

## Decision

Add `hooks/context-ceiling-guard.sh`, a `PreToolUse` hook registered on `Agent` and `Skill`. It computes occupancy from the latest transcript usage line, resolves the context window from `DEV_TEAM_CONTEXT_WINDOW` (else a `200000` default), and compares `occupancy/window` to a ceiling (`DEV_TEAM_CONTEXT_CEILING_PCT`, default 40). At or above the ceiling it warns to stderr (default, deduped by 5-point bucket per session to avoid spam) or blocks (`exit 2`) under `DEV_TEAM_CONTEXT_STRICT=on`. It whitelists recovery skills, and is fail-open throughout (`DEV_TEAM_CONTEXT_CEILING=off`, missing/unparseable transcript, missing `jq`, or any error → exit 0). On a 1M-context model the operator sets `DEV_TEAM_CONTEXT_WINDOW=1000000`.

## Consequences

- The 40% rule is now a measured backstop, not just prose — capability loads over budget surface a concrete nudge (or block) tied to real occupancy.
- The window default (200000) over-nudges on a 1M-context session until `DEV_TEAM_CONTEXT_WINDOW` is set; warn-by-default keeps that harmless, and the caveat is documented in the skill, CLAUDE.md, and `docs/agent-architecture.md`.
- The hook reads `tail -n 400` of the transcript per gated call; bounded, but adds a small jq cost to `Agent`/`Skill` dispatches (not to Read/Grep/Glob).
- Behavior is configurable and reversible via env vars; no schema or contract changes. Tests live in `tests/hooks/context_ceiling_guard.bats`.
