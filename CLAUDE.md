# Agentic Scrum Team - Orchestration Pipeline

## System Overview

This project implements a fully automated development team using persona-driven AI agents orchestrated through an intelligent coordination pipeline. The Orchestrator agent acts as the central dispatcher, routing tasks to specialized agents based on task classification, complexity, and required expertise.

## Core Principles

1. **Selective Agent Loading**: Only load necessary agents into context, avoiding token bloat. Target < 10,000 tokens for simple tasks.
2. **40% Context Window Rule**: Maintain context below 40% capacity to prevent hallucination. Trigger summarization at threshold.
3. **Persona-Driven Behavior**: Each agent has detailed psychological and behavioral specifications defined in `.claude/agents/`.
4. **Human-in-the-Loop**: Agents are autonomous but require oversight, not copilots.
5. **Dynamic Configuration**: User-level configuration updates through federated learning.
6. **Acceptance Test Driven Development**: All development follows ATDD. Behaviors are defined as scenarios in feature files (Gherkin) before implementation begins. Feature file scenarios are the single source of truth for expected behavior — no implementation without a corresponding scenario, no scenario without a corresponding test.

## Team Organization

See @docs/team-structure.md for the full team org chart (Mermaid diagram).

## Agent Registry

### Team Agents

| Agent | File | ~Tokens | Primary Focus |
|-------|------|---------|---------------|
| Orchestrator | `agents/orchestrator.md` | 500 | Task routing, model selection, review coordination |
| Software Engineer | `agents/software-engineer.md` | 320 | Code generation, implementation |
| Data Scientist | `agents/data-scientist.md` | 290 | ML models, data analysis |
| QA/SQA Engineer | `agents/qa-engineer.md` | 320 | Testing, quality assurance |
| UI/UX Designer | `agents/ui-ux-designer.md` | 300 | Interface design, UX |
| Architect | `agents/architect.md` | 360 | System design, architecture |
| Product Manager | `agents/product-manager.md` | 300 | Requirements, prioritization |
| Technical Writer | `agents/tech-writer.md` | 560 | Documentation, style consistency |
| Security Engineer | `agents/security-engineer.md` | 320 | Security analysis, threat modeling |
| DevOps/SRE Engineer | `agents/devops-sre-engineer.md` | 320 | Pipeline, deployment, reliability |
| **All team agents** | | **~3,590** | |

### Review Agents

Spawned by the orchestrator during Phase 3 inline checkpoints and full `/code-review` runs. Model selection follows the **Orchestrator Model Routing Table** in `agents/orchestrator.md`.

| Agent | File | Model Tier | What It Checks |
|-------|------|------------|----------------|
| a11y-review | `agents/a11y-review.md` | mid | WCAG 2.1 AA, ARIA, keyboard nav, focus management |
| arch-review | `agents/arch-review.md` | frontier | ADR compliance, layer boundary violations, dependency direction, pattern consistency |
| claude-setup-review | `agents/claude-setup-review.md` | small | CLAUDE.md completeness, rules, skills, path accuracy |
| complexity-review | `agents/complexity-review.md` | small | Function size, cyclomatic complexity, nesting, parameters |
| concurrency-review | `agents/concurrency-review.md` | mid | Race conditions, async pitfalls, shared state |
| doc-review | `agents/doc-review.md` | mid | README accuracy, API doc alignment, inline comment drift, ADR update triggers |
| domain-review | `agents/domain-review.md` | frontier | Domain boundaries, abstraction leaks, entity/DTO confusion |
| js-fp-review | `agents/js-fp-review.md` | mid | Array mutations, impure patterns, global state |
| naming-review | `agents/naming-review.md` | small | Intent-revealing names, boolean prefixes, magic values |
| performance-review | `agents/performance-review.md` | small | Resource leaks, N+1 queries, unbounded growth |
| security-review | `agents/security-review.md` | frontier | Injection, auth/authz, data exposure, crypto |
| structure-review | `agents/structure-review.md` | mid | SRP violations, DRY, coupling, file organization |
| svelte-review | `agents/svelte-review.md` | mid | Svelte reactivity pitfalls, closure state leaks |
| test-review | `agents/test-review.md` | mid | Coverage gaps, assertion quality, test hygiene |
| token-efficiency-review | `agents/token-efficiency-review.md` | small | File/function size, LLM anti-patterns, token usage |

## Skills Registry

