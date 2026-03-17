# Skills and Slash Commands

There are two kinds of reusable capabilities in this system:

- **Skills** (`/skills/`) — knowledge modules that agents read for domain expertise (patterns, guidelines, procedures). Agent-agnostic; any agent can reference them.
- **Slash commands** (`/commands/`) — user-invocable workflows with numbered steps, argument parsing, and structured output. Executed under Orchestrator direction.

## Skills Catalog

### Orchestration Skills

Used by the Orchestrator to manage the team:

| Skill | File | Purpose |
| --- | --- | --- |
| Context Loading Protocol | [`context-loading-protocol.md`](../.claude/skills/context-loading-protocol.md) | Decides which agent/skill files to load and when |
| Context Summarization | [`context-summarization.md`](../.claude/skills/context-summarization.md) | Compresses conversation history at utilization thresholds |
| Feedback & Learning | [`feedback-learning.md`](../.claude/skills/feedback-learning.md) | Processes feedback keywords, audit trail, rollback |
| Human Oversight Protocol | [`human-oversight-protocol.md`](../.claude/skills/human-oversight-protocol.md) | Approval gates, intervention commands, escalation |
| Performance Metrics | [`performance-metrics.md`](../.claude/skills/performance-metrics.md) | Task logging schema and reporting procedures |
| Agent & Skill Authoring | [`agent-skill-authoring.md`](../.claude/skills/agent-skill-authoring.md) | How to create and maintain agents and skills |
| Task Review & Correction | [`task-review-correction.md`](../.claude/skills/task-review-correction.md) | Review-correction loop coordination between agents |
| Agent-Assisted Specification | [`agent-assisted-specification.md`](../.claude/skills/agent-assisted-specification.md) | BDD scenario consistency gate before implementation |
| Beads Task Tracking | [`beads.md`](../.claude/skills/beads.md) | Beads issue lifecycle, session discipline, multi-agent coordination |

### Quality Skills

Used by all agents to ensure output correctness:

| Skill | File | Purpose |
| --- | --- | --- |
| Accuracy Validation | [`accuracy-validation.md`](../.claude/skills/accuracy-validation.md) | Self-validation checklist, hallucination detection, confidence scoring |
| Governance & Compliance | [`governance-compliance.md`](../.claude/skills/governance-compliance.md) | Audit trail, quality assurance layers, ethics principles |
| Verification Before Completion | [`verification-before-completion.md`](../.claude/skills/verification-before-completion.md) | Require fresh tool output as evidence before any completion claim |

### Development Discipline Skills

Enforce rigorous development practices:

| Skill | File | Purpose |
| --- | --- | --- |
| Test-Driven Development | [`test-driven-development.md`](../.claude/skills/test-driven-development.md) | RED-GREEN-REFACTOR cycle with hard gates, rationalization prevention |
| Systematic Debugging | [`systematic-debugging.md`](../.claude/skills/systematic-debugging.md) | 4-phase debugging protocol (reproduce, investigate, root-cause, fix) |
| Design Doc | [`design-doc.md`](../.claude/skills/design-doc.md) | Written design document with alternatives analysis before planning |
| Branch Workflow | [`branch-workflow.md`](../.claude/skills/branch-workflow.md) | PR creation, merge strategy, and branch cleanup after Phase 3 |

### Technical Skills

Domain knowledge for implementation work:

| Skill | File | Purpose |
| --- | --- | --- |
| Hexagonal Architecture | [`hexagonal-architecture.md`](../.claude/skills/hexagonal-architecture.md) | Ports & adapters pattern, dependency rule, project structure |
| Domain-Driven Design | [`domain-driven-design.md`](../.claude/skills/domain-driven-design.md) | Bounded contexts, aggregates, domain events, ubiquitous language |
| API Design | [`api-design.md`](../.claude/skills/api-design.md) | Contract-first design, versioning, REST conventions |
| Threat Modeling | [`threat-modeling.md`](../.claude/skills/threat-modeling.md) | STRIDE analysis, trust boundaries, mitigation strategies |
| Legacy Code | [`legacy-code.md`](../.claude/skills/legacy-code.md) | Characterization testing, safe refactoring in untested code |
| Mutation Testing | [`mutation-testing.md`](../.claude/skills/mutation-testing.md) | Evaluating test suite effectiveness against behavioral mutations |

