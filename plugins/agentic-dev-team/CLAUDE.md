# Agentic Scrum Team - Orchestration Pipeline

## System Overview

This project implements a fully automated development team using persona-driven AI agents orchestrated through an intelligent coordination pipeline. The Orchestrator agent acts as the central dispatcher, routing tasks to specialized agents based on task classification, complexity, and required expertise.

## Architecture

This project uses a layered loading strategy to minimize token usage:

- **CLAUDE.md**: Core philosophy + quick reference (always loaded, ~800 tokens)
- **Skills**: Detailed patterns and procedures (loaded on-demand when a phase or task requires them)
- **Knowledge**: Reference data — registries, rubrics, detection patterns (loaded on-demand by agents)
- **Agents**: Behavioral specifications (loaded per-phase, never all at once)
- **Templates**: Language-specific agent templates (scaffolded per-project by `/setup`)

## Output Guardrails

1. **Write to files, not chat.** Artifacts (plans, design docs, reports, code) go to files. Chat is for decisions, status updates, and questions — not deliverables.
2. **Plan-only mode.** When asked for a plan, produce ONLY the plan. Do not start implementing. The plan is a gate, not a warm-up.
3. **Incremental output.** Produce a first draft within 3-4 tool calls, then refine iteratively. Don't spend 20 tool calls exploring before writing anything.

## Core Principles

1. **Selective Agent Loading**: Only load necessary agents into context, avoiding token bloat. Target < 10,000 tokens for simple tasks.
2. **40% Context Window Rule**: Maintain context below 40% capacity to prevent hallucination. Trigger summarization at threshold.
3. **Persona-Driven Behavior**: Each agent has detailed psychological and behavioral specifications defined in `.claude/agents/`.
4. **Human-in-the-Loop**: Agents are autonomous but require oversight, not copilots.
5. **Dynamic Configuration**: User-level configuration updates through federated learning.
6. **Acceptance Test Driven Development**: All development follows ATDD. Behaviors are defined as scenarios in feature files (Gherkin) before implementation begins. Feature file scenarios are the single source of truth for expected behavior — no implementation without a corresponding scenario, no scenario without a corresponding test.

## Team Organization

See @docs/team-structure.md for the full team org chart (Mermaid diagram).

## Agent & Skill Registry

Full registry tables with token counts, model tiers, and used-by mappings are in [`knowledge/agent-registry.md`](knowledge/agent-registry.md). The orchestrator reads this file when routing decisions require the full catalog.

### Quick Reference

**Team agents** (11): Orchestrator, Software Engineer, Data Scientist, QA Engineer, UI/UX Designer, Architect, Product Manager, Technical Writer, Security Engineer, DevOps/SRE Engineer, ADR Author (~3,900 tokens total)

**Review agents** (19): spec-compliance-review, a11y-review, arch-review, claude-setup-review, complexity-review, concurrency-review, doc-review, domain-review, js-fp-review, naming-review, performance-review, security-review, structure-review, svelte-review, test-review, token-efficiency-review, refactoring-review, progress-guardian, data-flow-tracer

**Skills** (31): Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Quality Gate Pipeline, Governance & Compliance, Agent & Skill Authoring, Hexagonal Architecture, Domain-Driven Design, Domain Analysis, Specs, Threat Modeling, API Design, Legacy Code, Mutation Testing, Test-Driven Development, Systematic Debugging, Design Doc, Branch Workflow, CI Debugging, Test Design Reviewer, Browser Testing, Competitive Analysis, Design Interrogation, Design It Twice, Static Analysis Integration, Feature File Validation, Docker Image Create, Docker Image Audit, Performance Benchmark

**Subagent prompt templates** (8): `prompts/implementer.md`, `prompts/spec-reviewer.md`, `prompts/quality-reviewer.md`, `prompts/plan-reviewer.md`, `prompts/plan-review-acceptance.md`, `prompts/plan-review-design.md`, `prompts/plan-review-ux.md`, `prompts/plan-review-strategic.md`

