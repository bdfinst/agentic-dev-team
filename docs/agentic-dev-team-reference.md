---
title: "Agentic Dev Team Plugin — Reference Guide"
subtitle: "Roles, Agents, and Skills"
date: "2026-05-06"
---

# Agentic Dev Team Plugin

The **agentic-dev-team** plugin implements a fully automated software development team using persona-driven AI agents orchestrated through a three-phase workflow: **Research → Plan → Implement**. Each agent has defined responsibilities, collaboration protocols, and behavioral guidelines. Skills are reusable knowledge modules any agent can invoke.

---

# Team Agents

Team agents are persona-driven roles that implement, design, coordinate, and communicate. The Orchestrator routes every request to one or more team agents based on task classification.

## Orchestrator

**File:** `agents/orchestrator.md` | **Model:** Sonnet

The central dispatcher. Classifies every incoming request, selects and loads only the agents needed for the current phase, manages the three-phase workflow (Research → Plan → Implement), enforces the 40% context ceiling, and runs the inline review loop during implementation. Spans all phases; all other agents are loaded on demand.

**Key responsibilities:**

- Task routing and model assignment for all review agents
- Parallel plan review (four critic personas) before human gate
- Inline review loop: spec compliance → quality review → auto-fix (up to 5 iterations)
- Phase transition: writes structured progress files to `memory/` between phases

---

## Software Engineer

**File:** `agents/software-engineer.md` | **Model:** Sonnet (Opus for architectural changes)

Implements code following RED-GREEN-REFACTOR. Applies review corrections, writes vertical slices, and produces verification evidence (fresh test output) before claiming completion.

**Skills used:** Test-Driven Development, Systematic Debugging, Hexagonal Architecture, Domain-Driven Design, Legacy Code, Branch Workflow

---

## QA / SQA Engineer

**File:** `agents/qa-engineer.md` | **Model:** Sonnet

Owns acceptance test-driven development. Writes BDD scenarios before implementation begins, generates test infrastructure, validates behavior against acceptance criteria, and performs peer validation of other agents' output.

**Skills used:** Test-Driven Development, Feature File Validation, Mutation Testing, Test Design Reviewer, Browser Testing, Quality Gate Pipeline

---

## Architect

**File:** `agents/architect.md` | **Model:** Opus

Defines system structure, makes technology decisions, enforces architectural boundaries, and writes ADRs for significant decisions. Owns the research phase for non-trivial features and reviews plans for structural risk.

**Skills used:** Hexagonal Architecture, Domain-Driven Design, Domain Analysis, API Design, Threat Modeling, Design Doc, Design It Twice, Design Interrogation

---

## Product Manager

**File:** `agents/product-manager.md` | **Model:** Sonnet

Clarifies requirements, manages scope, produces user stories, and ensures the plan solves the right problem. Runs the Specs skill to produce BDD-aligned acceptance criteria before planning begins.

**Skills used:** Specs, Human Oversight Protocol, Competitive Analysis, Design Interrogation

---

## Security Engineer

**File:** `agents/security-engineer.md` | **Model:** Sonnet

Performs threat modeling, assesses attack surface, and provides secure design guidance. Runs STRIDE analysis for new APIs, authentication changes, and data flows crossing trust boundaries. Collaborates with Platform Engineer on infrastructure security.

**Skills used:** Threat Modeling, Quality Gate Pipeline, Governance & Compliance

---

## Platform Engineer

**File:** `agents/platform-engineer.md` | **Model:** Sonnet

Owns pipelines, deployment strategy, observability, and reliability planning. Provides self-service infrastructure capabilities to development teams. Advocates for safe, observable deployments and SLO-driven reliability.

**Key responsibilities:**

- Pipeline design and maintenance (build, test, deploy)
- Deployment strategies: blue-green, canary, rolling, feature flags
- Observability: metrics, logs, traces
- Reliability planning: SLOs, SLIs, error budgets
- Infrastructure-as-code and environment management

**Skills used:** Quality Gate Pipeline, Governance & Compliance, Docker Image Create, Docker Image Audit, Performance Benchmark, CI Debugging