Skills are reusable knowledge modules in `.claude/skills/` that agents reference. They define patterns, guidelines, and project structures without being tied to any single agent persona.

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Context Loading Protocol | `skills/context-loading-protocol.md` | 600 | Orchestrator |
| Context Summarization | `skills/context-summarization.md` | 500 | Orchestrator |
| Feedback & Learning | `skills/feedback-learning.md` | 1,010 | Orchestrator |
| Human Oversight Protocol | `skills/human-oversight-protocol.md` | 1,020 | Orchestrator, Product Manager |
| Performance Metrics | `skills/performance-metrics.md` | 890 | Orchestrator |
| Accuracy Validation | `skills/accuracy-validation.md` | 880 | All agents |
| Governance & Compliance | `skills/governance-compliance.md` | 990 | QA Engineer, Technical Writer |
| Agent & Skill Authoring | `skills/agent-skill-authoring.md` | 990 | Orchestrator |
| Hexagonal Architecture | `skills/hexagonal-architecture.md` | 420 | Architect, Software Engineer |
| Domain-Driven Design | `skills/domain-driven-design.md` | 710 | Architect, Software Engineer, Product Manager |
| Domain Analysis | `skills/domain-analysis.md` | 650 | Architect, Product Manager, Orchestrator |
| Task Review & Correction | `skills/task-review-correction.md` | 600 | QA Engineer, Orchestrator, All agents (self-review) |
| Agent-Assisted Specification | `skills/agent-assisted-specification.md` | 800 | Product Manager, Architect, QA Engineer, Orchestrator |
| Threat Modeling | `skills/threat-modeling.md` | 600 | Security Engineer, Architect |
| API Design | `skills/api-design.md` | 600 | Architect, Software Engineer |
| Legacy Code | `skills/legacy-code.md` | 700 | Software Engineer, QA Engineer, Architect |
| Mutation Testing | `skills/mutation-testing.md` | 700 | QA Engineer, Software Engineer |
| Beads Task Tracking | `skills/beads.md` | 500 | Orchestrator, Software Engineer, QA Engineer |

## Slash Commands Registry

User-invocable workflows in `.claude/commands/`. All review commands are executed under orchestrator direction. The orchestrator's **Model Routing Table** (`agents/orchestrator.md`) determines model assignment for all review agents.

| Command | File | Role | What It Does |
|---------|------|------|--------------|
| `/code-review` | `commands/code-review.md` | orchestrator | Run all enabled review agents with pre-flight gates |
| `/review-agent` | `commands/review-agent.md` | worker | Run a single review agent (used for inline checkpoints) |
| `/eval-audit` | `commands/eval-audit.md` | orchestrator | Audit agents/commands/hooks for structural compliance |
| `/eval-runner` | `commands/eval-runner.md` | orchestrator | Run eval fixtures, grade accuracy, detect regressions |
| `/agent-add` | `commands/agent-add.md` | implementation | Scaffold a new review agent with eval compliance and doc updates |
| `/agent-remove` | `commands/agent-remove.md` | implementation | Remove an agent and all its registry entries and doc references |
| `/add-plugin` | `commands/add-plugin.md` | implementation | Install a plugin and register it in settings.json |
| `/apply-fixes` | `commands/apply-fixes.md` | implementation | Apply correction prompts from `/code-review` output |
| `/review-summary` | `commands/review-summary.md` | orchestrator | Generate compact session summary for context continuity |
| `/semgrep-analyze` | `commands/semgrep-analyze.md` | worker | Run Semgrep SAST and return structured findings |
| `/domain-analysis` | `commands/domain-analysis.md` | worker | Assess existing system DDD health: bounded contexts, context map, event storm, value stream, friction report |

## Request Processing Flow

For trivial tasks (typo fix, simple query), the Orchestrator routes directly to a single agent. For non-trivial tasks, the Orchestrator follows the **Research → Plan → Implement** workflow:

### Three-Phase Workflow
1. **Research** — Understand the system: find relevant files, trace data flows, identify the problem surface area. Sub-agents explore the codebase and return concise findings to keep the parent context clean. Output: research progress file written to `memory/`.
2. **Human Review Gate** — Human reviews research findings. Catching a misunderstanding here prevents hundreds of bad lines of code.
3. **Plan** — Specify every change: files, snippets, test strategy, verification steps. The plan is the primary review artifact — 200 lines of plan is far more reviewable than 2,000 lines of code. Output: implementation plan progress file written to `memory/`.
4. **Human Review Gate** — Human reviews the plan. This replaces traditional line-by-line code review as the primary quality gate.
5. **Implement** — Execute the plan. Write code, run tests, verify at each step. After each discrete unit of work, the orchestrator runs an **inline review checkpoint** using targeted review agents. Review findings feed back to the coding agent (max 2 correction iterations). Run `/code-review --changed` before committing. Then invoke the tech-writer to verify all affected documentation is current before the human gate. Output: working code + test results + code review pass + docs verified.
6. **Human Review Gate** — Human reviews the final output. Lightweight if the plan was correct.
7. **Learning loop** — Update configs if needed, log metrics, refine routing.

### Phase Transitions
Each phase runs in a fresh context window. The output of each phase is a structured progress file in `memory/` that onboards the next phase. See the Orchestrator agent for the full protocol.

## Multi-Agent Collaboration Protocol

### Sub-Agents as Context Isolation

The primary value of sub-agents is **context isolation**, not persona specialization. When a parent agent dispatches a sub-agent to explore, search, or analyze, the sub-agent absorbs the context burden of reading files and tracing code flows. Only a concise, structured finding returns to the parent — keeping the parent's context clean and focused on the actual task.

