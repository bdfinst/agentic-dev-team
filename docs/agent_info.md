# Agents

Agents define **who does the work**. Each agent file in `.claude/agents/` specifies a role's persona, behavior, collaboration style, and which skills it uses.

## Agent Roster

| Agent | File | ~Tokens | Purpose |
| --- | --- | --- | --- |
| Scrum Master | [`scrum-master.md`](../.claude/agents/scrum-master.md) | 370 | Routes tasks, coordinates multi-agent work, manages context budget |
| Software Engineer | [`software-engineer.md`](../.claude/agents/software-engineer.md) | 300 | Code generation, implementation, refactoring, bug fixes |
| Data Scientist | [`data-scientist.md`](../.claude/agents/data-scientist.md) | 290 | ML models, data analysis, statistical validation |
| QA/SQA Engineer | [`qa-engineer.md`](../.claude/agents/qa-engineer.md) | 310 | Test generation, automated testing, quality gates |
| UI/UX Designer | [`ui-ux-designer.md`](../.claude/agents/ui-ux-designer.md) | 300 | Interface design, UX flows, accessibility compliance |
| Architect | [`architect.md`](../.claude/agents/architect.md) | 360 | System design, tech decisions, scalability planning |
| Product Manager | [`product-manager.md`](../.claude/agents/product-manager.md) | 300 | Requirements clarification, prioritization, stakeholder alignment |
| Technical Writer | [`tech-writer.md`](../.claude/agents/tech-writer.md) | 560 | Documentation, terminology consistency, style enforcement |

## Persona Template

Every agent file follows this structure:

```markdown
# [Role Name] Agent

## Technical Responsibilities
- [Primary capabilities - what this agent delivers]

## Skills
- [Skill Name](../skills/{file}.md) - [when/why this agent uses it]

## Collaboration Protocols
### Primary Collaborators
- [Agent Name]: [What they exchange]

### Communication Style
- [Tone, detail level, update frequency]

## Behavioral Guidelines
### Decision Making
- Autonomy level: [High/Moderate/Low] for [what]
- Escalation criteria: [When to escalate]
- Human approval requirements: [What needs sign-off]

### Conflict Management
- [How disagreements are resolved]

## Psychological Profile
- Work style: [Preferences]
- Problem-solving approach: [Methods]
- Quality vs. speed trade-offs: [Tendencies]

## Success Metrics
- [Measurable KPIs]
```

The `## Skills` section is the bridge between agents and skills. The agent defines *when and why* to invoke a skill; the skill defines *how* to execute it.

## Add a New Agent

1. Create `agents/{role-name}.md` using the template above
2. Add the agent to the Team Organization diagram in `CLAUDE.md`
3. Add it to the Agent Registry table in `CLAUDE.md`
4. Define collaboration protocols with existing agents
5. Reference any applicable skills in the `## Skills` section

See [Agent & Skill Authoring](../.claude/skills/agent-skill-authoring.md) for detailed guidelines.

## Remove an Agent

1. Delete the agent file from `agents/`
2. Remove it from the organization diagram and registry in `CLAUDE.md`
3. Update other agents' collaboration protocols that referenced the removed agent
