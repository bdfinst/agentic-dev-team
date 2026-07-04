---
name: context-summarization
description: Compress conversation history when context utilization approaches 40%. Use when too many files have been read, the conversation is long, or output quality is degrading — write a structured summary to memory/ and start a fresh context window.
role: orchestrator
user-invocable: true
---

# Context Summarization

Compress conversation history to keep context utilization below 40%. Uses forget/input/output gates to decide what to keep, compress, and discard.

## Constraints

- Summaries replace conversation history; never reload prior turns
- Never include credentials, PII, or sensitive data in `memory/`
- Summaries must be sufficient for the next phase to start without replaying history

## When to Summarize

The `hooks/context_ceiling_guard.py` hook's graduated bands are keyed to
multiples of the *effective ceiling* — `min(ceiling_pct% of window, 150K
tokens)` — not raw window percentage, so the same table applies whether the
threshold is percentage-bound (small windows) or absolute-bound (large
windows):

| Multiple of the effective ceiling | Action |
| --- | --- |
| < 1x | No action — below the ceiling |
| 1x – 1.25x | Nudge: consider running `/context-summarization` |
| 1.25x – 1.5x | Run `/context-summarization` now |
| 1.5x+ | Full summary to `memory/`, start a new conversation |

**Measuring utilization**: `utilization = (input + cache_read + cache_creation) / model_context_window` — the same formula `hooks/context_ceiling_guard.py` reads from the transcript's most recent assistant-message usage. The window is auto-detected from the session; the guard's effective ceiling is `min(ceiling_pct% of window, 150K tokens)`, so the trigger point stays conservative even on very large windows. Fallback signals: turn count > 40, many file reads accumulated, degraded output quality.

**Why 40%, not a higher number**: see [Context Loading Protocol → Why 40%](../context-loading-protocol/SKILL.md#why-40).

## The Three Gates

Apply in order to all context older than the last 3-5 turns:

### 1. Forget Gate -- Discard

- Exploratory dead ends and rejected approaches
- Verbose tool outputs where only the conclusion matters
- Superseded decisions
- Debugging steps for resolved issues

### 2. Input Gate -- Preserve

- Current task definition and acceptance criteria
- Active architectural decisions and rationale
- Unresolved questions or blockers
- File paths and line numbers being worked on
- User preferences and feedback from this session

### 3. Output Gate -- Keep Verbatim

- Last 3-5 conversation turns
- Code actively being modified
- Error messages being debugged
- Current agent persona and skill guidelines (if loaded)

## Writing Summaries

Write the summary to `memory/{date}-{task-slug}.md` using the Task Summary template in `references/summary-templates.md`.

## Phase Progress Files

Each phase produces a progress file that onboards the next phase's agent without replaying history. Write the progress file using the appropriate phase template (Research, Plan, or Implementation) from `references/summary-templates.md`.

## Using Summaries in New Conversations

1. Read the most recent summary from `memory/`
2. Load only **Key Context for Continuation** into active context
3. Load referenced files on demand, not upfront
4. Do NOT reload full conversation history -- the summary replaces it

## Cleanup

1. Archive summaries older than 30 days to `memory/archive/`
2. Delete archived summaries older than 90 days
3. Consolidate multiple summaries for the same task into one
