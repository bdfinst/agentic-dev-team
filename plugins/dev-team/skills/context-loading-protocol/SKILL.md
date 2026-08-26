---
name: context-loading-protocol
description: Decide which agents and skills to load for a given task. Use at the start of every task to select the minimum viable context load, calculate the token budget, and stay below the 40% utilization ceiling.
role: orchestrator
user-invocable: true
---

# Context Loading Protocol

Token-budget reference (CLAUDE.md baseline, full-load ceiling, per-agent and per-skill costs) is the **Baseline Budget** section of `CLAUDE.md`. This skill is the runtime procedure; don't duplicate the table here — it goes stale.

## Constraints

- Never load all agents upfront; load only the primary agent for each phase.
- Keep total context below **40%** of the model's window at all times.
- Load agents on demand when their phase begins, not speculatively.
- Use tool-based file reads (Read); do not paste file contents into the prompt.

## Enforcement

This protocol is backed by a `PreToolUse` hook — `hooks/context_ceiling_guard.py`
(registered on `Agent` and `Skill`). Before a capability-loading call it measures
`utilization = (input + cache_read + cache_creation) / model_context_window` from
the transcript's latest assistant-message usage against the model's context
window, which the hook auto-detects from the session's most recent
`message.model` by family/version substring: Haiku family -> 200K; current
1M-window models -> 1M (Fable, Mythos, Opus 4.6/4.7/4.8, Sonnet 5, Sonnet 4.6);
unrecognized model, or a same-family model outside those pinned versions ->
200K conservative fallback (window is a fixed per-model property, so an
unrecognized model is never assumed large). A ceiling computed against that
fallback **warns but never blocks** — the guard blocks on windows it knows,
and an unrecognized model id means it does not know this one. Set
`DEV_TEAM_CONTEXT_WINDOW` to override detection explicitly, which also
restores blocking.

Occupancy is measured from main-thread turns only: transcript rows marked
`isSidechain` are subagent turns whose usage describes the subagent's
context, not this one's, and are skipped by both the occupancy scan and
window detection.

The effective ceiling is `min(ceiling_pct% of window, 350K tokens)` — an
absolute-token cap (`DEV_TEAM_CONTEXT_ABS_CEILING`, default 350000, ADR 0038)
that keeps large windows from pushing the trigger point past where context
quality and per-turn cost degrade; it's a no-op on the 200K base window
(40% = 80K, already under the cap) and binding on every 1M one, so in
practice the shipped ceiling is a flat 350K, or 35% of a 1M window. The
warning
names which bound is binding — percentage or absolute, never both — and the
window's provenance (override, detected, or default).