**Knowledge files** (6): agent-registry, review-template, review-rubric, owasp-detection, domain-modeling, architecture-assessment

**Agent templates** (9): ts-enforcer, esm-enforcer, react-testing, front-end-testing, twelve-factor-audit, python-quality, go-quality, csharp-quality, angular-testing (in `templates/agents/`, scaffolded by `/setup`)

### Institutional Context

Teams can create a `REVIEW-CONTEXT.md` file in their project root to provide domain knowledge that code analysis alone cannot discover: related services, known issues, team context, architectural history. When present, `/code-review` reads it and passes the contents to each agent as additional context. This file is optional and project-local.

## Slash Commands Registry

User-invocable workflows in `.claude/commands/`. All review commands are executed under orchestrator direction. The orchestrator's **Model Routing Table** (`agents/orchestrator.md`) determines model assignment for all review agents.

| Command | File | Role | What It Does |
|---------|------|------|--------------|
| `/code-review` | `commands/code-review.md` | orchestrator | Run review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations) |
| `/review-agent` | `commands/review-agent.md` | worker | Run a single review agent (used for inline checkpoints) |
| `/agent-audit` | `commands/agent-audit.md` | orchestrator | Audit agents/commands/hooks for structural compliance |
| `/agent-eval` | `commands/agent-eval.md` | orchestrator | Run eval fixtures, grade accuracy, detect regressions |
| `/agent-add` | `commands/agent-add.md` | implementation | Scaffold a new review agent with eval compliance and doc updates |
| `/agent-remove` | `commands/agent-remove.md` | implementation | Remove an agent and all its registry entries and doc references |
| `/add-plugin` | `commands/add-plugin.md` | implementation | Install a plugin and register it in settings.json |
| `/apply-fixes` | `commands/apply-fixes.md` | implementation | Apply correction prompts from `/code-review` output |
| `/review-summary` | `commands/review-summary.md` | orchestrator | Generate compact session summary for context continuity |
| `/semgrep-analyze` | `commands/semgrep-analyze.md` | worker | Run Semgrep SAST and return structured findings |
| `/review` | `commands/review.md` | orchestrator | Alias for `/code-review` — same arguments, same behavior |
| `/domain-analysis` | `commands/domain-analysis.md` | worker | Assess existing system DDD health: bounded contexts, context map, event storm, value stream, friction report |
| `/setup` | `commands/setup.md` | orchestrator | Detect tech stack, generate project-level config, hooks, and agent templates |
| `/continue` | `commands/continue.md` | orchestrator | Resume work from a prior session using phase progress files |
| `/plan` | `commands/plan.md` | orchestrator | Create a structured implementation plan with TDD steps |
| `/build` | `commands/build.md` | orchestrator | Execute an approved plan with TDD, inline reviews, and verification evidence |
| `/pr` | `commands/pr.md` | orchestrator | Run quality gates and create a pull request |
| `/browse` | `commands/browse.md` | worker | Browser-based QA: navigate, screenshot, click, fill forms via Playwright |
| `/careful` | `commands/careful.md` | worker | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE, etc.) |
| `/freeze` | `commands/freeze.md` | worker | Scope-lock editing to a glob pattern; blocks edits outside the pattern |
| `/unfreeze` | `commands/unfreeze.md` | worker | Lift the scope lock set by `/freeze` |
| `/guard` | `commands/guard.md` | worker | Combined `/careful` + `/freeze` for production-critical sessions |
| `/upgrade` | `commands/upgrade.md` | worker | Check for and apply plugin updates from within a session |
| `/competitive-analysis` | `commands/competitive-analysis.md` | orchestrator | Compare plugin against others to find gaps and weaknesses |
| `/triage` | `commands/triage.md` | worker | Investigate a bug and file a GitHub issue with TDD fix plan |
| `/issues-from-plan` | `commands/issues-from-plan.md` | orchestrator | Break a plan into independently-grabbable GitHub issues |
| `/harness-audit` | `commands/harness-audit.md` | orchestrator | Analyze harness effectiveness and flag stale components |
| `/version` | `commands/version.md` | worker | Report the installed plugin version |
| `/benchmark` | `commands/benchmark.md` | worker | Capture runtime performance metrics (Core Web Vitals, resource sizes) and compare against baselines |
| `/help` | `commands/help.md` | worker | List all available slash commands with descriptions |

