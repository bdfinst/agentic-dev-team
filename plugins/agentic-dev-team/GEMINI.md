# Agentic Scrum Team - Gemini CLI Context

## System Overview

This plugin implements a fully automated development team using persona-driven AI agents. An intelligent coordination pipeline routes tasks to specialized agents based on task classification, complexity, and required expertise. On Gemini CLI, workflows run inline rather than through multi-agent orchestration; the agent harness dispatches work sequentially within the current context.

## Architecture

This plugin uses a layered loading strategy to minimize token usage:

- **GEMINI.md**: Core philosophy + quick reference (always loaded)
- **Skills**: Detailed patterns and procedures (loaded on-demand when a phase or task requires them)
- **Knowledge**: Reference data — registries, rubrics, detection patterns (loaded on-demand by agents)
- **Agents**: Behavioral specifications (loaded per-phase, never all at once)

## Core Principles

1. **Selective Loading**: Only load necessary agents and skills into context, avoiding token bloat. Target < 10,000 tokens for simple tasks.
2. **40% Context Window Rule**: Maintain context below 40% capacity to prevent hallucination. Trigger summarization at threshold.
3. **Persona-Driven Behavior**: Each agent has detailed psychological and behavioral specifications.
4. **Human-in-the-Loop**: Agents are autonomous but require oversight, not copilots.
5. **Acceptance Test Driven Development**: All development follows ATDD. Behaviors are defined as scenarios in feature files (Gherkin) before implementation begins.

## Team Organization

### Quick Reference

**Team agents** (11): Orchestrator, Software Engineer, Data Scientist, QA Engineer, UI/UX Designer, Architect, Product Manager, Technical Writer, Security Engineer, DevOps/SRE Engineer, ADR Author

**Review agents** (19): spec-compliance-review, a11y-review, arch-review, claude-setup-review, complexity-review, concurrency-review, doc-review, domain-review, js-fp-review, naming-review, performance-review, security-review, structure-review, svelte-review, test-review, token-efficiency-review, refactoring-review, progress-guardian, data-flow-tracer

**Skills** (31): Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Quality Gate Pipeline, Governance & Compliance, Agent & Skill Authoring, Hexagonal Architecture, Domain-Driven Design, Domain Analysis, Specs, Threat Modeling, API Design, Legacy Code, Mutation Testing, Test-Driven Development, Systematic Debugging, Design Doc, Branch Workflow, CI Debugging, Test Design Reviewer, Browser Testing, Competitive Analysis, Design Interrogation, Design It Twice, Static Analysis Integration, Feature File Validation, Docker Image Create, Docker Image Audit, Performance Benchmark

**Knowledge files** (6): agent-registry, review-template, review-rubric, owasp-detection, domain-modeling, architecture-assessment

### Skills by Phase

| Phase | Skills Used | Purpose |
|-------|-----------|---------|
| **Research** | Design Doc, Domain Analysis, Domain-Driven Design, Threat Modeling, Design Interrogation, Design It Twice, Competitive Analysis | Understand the system, explore alternatives, stress-test designs |
| **Plan** | Specs, API Design, Hexagonal Architecture, Legacy Code | Define what to build, specify interfaces and test strategy |
| **Implement** | Test-Driven Development, Systematic Debugging, Mutation Testing, Browser Testing, Performance Benchmark, CI Debugging | Build with TDD, debug issues, validate quality, measure performance |
| **Review** | Quality Gate Pipeline, Test Design Reviewer | Validate output before delivery |
| **Cross-phase** | Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Governance & Compliance, Branch Workflow, Agent & Skill Authoring | Orchestration, context management, learning |

## Gemini CLI Commands

The `commands-gemini/` directory contains Gemini-format (TOML) equivalents of key commands. The `skills/` directory is shared with the Claude Code plugin and works identically on Gemini CLI — load skill files on demand when a phase or task requires them.

Available commands:

| Command | Description |
|---------|-------------|
| `agentic-dev-team:code-review` | Run a code review on changed files with categorized findings |
| `agentic-dev-team:plan` | Create a structured implementation plan with TDD steps |
| `agentic-dev-team:build` | Execute the most recently approved plan using RED-GREEN-REFACTOR |
| `agentic-dev-team:help` | List all available commands and skills |
| `agentic-dev-team:browse` | Browser-based QA with screenshot and accessibility review |

## Request Processing Flow

For trivial tasks (typo fix, simple query), route directly to the relevant skill. For non-trivial tasks, follow the **Research - Plan - Implement** workflow:

1. **Research** — Understand the system: find relevant files, trace data flows, identify the problem surface area. Produce a design document at `docs/specs/` for non-trivial features.
2. **Human Review Gate** — Human reviews research findings and design doc.
3. **Plan** — Specify every change: files, snippets, test strategy, verification steps. The plan is the primary review artifact.
4. **Human Review Gate** — Human reviews the plan.
5. **Implement** — Execute the plan. All code follows RED-GREEN-REFACTOR with vertical slices (TDD skill). Run code review before committing.
6. **Human Review Gate** — Human reviews the final output.
7. **Learning loop** — Update configs if needed, log metrics, refine routing.

## Context Management

- **Load on demand**: Only load agent/skill files when their phase begins.
- **40% utilization ceiling**: Trigger summarization when context approaches 40% utilization.
- **Phase transitions**: Summarize completed phases before loading next-phase agents.
- **Summaries replace history**: New conversations read from `memory/`, not from prior conversation replay.

## Quality and Accuracy

All agents apply the Quality Gate Pipeline before delivering output: self-validation (Phase 1), verification evidence (Phase 2), and review-correction loops (Phase 3).

## Capability Limitations on Gemini CLI

The following features from the full plugin require Claude Code and are not available on Gemini CLI:

- **Multi-agent orchestration** is not available. Claude Code's Agent tool with model override enables parallel sub-agent dispatch and context isolation. On Gemini CLI, all workflows run inline within a single context.
- **Hook-based guards** have limited support. Claude Code hooks use a stdin JSON protocol for PreToolUse/PostToolUse interception. See `hooks/hooks-gemini.json` for Gemini-compatible hooks (currently experimental).
- **Tool scoping** is not available. Claude Code commands can restrict which tools an agent may use via allowed-tools declarations. On Gemini CLI, commands have full tool access.
- **Model routing** is not available. Claude Code's orchestrator routes agents to specific model tiers (haiku/sonnet/opus) based on task complexity. Gemini CLI uses its own model selection.

For full orchestration capability including multi-agent workflows, hook-based safety guards, tool scoping, and model routing, use the Claude Code plugin.