As occupancy climbs past the ceiling, the hook escalates through three
Handoff action bands keyed to multiples of the effective
ceiling (350K / 437.5K / 525K on a 1M window) — 1x nudge, 1.25x run
`/handoff` now, 1.5x full
summary + fresh conversation (see [Handoff → When to
Summarize](../handoff/SKILL.md#when-to-summarize)) — before
**blocking the load** at/above the ceiling (the default since
#2000; `DEV_TEAM_CONTEXT_STRICT=off` downgrades it to a warning).
Recovery skills
(`/handoff`, `/context-loading-protocol`, `/continue`,
`/review-summary`, `/session-review`) are never gated — blocking the path
back under budget would deadlock the session.

Knobs: `DEV_TEAM_CONTEXT_CEILING_PCT` (default 40), `DEV_TEAM_CONTEXT_ABS_CEILING`
(default 350000), `DEV_TEAM_CONTEXT_WINDOW` (overrides auto-detection),
`DEV_TEAM_CONTEXT_CEILING=off` (disables entirely).
The hook is a backstop measured from real usage; the budget estimate below is still
the planning tool you apply *before* loading.

### Why 40%

The 40% ceiling is a conservative planning target, not a claimed accuracy cliff.
Chroma's [Context Rot study](https://www.trychroma.com/research/context-rot) found
degradation across 18 models (including Claude 4) is gradual, not a sharp drop at
any single percentage. Needle-in-a-haystack benchmarks like RULER and NoLiMa show a
model's *effective* context is often only about half its advertised window, with
sharp accuracy drops on non-lexical retrieval well before the window limit. Anthropic's
[effective context engineering guidance](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
recommends proactive compaction well ahead of the limit. Given that evidence,
budgeting to 40% of the window (capped at 350K absolute) leaves headroom before
quality degrades, rather than chasing a precise threshold that doesn't exist.

The cap was 150K until [ADR 0038](../../../../docs/adr/0038-raise-the-absolute-context-ceiling-to-350k.md),
which is also where the "40%" in this section's title stops being the number
that binds: on every 1M-window model the cap governs, making the shipped
ceiling a flat 350K (35%). The percentage is still the rule for 200K windows
and still the right planning target for Step 4's estimate.

Full guide — warning-line field reference, concrete band fire-points per
window size, knob table, troubleshooting: [Context
Management](../../docs/context-management.md).

## Loading Decision Procedure

### Step 0: Confirm there is a task

Before loading anything or reading files, confirm an actionable instruction exists. If the user has not yet said what they want, wait — do not speculatively read files, verify code, or load agents. Premature investigation before a task is given wastes context and is a common interrupt trigger. Once a task exists, proceed to Step 1.

### Step 1: Classify the task

| Profile | Description | Example |
|---|---|---|
| **Simple/Single** | One agent, no skills | "Fix this typo", "Write a unit test" |
| **Standard/Single** | One agent + 1–2 skills | "Implement this feature using hexagonal architecture" |
| **Multi-Agent** | 2–3 agents coordinating | "Design and implement a new API endpoint" |
| **Complex/Multi** | 3+ agents + skills | "Build a new bounded context with full test coverage" |

### Step 2: Select agents

Load the **minimum set**:

1. Identify the **primary agent** (owns the deliverable).
2. Identify **supporting agents** (input or review).
3. Do NOT load agents for downstream validation yet — load them when their phase begins.

Order: primary first, then supporting agents one at a time as their phase begins.

### Step 3: Select skills

For each loaded agent, check its `## Skills` section:

- Only load skills **relevant to the current task** — not all skills the agent references.
- Skills shared by multiple loaded agents only need to be loaded once.

### Step 4: Calculate token budget

```
Total = CLAUDE.md baseline
      + conversation history (estimate)
      + agent files (sum selected)
      + skill files (sum selected)
      + expected output (estimate)
```

**Target: total < 40% of the model's context window, capped at 350K absolute tokens.** For Claude with a 200K window, that's < 80K tokens; on a 1M-window model the cap (350K) binds before the percentage would. See [Why 40%](#why-40) for the rationale. The config files are a small fraction; the real budget concern is conversation history + output accumulation over multi-turn tasks.

### Step 5: Load via tool-based file reads

```
Read agents/software-engineer.md
Read skills/hexagonal-architecture/SKILL.md
```

Do NOT copy file contents into the system prompt or conversation.

## Loading Profiles

Pre-computed loading sets for common task types.

### Code Implementation

- **Load**: Software Engineer + relevant skill(s)
- **Defer**: QA (load after implementation), Architect (load only if design questions arise)

### Architecture Design

- **Load**: Architect + relevant architecture skill(s)
- **Defer**: Software Engineer (load at implementation), QA (load at validation)

### Bug Fix

- **Load**: Software Engineer only
- **Defer**: QA (load if regression test needed)

### New Feature (full lifecycle)

Three phases, each in a fresh context window with a human review gate between. Each phase's output is a structured progress file in `.claude/memory/` that onboards the next phase.

| Phase | Load | Purpose | Output |
|---|---|---|---|
| 1. Research | Orchestrator + sub-agents (exploration) | Understand system, find files, trace data flows | Research progress file |
| 2. Plan | Architect + PM (if needed) + relevant skill(s) | Specify every change: files, snippets, tests | Implementation plan progress file |
| 3. Implement | Software Engineer + QA + skill(s) | Execute the plan; code, tests | Working code + test results |

Key rules:

- Each phase starts with a fresh context window, loading only the previous phase's progress file.
- Human reviews and approves the progress file before the next phase begins.
- Sub-agents primarily provide context isolation — they search, read, and return concise findings.
- If implementation is large, compact mid-phase: update the plan progress file with completed steps and continue in a fresh context.

## Unloading

Since tokens can't be literally removed from context:

1. **Phase transitions** — summarize completed phase output into `.claude/memory/` and start a new conversation for the next phase.
2. **Within a conversation** — stop referencing the agent/skill; the orchestrator mentally notes it's no longer active. Use the Handoff skill (continue mode) to compress stale content.
3. **Multi-turn accumulation** — when conversation history crosses **30%** utilization, trigger summarization before loading additional agents.

## Anti-patterns

- Loading all agents upfront — wastes tokens before any work begins. Load only the primary agent.
- Loading all of an agent's skills — most are irrelevant to the specific request.
- Never unloading — context grows monotonically until hallucination risk. Summarize and phase-transition.
- Loading agents "just in case" — adds cost without value. Load on demand when the phase begins.

## Output

Loading plan as one table: selected agents + skills, token costs, estimated total, and utilization percentage against the 40% ceiling. No narration.
