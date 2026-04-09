---
name: agent-skill-authoring
description: How to create and maintain agent and skill files for the Agentic Scrum Team. Use whenever adding a new agent persona, creating a new skill, or updating an existing one — including required registration in CLAUDE.md.
role: worker
user-invocable: true
---

# Agent & Skill Authoring

## Overview

This skill defines how to create and maintain agents and skills within the Agentic Scrum Team system. Agents own orchestration logic (when and why); skills own execution knowledge (how). This separation keeps agents readable as workflow definitions while keeping capabilities DRY across the team.

## Constraints
- Skills must be agent-agnostic; no persona or behavioral logic in skill files
- Execution details belong in skills; orchestration logic belongs in agents
- Every new agent or skill must be registered in `.claude/CLAUDE.md`
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

Place agent files at `.claude/agents/{role-name}.md`. Use the agent template and authoring guidelines from [`references/templates.md`](references/templates.md#agent-template).

## Creating a Skill

Place skill files at `.claude/skills/{skill-name}.md`. Use the skill template and authoring guidelines from [`references/templates.md`](references/templates.md#skill-template).

## Meta-Patterns for Skill Writing

Before writing a new skill, read 2-3 existing skills in `skills/` to absorb the project's voice and structure. Skills that follow existing patterns integrate better.

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

After creating an agent, skill, or command, follow the registration checklist in [`references/templates.md`](references/templates.md#registration-checklist). Incomplete registration leaves the system in an inconsistent state.

## Documentation Sync Policy

Every change must be reflected in documentation. See the sync policy and source-of-truth table in [`references/templates.md`](references/templates.md#documentation-sync-policy).

## Output
New or updated `.claude/agents/*.md` or `.claude/skills/*.md` file(s) with all registry tables and docs updated. Be concise — confirm what was created/updated and its registration status.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
| --- | --- | --- |
| Skill logic embedded in agent | Duplicated across agents, hard to update | Extract to a skill file, reference from agent |
| Agent behavior embedded in skill | Skill becomes role-specific, can't be reused | Move persona/judgment logic to the agent |
| Skill without any agent reference | Orphaned knowledge, never invoked | Add to relevant agents or remove |
| Agent without Skills section | All knowledge is inline, nothing is reusable | Identify extractable capabilities |
| Overly broad skill | Tries to cover too much, hard to reference precisely | Split into focused skills |
