# Skills

Skills define **what agents know**. Each skill file in `.claude/skills/` captures reusable knowledge (patterns, guidelines, procedures) that any agent can reference.

## Skills Catalog

### Orchestration Skills

Used by the Orchestrator to manage the team:

| Skill | File | ~Tokens | Purpose |
| --- | --- | --- | --- |
| Context Loading Protocol | [`context-loading-protocol.md`](../.claude/skills/context-loading-protocol.md) | 600 | Decides which agent/skill files to load and when |
| Context Summarization | [`context-summarization.md`](../.claude/skills/context-summarization.md) | 500 | Compresses conversation history at utilization thresholds |
| Feedback & Learning | [`feedback-learning.md`](../.claude/skills/feedback-learning.md) | 1,010 | Processes feedback keywords, audit trail, rollback |
| Human Oversight Protocol | [`human-oversight-protocol.md`](../.claude/skills/human-oversight-protocol.md) | 1,020 | Approval gates, intervention commands, escalation |
| Performance Metrics | [`performance-metrics.md`](../.claude/skills/performance-metrics.md) | 890 | Task logging schema and reporting procedures |

### Quality Skills

Used by all agents to ensure output correctness:

| Skill | File | ~Tokens | Purpose |
| --- | --- | --- | --- |
| Accuracy Validation | [`accuracy-validation.md`](../.claude/skills/accuracy-validation.md) | 880 | Self-validation checklist, hallucination detection, confidence scoring |
| Governance & Compliance | [`governance-compliance.md`](../.claude/skills/governance-compliance.md) | 990 | Audit trail, quality assurance layers, ethics principles |

### Technical Skills

Domain knowledge for implementation work:

| Skill | File | ~Tokens | Purpose |
| --- | --- | --- | --- |
| Hexagonal Architecture | [`hexagonal-architecture.md`](../.claude/skills/hexagonal-architecture.md) | 420 | Ports & adapters pattern, dependency rule, project structure |
| Domain-Driven Design | [`domain-driven-design.md`](../.claude/skills/domain-driven-design.md) | 710 | Bounded contexts, aggregates, domain events, ubiquitous language |

### Meta Skills

Skills about the system itself:

| Skill | File | ~Tokens | Purpose |
| --- | --- | --- | --- |
| Agent & Skill Authoring | [`agent-skill-authoring.md`](../.claude/skills/agent-skill-authoring.md) | 990 | How to create and maintain agents and skills |

## How Agents Use Skills

Agents reference skills in their `## Skills` section with invocation context:

```markdown
## Skills
- [Hexagonal Architecture](../skills/hexagonal-architecture.md) - invoke when structuring new services
- [Domain-Driven Design](../skills/domain-driven-design.md) - invoke when modeling bounded contexts
```

The annotation after the link explains *when and why* that agent uses the skill. The skill itself is agent-agnostic and defines *how*.

## Add a New Skill

1. Create `skills/{skill-name}.md` with the required sections (see below)
2. Add it to the Skills Registry table in `CLAUDE.md`
3. Reference it from each agent's `## Skills` section with invocation context

### Skill Template

```markdown
# [Skill Name]

## Overview
[What this skill covers and why it matters]

## Core Concepts
[Key terminology and mental models]

## Patterns
[Named patterns with when-to-use guidance]

## Project Structure (if applicable)
[Directory layout this skill implies]

## Guidelines
[Actionable rules for applying this skill]
```

See [Agent & Skill Authoring](../.claude/skills/agent-skill-authoring.md) for detailed guidelines and anti-patterns.
