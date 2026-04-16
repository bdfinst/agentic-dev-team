# Agentic Scrum Team - Orchestration Pipeline

## System Overview

This project implements a fully automated development team using persona-driven AI agents. An orchestrator agent acts as the central dispatcher, routing tasks to specialized agents based on task classification, complexity, and required expertise. The agents, skills, and knowledge files in this repository are designed to work with any agent harness that supports markdown-based agent definitions.

## Core Principles

1. **Selective Agent Loading**: Only load necessary agents into context, avoiding token bloat. Target under 10,000 tokens for simple tasks.
2. **40% Context Window Rule**: Maintain context below 40% capacity to prevent hallucination. Trigger summarization at threshold.
3. **Persona-Driven Behavior**: Each agent has detailed psychological and behavioral specifications that guide its output style, decision-making, and collaboration patterns.
4. **Human-in-the-Loop**: Agents are autonomous but require oversight, not copilots.
5. **Acceptance Test Driven Development**: All development follows ATDD. Behaviors are defined as scenarios in feature files (Gherkin) before implementation begins. Feature file scenarios are the single source of truth for expected behavior.

## Team Organization

### Quick Reference

**Team agents** (11): Orchestrator, Software Engineer, Data Scientist, QA Engineer, UI/UX Designer, Architect, Product Manager, Technical Writer, Security Engineer, DevOps/SRE Engineer, ADR Author (~3,900 tokens total)

**Review agents** (19): spec-compliance-review, a11y-review, arch-review, claude-setup-review, complexity-review, concurrency-review, doc-review, domain-review, js-fp-review, naming-review, performance-review, security-review, structure-review, svelte-review, test-review, token-efficiency-review, refactoring-review, progress-guardian, data-flow-tracer

**Skills** (33): Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Quality Gate Pipeline, Governance & Compliance, Agent & Skill Authoring, Hexagonal Architecture, Domain-Driven Design, Domain Analysis, Specs, Threat Modeling, API Design, Legacy Code, Mutation Testing, Test-Driven Development, Systematic Debugging, Design Doc, Branch Workflow, CI Debugging, Test Design Reviewer, Browser Testing, Competitive Analysis, Design Interrogation, Design It Twice, Static Analysis Integration, Feature File Validation, Docker Image Create, Docker Image Audit, Performance Benchmark, Receiving Code Review, JS Project Init

Skills are located in `.agents/skills/` per Codex convention. See CODEX-INSTALL.md for setup instructions.

## Three-Phase Workflow

For non-trivial tasks, the orchestrator follows a **Research, Plan, Implement** workflow with human review gates between each phase.

### 1. Research

Understand the system: find relevant files, trace data flows, identify the problem surface area. Agents explore the codebase and return concise findings. For non-trivial features, produce a design document with problem statement, approach, alternatives, and scope boundaries. Optionally run Design Interrogation to stress-test the design or Design It Twice to generate parallel alternative interfaces.

**Human Review Gate** -- Human reviews research findings and design doc before planning begins.

### 2. Plan

Specify every change: files, snippets, test strategy, verification steps. Before the human sees the plan, four plan review personas evaluate it in parallel: Acceptance Test Critic, Design & Architecture Critic, UX Critic, and Strategic Critic. Any blocker findings are addressed before the human gate. The plan is the primary review artifact.

**Human Review Gate** -- Human reviews the plan. This replaces traditional line-by-line code review as the primary quality gate.

### 3. Implement

Execute the plan. All code follows RED-GREEN-REFACTOR with vertical slices (TDD skill). After each unit, inline reviews check spec compliance and code quality. Actionable issues are fixed and re-reviewed in a loop. All agents must provide verification evidence (fresh test output) before claiming completion.

**Human Review Gate** -- Human reviews the final output. Lightweight if the plan was correct.

After implementation: create PR, choose merge strategy, clean up branch. Then update configs if needed, log metrics, refine routing.

## Skills by Phase