---

## Technical Writer

**File:** `agents/tech-writer.md` | **Model:** Sonnet

Maintains documentation accuracy, enforces ubiquitous language, and ensures all affected docs are updated after implementation. Runs after every implementation phase to verify docs reflect the current state of the system.

**Skills used:** Agent & Skill Authoring, Governance & Compliance

---

## UI/UX Designer

**File:** `agents/ui-ux-designer.md` | **Model:** Sonnet

Defines interface patterns, UX flows, and accessibility requirements. Reviews UI changes for WCAG compliance and cognitive load. Participates in plan review as the UX Critic persona.

---

## ADR Author

**File:** `agents/adr-author.md` | **Model:** Sonnet

Creates and manages Architecture Decision Records. Applies a decision framework to determine when an ADR is needed, writes the record with context, decision, and consequences, and flags when existing ADRs need updating.

---

## Codebase Recon

**File:** `agents/codebase-recon.md` | **Model:** Sonnet

Read-only reconnaissance agent. Surveys a codebase's entry points, dependency graph, security surface, and git history. Produces a structured RECON artifact in `memory/` that other agents consume during the Research phase.

---

# Review Agents

Review agents run as sub-agents during Phase 3 inline checkpoints and full `/code-review` runs. They are spawned by the Orchestrator — never invoked directly. Model assignment follows the Orchestrator's routing table.

| Agent | Model | What It Checks |
|---|---|---|
| `spec-compliance-review` | Sonnet | Spec-to-code matching — first gate before quality review |
| `test-review` | Sonnet | Coverage gaps, assertion quality, test hygiene |
| `security-review` | Opus | Injection, auth/authz, data exposure, crypto |
| `domain-review` | Opus | Abstraction leaks, boundary violations, entity/DTO confusion |
| `arch-review` | Opus | ADR compliance, layer violations, dependency direction |
| `structure-review` | Sonnet | SRP violations, DRY, coupling, file organization |
| `concurrency-review` | Sonnet | Race conditions, async pitfalls, shared state safety |
| `js-fp-review` | Sonnet | Array/parameter mutations, impure patterns (JS/TS only) |
| `a11y-review` | Sonnet | WCAG 2.1 AA, ARIA, keyboard navigation, focus management |
| `svelte-review` | Sonnet | Svelte reactivity pitfalls, closure state leaks, `$state` proxy issues |
| `doc-review` | Sonnet | README staleness, API doc alignment, inline comment drift |
| `refactor-opportunity-review` | Sonnet | Post-GREEN refactoring opportunities (TDD REFACTOR phase) |
| `progress-guardian` | Sonnet | Plan adherence, commit discipline, scope creep detection |
| `data-flow-tracer` | Sonnet | Data flow tracing through architecture layers (analysis-only) |
| `complexity-review` | Haiku | Cyclomatic complexity, nesting depth, function size |
| `naming-review` | Haiku | Intent-revealing names, magic values, boolean prefixes |
| `performance-review` | Haiku | Resource leaks, N+1 queries, unbounded growth, timeouts |
| `token-efficiency-review` | Haiku | File size, LLM anti-patterns, token usage |
| `claude-setup-review` | Haiku | CLAUDE.md completeness and accuracy |

---

# Skills

Skills are reusable knowledge modules — patterns, guidelines, and procedures — that agents invoke on demand. They are agent-agnostic: any agent can reference any skill.

## Orchestration Skills

| Skill | Purpose |
|---|---|
| **Context Loading Protocol** | Selects which agent/skill files to load and when; enforces the 40% context ceiling |
| **Context Summarization** | Compresses conversation history at utilization thresholds; writes structured summaries to `memory/` |
| **Feedback & Learning** | Processes `amend`/`learn`/`remember`/`forget` keywords; updates configs with full audit trail |
| **Human Oversight Protocol** | Approval gates, intervention commands (`override`, `pause`, `stop`), escalation rules |
| **Performance Metrics** | Task completion logging schema: tokens, cost, agents used, rework cycles, hallucination events |
| **Agent & Skill Authoring** | Guidelines for creating and maintaining agent and skill files |
| **Specs** | Collaborative workflow producing four artifacts (Intent, BDD scenarios, Architecture notes, Acceptance Criteria) before implementation |

