# Spike: `effort:` Agent-Tool Parameter Support

**Date**: 2026-04-20
**Context**: Opus 4.7 migration planning (`plans/opus-4-7-alignment.md`, Step 0)
**Question**: Is `effort` a native parameter on the Claude Code `Agent` tool, or must it be conveyed as prose inside the dispatched prompt?

## Evidence

The authoritative source is the `Agent` tool's JSONSchema as exposed to the running assistant. Its accepted properties are:

| Property | Required | Type / Enum |
|---|---|---|
| `description` | yes | string |
| `prompt` | yes | string |
| `subagent_type` | no | string |
| `model` | no | enum: `sonnet` \| `opus` \| `haiku` |
| `isolation` | no | enum: `worktree` |
| `run_in_background` | no | boolean |

The schema sets `additionalProperties: false`. Passing an `effort` field returns `InputValidationError` before the sub-agent is dispatched.

## How effort is actually controlled in Claude Code

Per Anthropic's official best-practices post (`https://claude.com/blog/best-practices-for-using-claude-opus-4-7-with-claude-code`), effort in Opus 4.7 is a **session-level configuration**, not a per-dispatch parameter:

- Default effort is `xhigh` for most coding/agentic work
- `low`, `medium`, `high`, `xhigh`, `max` are the documented tiers
- Tier selection happens at the Claude Code runtime level (model/fast toggles, auto-mode for Max users)
- Fixed `budget_tokens` are unsupported; Opus 4.7 uses adaptive thinking per step

Thinking *intensity* at the prompt level is modulated via directives like:

- More thinking: `"Think carefully and step-by-step before responding; this problem is harder than it looks"`
- Less thinking: `"Prioritize responding quickly rather than thinking deeply"`

## Implication for the plan

Step 2 of `plans/opus-4-7-alignment.md` must take the **advisory-only branch**:

1. Add an `Effort` column to the Model Routing Table as **documentation** — it records the *intended* effort tier per agent/task class.
2. For agents that should carry an explicit thinking-intensity directive (Step 7 of the plan), encode the directive as **prose in the agent's frontmatter or instructions**, not as a structured dispatch field.
3. **Drop** any plan assertions that expect a structured `effort:` field in Agent-tool dispatch calls. The `check-routing-table.sh` script validates the table's shape, not runtime behavior.
4. The routing table must carry a one-line note stating that effort is advisory and conveyed via prompt-level directives, so downstream readers don't infer a contract that doesn't hold.

## Re-baseline trigger

If Anthropic adds a native `effort:` parameter to the Claude Code `Agent` tool in a future release, re-run this spike and flip Step 2 to the "native parameter" branch (update dispatch wrappers in `prompts/implementer.md` and `prompts/quality-reviewer.md` to pass the field).
