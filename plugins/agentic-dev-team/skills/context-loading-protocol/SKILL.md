---
name: context-loading-protocol
description: Decide which agents and skills to load for a given task. Use at the start of every task to select the minimum viable context load, calculate the token budget, and stay below the 40% utilization ceiling.
role: orchestrator
user-invocable: true
---

# Context Loading Protocol

## Overview

Concrete procedure for deciding which agent and skill files to load into context for a given task. The goal is to keep total context utilization below 40% of the model's window by loading only what's needed.

## Constraints
- Never load all agents upfront; load only the primary agent for each phase
- Keep total context below 40% of the model's window at all times
- Load agents on demand when their phase begins, not speculatively
- Do not copy-paste file contents into the prompt; use tool-based file reads

## Token Budget Reference

These are the measured sizes of each loadable file. CLAUDE.md is always loaded automatically (~870 tokens).

### Agents

| Agent | File | ~Tokens |
| --- | --- | --- |
| Orchestrator | `agents/orchestrator.md` | 370 |
| Software Engineer | `agents/software-engineer.md` | 300 |
| QA/SQA Engineer | `agents/qa-engineer.md` | 310 |
| UI/UX Designer | `agents/ui-ux-designer.md` | 300 |
| Architect | `agents/architect.md` | 360 |
| Product Manager | `agents/product-manager.md` | 300 |
| Technical Writer | `agents/tech-writer.md` | 560 |
| Security Engineer | `agents/security-engineer.md` | 320 |
| DevOps/SRE Engineer | `agents/devops-sre-engineer.md` | 320 |

### Skills

| Skill | File | ~Tokens |
| --- | --- | --- |
| Context Loading Protocol | `skills/context-loading-protocol/SKILL.md` | ~600 |
| Context Summarization | `skills/context-summarization/SKILL.md` | ~500 |
| Feedback & Learning | `skills/feedback-learning/SKILL.md` | ~1,010 |
| Human Oversight Protocol | `skills/human-oversight-protocol/SKILL.md` | ~1,020 |
| Performance Metrics | `skills/performance-metrics/SKILL.md` | ~890 |
| Quality Gate Pipeline | `skills/quality-gate-pipeline/SKILL.md` | ~900 |
| Governance & Compliance | `skills/governance-compliance/SKILL.md` | ~990 |
| Agent & Skill Authoring | `skills/agent-skill-authoring/SKILL.md` | ~990 |
| Hexagonal Architecture | `skills/hexagonal-architecture/SKILL.md` | ~420 |
| Domain-Driven Design | `skills/domain-driven-design/SKILL.md` | ~710 |
| Specs | `skills/specs/SKILL.md` | ~800 |
| Threat Modeling | `skills/threat-modeling/SKILL.md` | ~600 |
| API Design | `skills/api-design/SKILL.md` | ~600 |
| Legacy Code | `skills/legacy-code/SKILL.md` | ~700 |
| Mutation Testing | `skills/mutation-testing/SKILL.md` | ~700 |

### Always-Loaded Baseline
| Item | ~Tokens |
| --- | --- |
| CLAUDE.md (auto-loaded) | 870 |
| User request | varies |
| Conversation history | accumulates |

## Loading Decision Procedure

### Step 1: Classify the Task

Determine the **task profile** before loading anything:

| Task Profile | Description | Example |
| --- | --- | --- |
| **Simple/Single** | One agent, no skills needed | "Fix this typo", "Write a unit test" |
| **Standard/Single** | One agent + 1-2 skills | "Implement this feature using hexagonal architecture" |
| **Multi-Agent** | 2-3 agents coordinating | "Design and implement a new API endpoint" |
| **Complex/Multi** | 3+ agents + skills | "Build a new bounded context with full test coverage" |

### Step 2: Select Agents

Load the **minimum set** of agents required:

1. Identify the **primary agent** - who owns the deliverable
2. Identify **supporting agents** - who provides input or review
3. Do NOT load agents for downstream validation yet (load them when that phase begins)

**Loading order**: Primary agent first, then supporting agents one at a time as their phase begins.

### Step 3: Select Skills

For each loaded agent, check its `## Skills` section:

1. Only load skills **relevant to the current task** - not all skills an agent references
2. If the agent references 3 skills but only 1 applies, load only that 1
3. Skills shared by multiple loaded agents only need to be loaded once

### Step 4: Calculate Token Budget

Before loading, estimate the total:

```
Total = CLAUDE.md (~870)
      + conversation history (estimate)
      + agent files (sum selected)
      + skill files (sum selected)
      + expected output (estimate)
```

**Target: keep total under 40% of model context window.**

For Claude (200K window): target < 80K total context.
For typical tasks, the config files are a small fraction. The real budget concern is conversation history + output accumulation over multi-turn tasks.

### Step 5: Load via File Read

Instruct the Orchestrator to load files using the Read tool:

```
Read agents/software-engineer.md    → load persona
Read skills/hexagonal-architecture/SKILL.md → load skill
```

Do NOT load files by copy-pasting their contents into the system prompt or conversation. Use tool-based file reads so the content is available but retrievable on demand.

## Loading Profiles

Pre-computed loading sets for common task types:

### Code Implementation
- **Load**: Software Engineer + relevant skill(s)
- **~Tokens**: 300 + skill(s)
- **Defer**: QA (load after implementation), Architect (load only if design questions arise)

### Architecture Design
- **Load**: Architect + relevant architecture skill(s)
- **~Tokens**: 360 + skill(s)
- **Defer**: Software Engineer (load at implementation), QA (load at validation)

### Bug Fix
- **Load**: Software Engineer only
- **~Tokens**: 300
- **Defer**: QA (load if regression test needed)

### New Feature (Full Lifecycle)
Load in three phases, each in a fresh context window. A human review gate separates each phase. Phase output is a structured progress file in `memory/` that onboards the next phase.

| Phase | Load | Purpose | Output |
| --- | --- | --- | --- |
| 1. Research | Orchestrator + sub-agents (exploration) | Understand system, find files, trace data flows | Research progress file |
| 2. Plan | Architect + PM (if needed) + relevant skill(s) | Specify every change: files, snippets, tests | Implementation plan progress file |
| 3. Implement | Software Engineer + QA + skill(s) | Execute the plan, write code, run tests | Working code + test results |

**Key principles**:
- Each phase starts with a fresh context window, loading only the previous phase's progress file
- Human reviews and approves the progress file before the next phase begins
- Sub-agents are used primarily for context isolation — they search, read, and return concise findings so the parent context stays clean
- If implementation is large, compact mid-phase: update the plan progress file with completed steps and continue in a fresh context

## Output
Loading plan: selected agents and skills with their token costs, estimated total, and utilization percentage against the 40% ceiling. Be concise — one table, no narration.

## Unloading Strategy

Since we can't literally remove tokens from context, "unloading" means:

1. **Phase transitions**: Summarize the completed phase output into `memory/` and start a new conversation for the next phase
2. **Within a conversation**: Stop referencing the agent/skill; the Orchestrator mentally notes it's no longer active. Rely on context summarization (see Context Summarization skill) to compress stale content.
3. **Multi-turn accumulation**: When conversation history crosses 30% utilization, trigger summarization before loading additional agents

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
| --- | --- | --- |
| Loading all agents upfront | Wastes ~2,500 tokens before any work begins | Load only primary agent for the task |
| Loading all skills for an agent | Loads knowledge irrelevant to the task | Check skill relevance against the specific request |
| Never unloading | Context grows monotonically until hallucination risk | Summarize and phase-transition |
| Loading agents "just in case" | Adds cost without value | Load on demand when the agent's phase begins |
