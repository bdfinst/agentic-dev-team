---
name: agent-skill-authoring
description: Conventions, anti-patterns, and meta-patterns for writing skills (and the shared agent/skill philosophy). Use when creating or editing a SKILL.md file, or when reviewing the agent-vs-skill separation. For the procedural workflow that generates a new agent file, use the agent-create skill (invoked by /agent-add).
role: worker
user-invocable: true
---

# Agent & Skill Authoring

## Overview

This skill defines the philosophy of the agent-vs-skill split and the conventions for writing skills. Agents own orchestration logic (when and why); skills own execution knowledge (how). This separation keeps agents readable as workflow definitions while keeping capabilities DRY across the team.

**Scope boundary**:
- This skill — skill creation, shared philosophy, anti-patterns, documentation sync policy
- `agent-create` skill — the procedural workflow for generating a new agent file (invoked by `/agent-add`)

If you are creating an agent file, use `/agent-add` (which invokes the `agent-create` skill). This skill no longer duplicates that procedure.

## Constraints
- Skills must be agent-agnostic; no persona or behavioral logic in skill files
- Execution details belong in skills; orchestration logic belongs in agents
- Every new agent or skill must be registered (see [`references/templates.md`](references/templates.md#registration-checklist))
- Do not embed a skill's knowledge inline in an agent — reference the skill file

## Core Pattern

```
Agent (when + why)          Skill (how)
┌─────────────────┐        ┌─────────────────┐
│ ## Skills        │        │ # Skill Name    │
│ - Skill A ──────│───────>│                 │
│   "Invoke when  │        │ ## Concepts     │
│    designing    │        │ ## Patterns     │
│    bounded      │        │ ## Guidelines   │
│    contexts"    │        │ ## Structure    │
│                 │        │                 │
│ ## Behavioral   │        │ (reusable by    │
│   Guidelines    │        │  any agent)     │
│ (orchestration) │        │                 │
└─────────────────┘        └─────────────────┘
```

- **Agents** define the *role*: persona, behavior, collaboration style, and *when/why* to use each skill
- **Skills** define the *capability*: concepts, patterns, guidelines, and project structures
- An agent references a skill and annotates it with invocation context
- Multiple agents can share the same skill, each with different invocation context

## Creating an Agent

Run `/agent-add` — it invokes the `agent-create` skill, which is the canonical procedure: name validation, type detection, scope-overlap check, body generation within token-efficiency budgets, `/plugin-audit` validation gate, and registry/CLAUDE.md updates.

Do not hand-author agent files when `/agent-add` is available — divergent templates produced manually have historically drifted from the schema enforced by `/plugin-audit`.

## Creating a Skill

Resolve the target plugin directory (`$PLUGIN`) using the same convention as
`agent-create`: `--plugin <dir>` argument; else single `plugins/*/`; else cwd
ancestor with `.claude-plugin/plugin.json`; else ask.

Place skill files at `$PLUGIN/skills/{skill-name}/SKILL.md`. Use the skill template and authoring guidelines from [`references/templates.md`](references/templates.md#skill-template). Then follow the [registration checklist](references/templates.md#registration-checklist).

## Meta-Patterns for Skill Writing

Before writing a new skill, read 2-3 existing skills in `$PLUGIN/skills/` to absorb the project's voice and structure. Skills that follow existing patterns integrate better.

**Explain the why, not just the what.** LLMs follow rules more reliably when they understand the reasoning. "Do X because Y happens without it" beats "ALWAYS do X." Compare:
- Weak: "ALWAYS run tests before claiming done"
- Strong: "Run tests before claiming done — LLMs confidently claim 'done' without verification, and this is the single most common failure mode"

**Include rationalization prevention.** LLMs generate plausible excuses to skip hard steps. Add an "Excuses vs. Reality" table that pre-empts the common rationalizations for the skill's domain. This is the most effective compliance pattern in this project.

**Use hard gates, not soft suggestions.** "Should" is ignored; "must, with evidence" is followed. Gate pattern: require tool output (paste the result) as proof that a step was completed. Without evidence, the agent cannot proceed.

**Constrain scope explicitly.** Skills that try to cover everything get applied inconsistently. Define clear boundaries: what this skill covers, what it doesn't, and what adjacent skills handle the rest.

**Test against the forgetting curve.** Skills are most likely to be skipped when the agent is deep in implementation and eager to deliver. Front-load the most critical constraints in the skill's ## Constraints section — they're read first and remembered longest.

**Apply TDD to skill-writing itself.**
1. **RED**: Run the task scenario WITHOUT the skill. Observe how the agent naturally fails.
2. **GREEN**: Write the minimal skill that addresses those specific failures.
3. **REFACTOR**: Capture the verbatim excuses the agent generated during baseline testing and build explicit counters into a rationalization prevention table.

**Optimize skill descriptions for triggering.** The `description` field in frontmatter determines whether the skill gets invoked. Descriptions that summarize the workflow cause the agent to follow the description instead of reading the full skill. Descriptions should contain triggering conditions only — *when should I use this?* — not workflow summaries.

## Registration

After creating an agent or skill, follow the registration checklist in [`references/templates.md`](references/templates.md#registration-checklist). For agents, `/agent-add` performs registration automatically; for skills and slash commands, follow the manual steps. Incomplete registration leaves the system in an inconsistent state.

## Documentation Sync Policy

Every change must be reflected in documentation. See the sync policy and source-of-truth table in [`references/templates.md`](references/templates.md#documentation-sync-policy).

## Output

New or updated `$PLUGIN/skills/*/SKILL.md` file(s) with all registry tables and docs updated. Be concise — confirm what was created/updated and its registration status.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
| --- | --- | --- |
| Skill logic embedded in agent | Duplicated across agents, hard to update | Extract to a skill file, reference from agent |
| Agent behavior embedded in skill | Skill becomes role-specific, can't be reused | Move persona/judgment logic to the agent |
| Skill without any agent reference | Orphaned knowledge, never invoked | Add to relevant agents or remove |
| Agent without Skills section | All knowledge is inline, nothing is reusable | Identify extractable capabilities |
| Overly broad skill | Tries to cover too much, hard to reference precisely | Split into focused skills |
| Hand-authoring an agent file | Drifts from the schema enforced by /plugin-audit | Use /agent-add (invokes the agent-create skill) |
| Deferred tool called before its schema loads | Assumed shape (e.g. batched `TaskCreate`) fails with `InputValidationError` | Call `ToolSearch("select:<ToolName>")` first; state the real per-call contract |
