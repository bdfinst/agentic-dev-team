# 16. Rely on harness-native compaction; the plugin performs structured summarization only

Date: 2026-07-03

## Status

Accepted

Refines [11. Enforce the context ceiling with a transcript-measured PreToolUse hook](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md)

## Context

The plugin's context management ([ADR 11](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md), the `context-loading-protocol` and `context-summarization` skills) detects when a session approaches its context ceiling and nudges the model to summarize. While designing the guard improvements in [issue #775](https://github.com/bdfinst/agentic-dev-team/issues/775), the question arose whether the plugin should go further and implement **auto-compaction** — automatically shrinking the conversation when the ceiling is crossed, instead of nudging.

Three findings settled it:

1. **A plugin cannot compact.** Compaction means rewriting what is inside the model's context window, and only the Claude Code harness can do that. Hooks observe usage, warn, and block tool calls; they cannot remove or replace tokens already in context. Built-in commands such as `/compact` are user-invoked and not model- or skill-invocable. Any plugin-built "auto-compaction" reduces to prompting the model to summarize — which is exactly what the `/context-summarization` skill already is.

2. **The harness already auto-compacts.** Claude Code ships three native layers: *microcompaction* (bulky old tool results offloaded to disk behind a path reference), *auto-compact* of the whole conversation at roughly 83.5% of the window (user-tunable via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`), and manual `/compact`. Rebuilding any of this in the plugin would duplicate harness behavior we do not control and cannot keep in sync.

3. **Generic compaction is worse than deliberate summarization for this plugin's workflow.** Harness auto-compact produces a generic summary at an uncontrolled moment — mid-implementation it can drop plan-step state, file:line anchors, and acceptance criteria. The plugin's `memory/` progress files use structured templates (forget/input/output gates), are human-reviewable at phase gates, and persist across sessions. Compaction also discards the warm prompt cache, so the next request re-reads the new context at full input price; firing it eagerly trades quality risk and cost for little benefit. Published evidence (Chroma's Context Rot study, RULER, NoLiMa, Anthropic's context-engineering guidance) shows degradation is gradual and tracks absolute token count — which argues for early, deliberate, structured summarization rather than late, generic compaction.

## Decision

Rely on harness-native compaction as the backstop and never implement plugin-side auto-compaction. The plugin's role is **semi-automatic structured summarization**: the context ceiling guard measures real occupancy from the transcript and, as occupancy rises, escalates from a warning nudge to an imperative instruction to run `/context-summarization` now — with `DEV_TEAM_CONTEXT_STRICT=on` blocking further capability loads until the session is back under budget. Summaries are written as structured progress files to `memory/`, per the `context-summarization` skill. Native auto-compact (~83.5%) remains the safety net for anything the guard misses; the plugin documents `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` as a user-side knob but does not lower it by default.

## Consequences

- No compaction machinery to build or maintain; the plugin's context work stays inside its existing hook + skill surface, and harness compaction improvements are inherited for free.
- Session-critical state survives context refreshes as reviewable `memory/` artifacts instead of an opaque harness summary, preserving the human phase gates.
- The escalation path depends on the model following the guard's instruction; strict mode is the enforcement backstop when it does not. A session that ignores both still falls through to harness auto-compact — later and lossier, but never stuck.
- Two mechanisms coexist by design: users who tune `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` below the guard's ceiling get harness compaction before the plugin's structured summarization can run; docs must present the guard as the earlier, preferred layer.
- The full rationale and the guard changes it shapes are tracked in [issue #775](https://github.com/bdfinst/agentic-dev-team/issues/775).