## Quality Skills

| Skill | Purpose |
|---|---|
| **Quality Gate Pipeline** | Unified three-phase gate: self-validation → verification evidence → review-correction loop |
| **Governance & Compliance** | Audit logging, quality assurance layers, ethics principles, compliance escalation |
| **Static Analysis Integration** | SARIF-first pre-pass for `/code-review`: runs available static analysis tools, normalizes to unified finding envelope, deduplicates across tools |

## Development Discipline Skills

| Skill | Purpose |
|---|---|
| **Test-Driven Development** | Enforces RED-GREEN-REFACTOR with hard gates; prevents implementation-first failure mode |
| **Systematic Debugging** | Four-phase protocol: reproduce → investigate → root-cause → fix; prevents guess-and-fix thrashing |
| **Legacy Code** | Characterization tests and dependency-breaking techniques for untested code |
| **Branch Workflow** | PR creation, merge strategy, and branch cleanup after Phase 3 |
| **CI Debugging** | Hypothesis-first CI failure diagnosis; environment delta analysis; anti-patterns |
| **Test Design Reviewer** | Scores test suites using Dave Farley's 8 properties (Farley Score) |
| **Browser Testing** | Playwright patterns: navigation, form interaction, screenshots, visual verification |
| **Feature File Validation** | Gherkin quality, determinism, implementation independence, test automation coverage |
| **Mutation Testing** | Run Stryker/pitest/mutmut and triage surviving mutants; AI classifies survivors |

## Research & Design Skills

| Skill | Purpose |
|---|---|
| **Domain Analysis** | Strategic DDD health assessment: bounded contexts, context map, event flows, friction report |
| **Design Doc** | Written design document with alternatives analysis; requires user approval before planning |
| **Design Interrogation** | Relentless interview to surface hidden assumptions, unresolved decisions, and edge cases |
| **Design It Twice** | Generates multiple radically different interface designs via parallel sub-agents for comparison |
| **Competitive Analysis** | Gap analysis against external tools, plugins, or feature sets |

## Technical Skills

| Skill | Purpose |
|---|---|
| **Hexagonal Architecture** | Ports-and-adapters pattern: separates domain from infrastructure, enforces dependency rule |
| **Domain-Driven Design** | Bounded contexts, aggregates, value objects, domain events, ubiquitous language |
| **API Design** | Contract-first design: versioning, REST conventions, backward compatibility, error contracts |
| **Threat Modeling** | STRIDE analysis: trust boundaries, attack surface, mitigations |
| **Docker Image Create** | Generates production-ready multi-stage Dockerfiles with minimal/distroless base images |
| **Docker Image Audit** | Audits Dockerfiles and images with hadolint, Trivy, Grype; structured severity report |
| **Performance Benchmark** | Captures Core Web Vitals, resource sizes, load times; compares against baselines and budgets |
| **JS Project Init** | Scaffolds a JavaScript project with ESM, functional style, prettier, eslint, vitest, gitignore |

---

# Slash Commands

All user-invocable workflows. Executed under Orchestrator direction unless otherwise noted.

## Review Commands

| Command | Purpose |
|---|---|
| `/code-review` | Run all review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations) |
| `/review` | Alias for `/code-review` |
| `/review-agent <name>` | Run a single named review agent (used for targeted or inline review) |
| `/apply-fixes` | Apply correction prompts generated by `/code-review` |
| `/review-summary` | Generate a compact session summary for cross-session context continuity |
| `/semgrep-analyze` | Run Semgrep SAST and return structured findings |

## Workflow Commands