## Request Processing Flow

For trivial tasks (typo fix, simple query), the Orchestrator routes directly to a single agent. For non-trivial tasks, the Orchestrator follows the **Research → Plan → Implement** workflow:

### Three-Phase Workflow
1. **Research** — Understand the system: find relevant files, trace data flows, identify the problem surface area. Sub-agents explore the codebase and return concise findings to keep the parent context clean. For non-trivial features, produce a **design document** at `docs/specs/` with problem statement, approach, alternatives, and scope boundaries. Optionally run **Design Interrogation** to stress-test the design and surface unresolved decisions before planning. For module boundaries, use **Design It Twice** to generate parallel alternative interfaces via sub-agents. Output: research progress file + design doc written to `memory/`.
2. **Human Review Gate** — Human reviews research findings and design doc. Catching a misunderstanding here prevents hundreds of bad lines of code.
3. **Plan** — Specify every change: files, snippets, test strategy, verification steps. Before the human sees the plan, **four plan review personas** run in parallel as critical outside reviewers: Acceptance Test Critic (criteria quality, scenario gaps), Design & Architecture Critic (coupling, structural risks), UX Critic (user journey, accessibility), and Strategic Critic (scope, risk, opportunity cost). Any blocker findings are addressed before the human gate. The plan is the primary review artifact — 200 lines of plan is far more reviewable than 2,000 lines of code. After approval, optionally run `/issues-from-plan` to create GitHub issues for team distribution. Output: implementation plan progress file written to `memory/`.
4. **Human Review Gate** — Human reviews the plan. This replaces traditional line-by-line code review as the primary quality gate.
5. **Implement** — Execute the plan using the `prompts/implementer.md` template. All code follows **RED-GREEN-REFACTOR** with **vertical slices** (TDD skill). For parallel independent units, use **worktree isolation** (`isolation: "worktree"`). After each unit, a **three-stage inline review** runs: (1) spec-compliance-review checks code matches spec, (2) quality review agents check code quality, (3) browser verification for UI changes. Actionable issues (error/warning severity with high/medium confidence) are **auto-fixed and re-reviewed** in a loop (up to 5 iterations) — only issues requiring human judgment are escalated. Run `/code-review` before committing (which auto-scopes to uncommitted changes and runs its own fix loop). Then invoke the tech-writer to verify all affected documentation is current. All agents must provide **verification evidence** (fresh test output) before claiming completion. Output: working code + test results + code review pass + docs verified.
6. **Human Review Gate** — Human reviews the final output. Lightweight if the plan was correct.
7. **Branch Workflow** — Create PR, choose merge strategy, clean up branch (see Branch Workflow skill).
8. **Learning loop** — Update configs if needed, log metrics, refine routing.

### Skills by Phase

| Phase | Skills Used | Purpose |
|-------|-----------|---------|
| **Research** | Design Doc, Domain Analysis, Domain-Driven Design, Threat Modeling, Design Interrogation, Design It Twice, Competitive Analysis | Understand the system, explore alternatives, stress-test designs |
| **Plan** | Specs, API Design, Hexagonal Architecture, Legacy Code | Define what to build, specify interfaces and test strategy |
| **Plan → Team** | `/issues-from-plan` | Break plan into GitHub issues for team distribution |
| **Implement** | Test-Driven Development, Systematic Debugging, Mutation Testing, Browser Testing, Performance Benchmark, CI Debugging | Build with TDD, debug issues, validate quality, measure performance |
| **Bug Triage** | `/triage` (Systematic Debugging + GitHub issue creation) | Investigate bugs and file actionable issues |
| **Review** | Quality Gate Pipeline, Test Design Reviewer | Validate output before delivery |
| **Cross-phase** | Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Governance & Compliance, Branch Workflow, Agent & Skill Authoring | Orchestration, context management, learning |

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
| `sonnet` | spec-compliance-review, test-review, structure-review, js-fp-review, concurrency-review, a11y-review, svelte-review, doc-review, refactoring-review, progress-guardian, data-flow-tracer, orchestrator, qa-engineer, tech-writer, software-engineer (default) |
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