### Subagent Prompt Templates

Concrete templates in `prompts/` for reproducible subagent dispatch:

| Template | File | Purpose |
| --- | --- | --- |
| Implementer | [`implementer.md`](../prompts/implementer.md) | Phase 3 implementation dispatch with TDD enforcement |
| Spec Reviewer | [`spec-reviewer.md`](../prompts/spec-reviewer.md) | Two-stage review gate 1: does code match spec? |
| Quality Reviewer | [`quality-reviewer.md`](../prompts/quality-reviewer.md) | Two-stage review gate 2: is code high quality? |
| Plan Reviewer | [`plan-reviewer.md`](../prompts/plan-reviewer.md) | Phase 2 automated pre-check before human review |

## Slash Commands Catalog

Slash commands are invoked by the user (e.g., `/code-review`) and executed under Orchestrator direction. The Orchestrator's Model Routing Table controls which model runs each review agent.

### Review Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/code-review` | [`code-review.md`](../.claude/commands/code-review.md) | Run all review agents with pre-flight gates (lint, type-check, secret scan) |
| `/review-agent <name>` | [`review-agent.md`](../.claude/commands/review-agent.md) | Run a single named review agent; used for inline Phase 3 checkpoints |
| `/apply-fixes` | [`apply-fixes.md`](../.claude/commands/apply-fixes.md) | Apply correction prompts generated by `/code-review` |
| `/review-summary` | [`review-summary.md`](../.claude/commands/review-summary.md) | Generate a compact session summary for cross-session context continuity |
| `/semgrep-analyze` | [`semgrep-analyze.md`](../.claude/commands/semgrep-analyze.md) | Run Semgrep static analysis and return structured findings |

### Eval Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-audit` | [`agent-audit.md`](../.claude/commands/agent-audit.md) | Audit agents and commands for structural compliance |
| `/agent-eval` | [`agent-eval.md`](../.claude/commands/agent-eval.md) | Run eval fixtures, grade review agent accuracy, detect regressions |

### Scaffolding Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-add` | [`agent-add.md`](../.claude/commands/agent-add.md) | Scaffold a new review agent with eval compliance check and doc updates |
| `/agent-remove` | [`agent-remove.md`](../.claude/commands/agent-remove.md) | Remove an agent and all its registry entries and doc references |
| `/add-plugin` | [`add-plugin.md`](../.claude/commands/add-plugin.md) | Install a plugin and register it in `settings.json` |

## How Agents Use Skills

Agents reference skills in their `## Skills` section with invocation context:

```markdown
## Skills
- [Hexagonal Architecture](../skills/hexagonal-architecture.md) - invoke when structuring new services
- [Domain-Driven Design](../skills/domain-driven-design.md) - invoke when modeling bounded contexts
```

The annotation explains *when and why* that agent uses the skill. The skill itself defines *how* and is agent-agnostic.

## Add a Knowledge Skill

1. Create `.claude/skills/{skill-name}.md` with the required sections (see template below)
2. Add it to the Skills Registry table in `.claude/CLAUDE.md`
3. Reference it from each relevant agent's `## Skills` section with invocation context

### Skill Template

```markdown
---
name: skill-name
description: When to trigger this skill and what it does.
role: worker
user-invocable: true
---

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

## Add a Slash Command

For a new review agent command, use `/add-agent`. For a new workflow command, create `.claude/commands/{name}.md` following the slash command structure (YAML frontmatter with `user-invocable: true`, `Role:` declaration, constraints, numbered steps). Run `/agent-audit` after creation.
