# Agent & Skill Templates and Registration

## Agent Template

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

## Skill Template

```markdown
---
name: skill-name
description: When to trigger this skill and what it does. Be specific about the contexts that should cause an agent to invoke it.
role: worker
user-invocable: true
---

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

## Registration Checklist

After creating an agent or skill, update all of the following. Incomplete registration leaves the system in an inconsistent state.

### For a New Team Agent
1. Add to the **Team Agents** table in `.claude/CLAUDE.md`
2. Add a node and edges to the team diagram in `docs/team-structure.md`
3. Add a row to the Team Agents table in `docs/agent_info.md`
4. Define collaboration edges with existing agents

### For a New Review Agent
Use `/agent-add` -- it handles all registration steps automatically. For manual creation:
1. Add to the **Review Agents** table in `.claude/CLAUDE.md`
2. Add a row to the Review Agents table in `docs/agent_info.md`
3. Add to the dispatch diagram in `docs/team-structure.md`
4. Add eval fixtures to `.claude/evals/fixtures/` and expected results to `.claude/evals/expected/`

### For a New Knowledge Skill
1. Add to the **Skills Registry** table in `.claude/CLAUDE.md`
2. Add to the appropriate section of `docs/skills.md`
3. Reference it from each relevant agent's `## Skills` section with invocation context

### For a New Slash Command
1. Add to the **Slash Commands Registry** table in `.claude/CLAUDE.md`
2. Add to the appropriate section of `docs/skills.md`
3. Add a row to the relevant table in `README.md` if user-facing

## Documentation Sync Policy

**Every change to this repository must be reflected in documentation.** Enforced at three levels:

1. **Hook** -- `eval-compliance-check.sh` fires on every Edit/Write and emits targeted doc sync reminders
2. **Commands** -- `/agent-add` and `/agent-remove` include mandatory documentation update steps
3. **Orchestrator Phase 3 gate** -- tech-writer reviews all affected docs before task completion

| Change type | Source of truth | Must match |
|---|---|---|
| Agent files | `CLAUDE.md` agent tables | `docs/agent_info.md` tables + `README.md` |
| Slash commands | `CLAUDE.md` slash commands table | `docs/skills.md` commands tables + `README.md` |
| Model routing | `agents/orchestrator.md` Model Routing Table | `CLAUDE.md` Model Routing summary |
| Team structure | `docs/team-structure.md` Mermaid diagrams | Actual agent files in `agents/` |
| Behavior/workflow | `agents/orchestrator.md` Phase workflow | `README.md` Workflow section |
| Architecture | `docs/agent-architecture.md` | `README.md` architecture section |
| Config/setup | `settings.json` + hook scripts | `docs/agent-architecture.md` Governance section |
