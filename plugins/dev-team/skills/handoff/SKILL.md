---
name: handoff
description: Compress or split off context for another session to pick up. Use to compress conversation history when context utilization approaches 40% (continue mode), or to split off a distinguishable out-of-scope side-task to an independent session (fork mode) — write a structured artifact for the other session and free the current one.
role: orchestrator
user-invocable: true
---

# Handoff

One skill, two modes, for getting structured context to another session instead of replaying history:

- **Continue mode** — compress *this* task's history so the *same* task can keep going past the context ceiling, in a fresh window.
- **Fork mode** — split off a distinguishable, out-of-scope side-task into an *independent* session (a parallel sibling, or a child that later hands learnings back), without diluting or compacting the current session's context.

Both modes apply the same Three Gates (below) to decide what to keep, compress, and discard — that logic is written once and shared by both modes.

## Mode Selection

Keyed off whether a **stated purpose** exists for an independent/fresh session:

| Signal | Mode |
| --- | --- |
| No stated purpose — continuing the current task past the ceiling | **Continue** (default, unchanged behavior) |
| A stated purpose for a distinguishable, out-of-scope side-task | **Fork** |
| Ambiguous — unclear whether this is the same task or a split-off | Ask: "Continue this task in a fresh window, or split off unrelated work to an independent session?" |

## Constraints

- Summaries/handoff artifacts replace conversation history; never reload prior turns
- Never include credentials, PII, or other sensitive data in written output — see Redaction below
- Output must be sufficient for the receiving session to start without replaying history

## The Three Gates

Apply in order to all context older than the last 3-5 turns, in both modes:

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

## Redaction

Before writing any output in either mode, redact secrets, API keys, tokens, and PII from the content. Fork-mode output leaves the repo-adjacent trust boundary (an OS temp dir another session reads), so redaction is mandatory there. Continue-mode output stays under `.claude/memory/` inside the repo, but apply the same redaction pass for consistency — a secret that shouldn't be in conversation history shouldn't be in a committed-adjacent file either.

## Continue Mode

Compress conversation history to keep context utilization below 40% while continuing the *same* task in a fresh window.

### When to Summarize

`/handoff` is manual: nothing forces or blocks on it. Reach for it when a
deliberate, structured summary beats the harness's generic compaction:

- before a long phase ends, so the next phase starts from a reviewable
  `.claude/memory/` file rather than replayed history;
- when you notice the session is heavy (many file reads accumulated, turn
  count above about 40, degraded output quality) and want to choose what
  survives;
- before a planned break in the work.

The harness compacts on its own at the percentage `/dev-team:setup` configures
(default 40%); a `/handoff` summary written first is the structured
alternative to that generic summary.

**Measuring utilization**: `utilization = (input + cache_read + cache_creation) / model_context_window`, from the most recent assistant-message usage in the session transcript.

**Why 40%, not a higher number**: see [Context Loading Protocol → Why 40%](../context-loading-protocol/SKILL.md#why-40).

### Writing Summaries

- **Destination**: `.claude/memory/{date}-{task-slug}.md`
- **Scope**: full relevant history for the task
- **Requires**: nothing extra — the task is already known

Write the summary using the Task Summary template in `references/summary-templates.md`.

### Phase Progress Files

Each phase produces a progress file that onboards the next phase's agent without replaying history. Write the progress file using the appropriate phase template (Research, Plan, or Implementation) from `references/summary-templates.md`.

### Using Summaries in New Conversations

1. Read the most recent summary from `.claude/memory/`
2. Load only **Key Context for Continuation** into active context
3. Load referenced files on demand, not upfront
4. Do NOT reload full conversation history -- the summary replaces it

### Cleanup (Time-Based)

1. Archive summaries older than 30 days to `.claude/memory/archive/`
2. Delete archived summaries older than 90 days
3. Consolidate multiple summaries for the same task into one

## Fork Mode

Split off a distinguishable, out-of-scope side-task into an independent session — a sibling running in parallel, or a child (e.g. a prototype session) that later hands learnings back — without diluting or compacting the current session.

### Requires a Stated Purpose

Fork mode always needs a one-line purpose describing the side-task. If the user hasn't stated one, ask for it before writing anything — an unpurposed fork artifact can't be scoped correctly by the Forget/Input/Output gates above.

### Writing the Fork Artifact

- **Destination**: the OS temp dir (e.g. `$TMPDIR` or the platform default), never `.claude/memory/` — the artifact is disposable and not part of the repo's durable history
- **Scope**: just the slice of context relevant to the stated purpose, not the full session history
- **Naming**: `{tmpdir}/handoff-{purpose-slug}-{date}.md`

Use the **Fork Handoff** template in `references/summary-templates.md`, which adds these sections beyond the Task Summary:

- **Suggested Skills** — skills the receiving session likely needs loaded for the stated purpose, so it doesn't have to rediscover them.
- **Pointers, not duplication** — link to or cite content that already exists in other artifacts (files, prior summaries, design docs) instead of copying it into the fork doc. The fork doc should compose with existing artifacts, not fork a second copy of them.
- **Hand-back** (when the fork will report results back to this session) — what the parent session needs from the child when it's done: a short result summary and pointers to what changed, in a shape the parent can merge without replaying the child's history.

### Cleanup (Event-Based, Never Time-Based)

Fork-mode artifacts are deleted **on consumption**, not on a schedule:

- The receiving session merges its result back into the parent — delete the fork artifact once the merge is confirmed.
- The parent session reads a hand-back doc from a completed child — delete the hand-back doc once it has been read.

Never apply the continue-mode 30/90-day time-based cleanup to fork-mode output — an unconsumed fork artifact should persist until it's actually picked up, and a consumed one should not linger waiting for a sweep.