1. **[Context Loading Protocol](skills/context-loading-protocol/SKILL.md)** - decides *what* to load and *when*, using task classification, phased loading, and measured token budgets
2. **[Context Summarization](skills/context-summarization/SKILL.md)** - decides *when* to compress and *how*, using LSTM-inspired gates, utilization triggers, and structured summaries written to `memory/`

### Baseline Budget
- CLAUDE.md (always loaded): ~800 tokens (reduced by moving registries to `knowledge/agent-registry.md`)
- Single team agent + single skill: ~600-1,100 tokens
- All team agents (no skills): ~3,590 tokens
- All review agents: ~3,100 tokens (spawned as sub-agents, not loaded in parent context; includes spec-compliance-review)
- Knowledge files: ~3,450 tokens total (loaded on demand by agents, not in parent context; includes agent-registry)
- Subagent prompt templates: ~1,800 tokens total (loaded by orchestrator when dispatching; includes 4 plan review personas)
- Full load (all team agents + all skills): ~18,100 tokens

### Operating Rules
1. **Load on demand**: Only load agent/skill files when their phase begins (see Loading Protocol)
2. **40% utilization ceiling**: Trigger summarization when proxy signals indicate 40%+ utilization
3. **Phase transitions**: Summarize completed phases to `memory/` before loading next-phase agents
4. **Summaries replace history**: New conversations read from `memory/`, not from prior conversation replay

## Feedback & Learning

Users can modify system behavior at any time using trigger keywords (`amend`, `learn`, `remember`, `forget`). The full procedure is defined in **[Feedback & Learning](skills/feedback-learning/SKILL.md)**.

Changes are logged to `metrics/config-changelog.jsonl` with full audit trail and rollback support.

Non-obvious routing and architectural decisions are logged to `memory/decisions.md` by the Orchestrator during task execution. This log persists across session resets and gives subsequent phases visibility into prior reasoning.

## Human Oversight

Agents operate autonomously within defined boundaries. Human involvement is required for high-impact decisions (production deployments, architecture changes, scope modifications). The full protocol is defined in **[Human Oversight Protocol](skills/human-oversight-protocol/SKILL.md)**.

Intervention commands: `amend`, `learn`, `remember`, `forget`, `override`, `pause`, `stop`.

## Quality & Accuracy

All agents apply the **[Quality Gate Pipeline](skills/quality-gate-pipeline/SKILL.md)** before delivering output: self-validation (Phase 1), verification evidence (Phase 2), and review-correction loops (Phase 3). The QA agent performs peer validation when applicable.

Audit logging, quality gates, and ethics principles are defined in **[Governance & Compliance](skills/governance-compliance/SKILL.md)**.

A `PreToolUse` hook (`hooks/pre-tool-guard.sh`) blocks writes to sensitive paths (credentials, keys, secrets) before they execute. Protected path patterns are configurable via `hooks/guards.json`. A second `PreToolUse` hook (`hooks/destructive-guard.sh`) detects destructive Bash commands (rm -rf, force-push, DROP TABLE, etc.) and warns by default. Use `/careful` to escalate warnings to blocks, `/freeze` to scope-lock edits, or `/guard` for both.

## Performance Metrics

Task completion data is logged to `metrics/` in JSONL format. See **[Performance Metrics](skills/performance-metrics/SKILL.md)** for the schema and reporting cadence.

### Targets
- 10-15% overall efficiency gains
- 95% accuracy on structured data extraction
- < 5% hallucination rate with context management
- 95% accuracy maintained across full conversation lifecycle
- > 80% first-pass acceptance rate