| Phase | Skills Used | Purpose |
|-------|-----------|---------|
| **Research** | Design Doc, Domain Analysis, Domain-Driven Design, Threat Modeling, Design Interrogation, Design It Twice, Competitive Analysis | Understand the system, explore alternatives, stress-test designs |
| **Plan** | Specs, API Design, Hexagonal Architecture, Legacy Code | Define what to build, specify interfaces and test strategy |
| **Implement** | Test-Driven Development, Systematic Debugging, Mutation Testing, Browser Testing, Performance Benchmark, CI Debugging | Build with TDD, debug issues, validate quality, measure performance |
| **Review** | Quality Gate Pipeline, Test Design Reviewer | Validate output before delivery |
| **Cross-phase** | Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Governance & Compliance, Branch Workflow, Agent & Skill Authoring | Orchestration, context management, learning |

## Sub-Agents as Context Isolation

The primary value of sub-agents is context isolation, not persona specialization. When a parent agent dispatches a sub-agent to explore, search, or analyze, the sub-agent absorbs the context burden of reading files and tracing code flows. Only a concise, structured finding returns to the parent, keeping the parent's context clean and focused.

Design sub-agent calls for minimal context return:
- Send the sub-agent a specific question ("Where is user authentication handled? Return file paths and line numbers.")
- The sub-agent reads 20 files; the parent receives 10 lines of structured findings
- The parent can get right to work without the context burden of exploration

## Output Guardrails

1. **Write to files, not chat.** Artifacts (plans, design docs, reports, code) go to files. Chat is for decisions, status updates, and questions.
2. **Plan-only mode.** When asked for a plan, produce ONLY the plan. Do not start implementing.
3. **Incremental output.** Produce a first draft within 3-4 tool calls, then refine iteratively.

## Quality and Accuracy

All agents apply the Quality Gate Pipeline before delivering output: self-validation (Phase 1), verification evidence (Phase 2), and review-correction loops (Phase 3).

## Context Management

Context management is the orchestrator's responsibility, governed by two skills:

1. **Context Loading Protocol** -- decides what to load and when, using task classification, phased loading, and measured token budgets
2. **Context Summarization** -- decides when to compress and how, using utilization triggers and structured summaries

### Operating Rules
1. **Load on demand**: Only load agent/skill files when their phase begins
2. **40% utilization ceiling**: Trigger summarization when context approaches 40% utilization
3. **Phase transitions**: Summarize completed phases before loading next-phase agents
4. **Summaries replace history**: New conversations read from summaries, not from prior conversation replay

## Feedback and Learning

Users can modify system behavior at any time using trigger keywords (`amend`, `learn`, `remember`, `forget`). Changes are logged with full audit trail and rollback support.

## Human Oversight

Agents operate autonomously within defined boundaries. Human involvement is required for high-impact decisions (production deployments, architecture changes, scope modifications).

Intervention commands: `amend`, `learn`, `remember`, `forget`, `override`, `pause`, `stop`.

## Capability Limitations on Codex

The agentic-dev-team plugin was designed for full multi-agent orchestration. When running on OpenAI Codex CLI, the following limitations apply:

- **Multi-agent orchestration**: Codex does not automatically dispatch sub-agents. To use a team agent or review agent, you must explicitly request it in your prompt (e.g., "Act as the Software Engineer agent and implement this feature"). The orchestrator cannot spawn agents on your behalf.
- **Hook-based guards**: The plugin's PreToolUse and PostToolUse hooks (destructive command blocking, path guards, scope locks) have limited support on Codex. The `.codex/hooks.json` file is provided but currently empty while the Codex hooks API stabilizes.
- **Tool scoping**: The `allowed-tools:` frontmatter used by some agents to restrict which tools they can invoke is not available on Codex. All tools are available to all agents.
- **Model routing**: The plugin's model routing table (haiku/sonnet/opus assignments per agent) does not apply. Use Codex's own model and profile system to select models for different tasks.
- **Slash commands**: The `/command` invocation syntax is specific to Claude Code. On Codex, read the corresponding command file (in `commands/`) and follow its instructions manually, or adapt the workflow to Codex's prompt style.
- **Worktree isolation**: The `isolation: "worktree"` directive for parallel sub-agent execution is not supported. Run tasks sequentially or manage parallelism outside Codex.

For full orchestration capability -- automatic sub-agent dispatch, hook-based guards, model routing, and slash commands -- use the Claude Code plugin.
