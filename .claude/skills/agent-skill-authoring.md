---
name: agent-skill-authoring
description: How to create and maintain agents and skills within the Agentic Scrum Team system
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

### File Location
`.claude/agents/{role-name}.md`

### Required Sections

```markdown
# [Role Name] Agent

## Technical Responsibilities
- [Primary capabilities in imperative form]
- [Keep to 4-8 items that define the role's scope]

## Skills
- [Skill Name](../skills/{skill-file}.md) - [When/why this agent uses it]
- [Skill Name](../skills/{skill-file}.md) - [When/why this agent uses it]

## Collaboration Protocols

### Primary Collaborators
- [Agent Name]: [Nature of collaboration - what they exchange]

### Communication Style
- [Tone and approach]
- [Level of detail]
- [Update frequency]

## Behavioral Guidelines

### Decision Making
- Autonomy level: [High/Moderate/Low] for [what]
- Escalation criteria: [When to escalate]
- Human approval requirements: [What needs human sign-off]

### Conflict Management
- [How to handle disagreements with other agents]
- [Resolution protocols]
- [Escalation paths]

## Psychological Profile
- Work style: [Preferences]
- Problem-solving approach: [Methods]
- Quality vs. speed trade-offs: [Tendencies]

## Success Metrics
- [Measurable KPIs for this role]
```

### Agent Authoring Guidelines
- Keep agents focused on orchestration: *when* to act, *who* to collaborate with, *why* to escalate
- Execution details belong in skills, not in the agent persona
- The Skills section links to skill files with a short annotation explaining invocation context
- If an agent's Technical Responsibilities section grows beyond 8 items, extract a skill
- Behavioral Guidelines define personality and judgment, not technical procedures

## Creating a Skill

### File Location
`.claude/skills/{skill-name}.md`

### Required Sections

```markdown
# [Skill Name]

## Overview
[1-2 sentences: what this skill covers and why it matters]

## Core Concepts
[Key terminology and mental models needed to apply this skill]

## Patterns
[Named patterns with descriptions, when to use, and examples]

## Project Structure (if applicable)
[Directory layout or file organization this skill implies]

## Guidelines
[Actionable rules for applying this skill correctly]
```

### Skill Authoring Guidelines
- Skills must be agent-agnostic: no references to specific agent personas or behaviors
- Write in imperative/instructional tone, not persona-driven
- Include "when to apply" vs. "when not to apply" guidance to prevent over-application
- Use tables for decision matrices (situation -> approach)
- Include project structure templates when the skill implies a file organization
- Keep skills focused on a single cohesive topic; split broad topics into multiple skills

## Registration

After creating an agent or skill, update `.claude/CLAUDE.md`:

### For a New Agent
1. Add to the **Agent Registry** table
2. Add to the **Team Organization** mermaid diagram
3. Define collaboration edges with existing agents

### For a New Skill
1. Add to the **Skills Registry** table with the "Used By" column listing all referencing agents
2. Add a reference in each agent's `## Skills` section with invocation context

## Output
New or updated `.claude/agents/*.md` or `.claude/skills/*.md` file(s) with corresponding CLAUDE.md registry entries updated. Be concise — confirm what was created/updated and its registration status.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
| --- | --- | --- |
| Skill logic embedded in agent | Duplicated across agents, hard to update | Extract to a skill file, reference from agent |
| Agent behavior embedded in skill | Skill becomes role-specific, can't be reused | Move persona/judgment logic to the agent |
| Skill without any agent reference | Orphaned knowledge, never invoked | Add to relevant agents or remove |
| Agent without Skills section | All knowledge is inline, nothing is reusable | Identify extractable capabilities |
| Overly broad skill | Tries to cover too much, hard to reference precisely | Split into focused skills |