| Command | Purpose |
|---|---|
| `/plan` | Create a structured implementation plan with TDD steps and acceptance criteria |
| `/build` | Execute an approved plan with TDD, inline reviews, and verification evidence |
| `/pr` | Run quality gates and create a pull request with structured summary |
| `/setup` | Detect tech stack, generate project-level CLAUDE.md, hooks, and agent templates |
| `/continue` | Resume work from a prior session using phase progress files in `memory/` |
| `/triage` | Investigate a bug, find root cause, file a GitHub issue with TDD fix plan |
| `/issues-from-plan` | Break a plan into independently-grabbable GitHub issues |
| `/domain-analysis` | Assess DDD health: bounded contexts, context map, friction report |
| `/browse` | Browser-based QA via Playwright: navigate, screenshot, click, fill forms |
| `/benchmark` | Capture runtime performance metrics and compare against baselines |
| `/competitive-analysis` | Compare plugin against other tools to find gaps and weaknesses |
| `/init-dev-team` | Install plugin prerequisites (jq, python3, mutation tools); state-aware CodeGraph offer; JS bootstrap via `js-project-init` when `package.json` is missing |

## Safety Commands

| Command | Purpose |
|---|---|
| `/careful` | Toggle destructive command blocking (`rm -rf`, force-push, `DROP TABLE`) |
| `/freeze <glob>` | Scope-lock editing to a glob pattern |
| `/unfreeze` | Lift the scope lock set by `/freeze` |
| `/guard <glob>` | Combined `/careful` + `/freeze` for production-critical sessions |

## Scaffolding Commands

| Command | Purpose |
|---|---|
| `/agent-add` | Scaffold a new review agent with eval compliance check and doc updates |
| `/agent-remove` | Remove an agent and all its registry entries and doc references |
| `/agent-audit` | Audit agents and commands for structural compliance |
| `/agent-eval` | Run eval fixtures, grade review agent accuracy, detect regressions |
| `/harness-audit` | Analyze harness effectiveness and flag stale components |
| `/add-plugin` | Install a plugin and register it in `settings.json` |

## Team Agent Commands

Each team agent is also a user-invocable command that adopts the agent's persona.

| Command | Purpose |
|---|---|
| `/orchestrator` | Routes tasks and coordinates multi-agent collaboration |
| `/architect` | System design, architecture definition, technical decisions |
| `/software-engineer` | Full-stack development, implementation, refactoring |
| `/qa-engineer` | ATDD test generation, quality metrics, regression testing |
| `/security-engineer` | Threat modeling, security analysis, vulnerability assessment |
| `/platform-engineer` | Pipeline design, deployment strategy, observability, reliability |
| `/ui-ux-designer` | UI patterns, UX optimization, accessibility compliance |
| `/product-manager` | Feature scoping, prioritization, stakeholder alignment |
| `/tech-writer` | Documentation, terminology consistency, style enforcement |

## Skill Commands

Each skill is also directly invocable as a slash command.

| Command | Purpose |
|---|---|
| `/specs` | Collaborative spec workflow: Intent, BDD scenarios, Architecture notes, Acceptance Criteria |
| `/threat-modeling` | STRIDE analysis for new APIs, auth changes, or data flows |
| `/hexagonal-architecture` | Ports-and-adapters design guidance |
| `/domain-driven-design` | Bounded contexts, aggregates, context mapping |
| `/api-design` | Contract-first API design, versioning, REST conventions |
| `/legacy-code` | Characterization tests and safe refactoring in untested code |
| `/mutation-testing` | Run mutation tool and triage surviving mutants |
| `/governance-compliance` | Audit logging, quality gates, ethics escalation |
| `/feedback-learning` | Process `amend`/`learn`/`remember`/`forget` keywords |
| `/context-loading-protocol` | Select minimum viable context load for a task |
| `/context-summarization` | Compress conversation history at utilization threshold |
| `/performance-metrics` | Log task completion data |
| `/quality-gate-pipeline` | Run self-validation, verification evidence, and review-correction loop |
| `/human-oversight-protocol` | Invoke approval gates, respond to intervention commands |
| `/agent-skill-authoring` | Guidance for creating and maintaining agent and skill files |

## Utility Commands

| Command | Purpose |
|---|---|
| `/help` | List all available slash commands with descriptions |
| `/version` | Report the installed plugin version |
| `/upgrade` | Check for and apply plugin updates |