**Design sub-agent calls for minimal context return**:
- Send the sub-agent a specific question ("Where is user authentication handled? Return file paths and line numbers.")
- The sub-agent reads 20 files; the parent receives 10 lines of structured findings
- The parent can get right to work without the context burden of exploration

Persona specialization (Software Engineer, Architect, etc.) provides behavioral guardrails and domain expertise, but context isolation is what makes multi-agent workflows scale.

### Multi-Agent Coordination

When a task requires multiple agents:
1. Orchestrator identifies multi-agent task and assigns the three-phase workflow
2. Load primary agent + sub-agents for the current phase only
3. Sub-agents explore and return concise findings (context isolation)
4. Primary agent coordinates (defines interfaces, manages dependencies, resolves conflicts)
5. Phase output is written to `memory/` as a progress file
6. Human reviews before next phase begins
7. Integration and validation (QA validates, Architect reviews if architectural changes)
8. Unified result delivery

## Model Routing

The orchestrator controls model selection for all agents. The full routing table is in `agents/orchestrator.md`. Summary:

| Model | Assigned to |
|-------|------------|
| `haiku` | naming-review, complexity-review, claude-setup-review, token-efficiency-review, performance-review |
| `sonnet` | test-review, structure-review, js-fp-review, concurrency-review, a11y-review, svelte-review, doc-review, orchestrator, qa-engineer, tech-writer, software-engineer (default) |
| `opus` | security-review, domain-review, arch-review, architect, software-engineer (architectural changes) |

Each agent's `model:` frontmatter is a fallback for direct invocation. When the orchestrator spawns agents via the Agent tool, it passes the model explicitly from the routing table.

## Multi-LLM Routing

| Criteria | Claude | Gemini |
|----------|--------|--------|
| Task complexity | Complex tasks | Simple, high-volume |
| Cost sensitivity | Premium | Cost-optimized |
| Context requirements | Large context needs | Standard context |
| Precision requirements | Critical components | Standard components |

## Context Management

Context management is the Orchestrator's responsibility, governed by two operational skills:

1. **[Context Loading Protocol](skills/context-loading-protocol.md)** - decides *what* to load and *when*, using task classification, phased loading, and measured token budgets
2. **[Context Summarization](skills/context-summarization.md)** - decides *when* to compress and *how*, using LSTM-inspired gates, utilization triggers, and structured summaries written to `memory/`

### Baseline Budget
- CLAUDE.md (always loaded): ~1,400 tokens
- Single team agent + single skill: ~600-1,100 tokens
- All team agents (no skills): ~3,590 tokens
- All review agents: ~2,800 tokens (spawned as sub-agents, not loaded in parent context)
- Full load (all team agents + all skills): ~14,200 tokens

### Operating Rules
1. **Load on demand**: Only load agent/skill files when their phase begins (see Loading Protocol)
2. **40% utilization ceiling**: Trigger summarization when proxy signals indicate 40%+ utilization
3. **Phase transitions**: Summarize completed phases to `memory/` before loading next-phase agents
4. **Summaries replace history**: New conversations read from `memory/`, not from prior conversation replay

## Feedback & Learning

Users can modify system behavior at any time using trigger keywords (`amend`, `learn`, `remember`, `forget`). The full procedure is defined in **[Feedback & Learning](skills/feedback-learning.md)**.

Changes are logged to `metrics/config-changelog.jsonl` with full audit trail and rollback support.

Non-obvious routing and architectural decisions are logged to `memory/decisions.md` by the Orchestrator during task execution. This log persists across session resets and gives subsequent phases visibility into prior reasoning.

## Human Oversight

Agents operate autonomously within defined boundaries. Human involvement is required for high-impact decisions (production deployments, architecture changes, scope modifications). The full protocol is defined in **[Human Oversight Protocol](skills/human-oversight-protocol.md)**.

Intervention commands: `amend`, `learn`, `remember`, `forget`, `override`, `pause`, `stop`.

## Quality & Accuracy

All agents apply self-validation before delivering output. The QA agent performs peer validation when applicable. See **[Accuracy Validation](skills/accuracy-validation.md)** for the checklist and confidence scoring system.

Audit logging, quality gates, and ethics principles are defined in **[Governance & Compliance](skills/governance-compliance.md)**.

A `PreToolUse` hook (`hooks/pre-tool-guard.sh`) blocks writes to sensitive paths (credentials, keys, secrets) before they execute. Protected path patterns are configurable via `hooks/guards.json`.

## Performance Metrics

Task completion data is logged to `metrics/` in JSONL format. See **[Performance Metrics](skills/performance-metrics.md)** for the schema and reporting cadence.

### Targets
- 10-15% overall efficiency gains
- 95% accuracy on structured data extraction
- < 5% hallucination rate with context management
- 95% accuracy maintained across full conversation lifecycle
- > 80% first-pass acceptance rate
