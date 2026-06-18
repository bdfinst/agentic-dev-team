# Skills

Skills are the unified reusable capability layer in this system. All skills live in `skills/<name>/SKILL.md` and fall into two sub-types differentiated by frontmatter:

- **Agent-loaded skills** — knowledge modules that agents read for domain expertise (patterns, guidelines, procedures). Agent-agnostic; any agent can reference them.
- **User-invocable skills** (`user-invocable: true`) — user-invocable workflows with numbered steps, argument parsing, and structured output. Executed under Orchestrator direction as slash commands (e.g., `/code-review`).

## Skills Catalog

### Orchestration Skills

Used by the Orchestrator to manage the team:

| Skill | File | Purpose |
| --- | --- | --- |
| Context Loading Protocol | [`context-loading-protocol.md`](../skills/context-loading-protocol/SKILL.md) | Decides which agent/skill files to load and when |
| Context Summarization | [`context-summarization.md`](../skills/context-summarization/SKILL.md) | Compresses conversation history at utilization thresholds |
| Feedback & Learning | [`feedback-learning.md`](../skills/feedback-learning/SKILL.md) | Processes feedback keywords, audit trail, rollback |
| Human Oversight Protocol | [`human-oversight-protocol.md`](../skills/human-oversight-protocol/SKILL.md) | Approval gates, intervention commands, escalation |
| Performance Metrics | [`performance-metrics.md`](../skills/performance-metrics/SKILL.md) | Task logging schema and reporting procedures |
| Agent & Skill Authoring | [`agent-skill-authoring.md`](../skills/agent-skill-authoring/SKILL.md) | Skill-authoring conventions, anti-patterns, and the agent-vs-skill philosophy (for creating new agents, use the `agent-create` skill via `/agent-add`) |
| Specs | [`specs.md`](../skills/specs/SKILL.md) | Intent, architecture, and acceptance-criteria consistency gate before planning (Gherkin is authored per slice in `/plan`) |

### Quality Skills

Used by all agents to ensure output correctness:

| Skill | File | Purpose |
| --- | --- | --- |
| Quality Gate Pipeline | [`quality-gate-pipeline.md`](../skills/quality-gate-pipeline/SKILL.md) | Unified quality gate: self-validation, verification evidence, review-correction loops |
| Governance & Compliance | [`governance-compliance.md`](../skills/governance-compliance/SKILL.md) | Audit trail, quality assurance layers, ethics principles |
| Static Analysis Integration | [`static-analysis-integration/SKILL.md`](../skills/static-analysis-integration/SKILL.md) | SARIF-first pre-pass for `/code-review`: runs available static analysis tools, normalizes to unified finding envelope, deduplicates across tools |

### Development Discipline Skills

Enforce rigorous development practices:

| Skill | File | Purpose |
| --- | --- | --- |
| Test-Driven Development | [`test-driven-development.md`](../skills/test-driven-development/SKILL.md) | RED-GREEN-REFACTOR cycle with hard gates, rationalization prevention |
| Systematic Debugging | [`systematic-debugging.md`](../skills/systematic-debugging/SKILL.md) | 4-phase debugging protocol (reproduce, investigate, root-cause, fix) |
| Design Doc | [`design-doc.md`](../skills/design-doc/SKILL.md) | Written design document with alternatives analysis before planning |
| Branch Workflow | [`branch-workflow.md`](../skills/branch-workflow/SKILL.md) | PR creation, merge strategy, and branch cleanup after Phase 3 |
| CI Debugging | [`ci-debugging.md`](../skills/ci-debugging/SKILL.md) | CI pipeline failure investigation and resolution |
| Test Design Reviewer | [`test-design-reviewer.md`](../skills/test-design-reviewer/SKILL.md) | Test quality patterns and anti-patterns |
| Test Design Advisor | [`test-design-advisor.md`](../skills/test-design-advisor/SKILL.md) | Advise on testability, pyramid layer, double strategy, and behavior-preserving refactor sequences |
| CD Test Architecture | [`cd-test-architecture.md`](../skills/cd-test-architecture/SKILL.md) | Evaluate an app's tests and recommend a CD-aligned architecture: deterministic, config-free CI gate with UI/service/batch patterns |
| Browser Testing | [`browser-testing.md`](../skills/browser-testing/SKILL.md) | Playwright-based browser QA for visual verification |
| Feature File Validation | [`feature-file-validation.md`](../skills/feature-file-validation/SKILL.md) | Gherkin quality, determinism, implementation independence, test automation coverage |

> For the full test evaluation workflow — how Test Design Advisor, CD Test Architecture, `/test-design`, and `test-smell-review` relate, the out-of-repo anti-pattern, and sample invocations — see [Test Evaluation and Architecture](test-evaluation.md).

### Research & Design Skills

Used during the Research phase to explore alternatives and stress-test designs:

| Skill | File | Purpose |
| --- | --- | --- |
| Domain Analysis | [`domain-analysis/SKILL.md`](../skills/domain-analysis/SKILL.md) | Strategic DDD health assessment of an existing system: bounded contexts, context map, event flows, friction report |
| Competitive Analysis | [`competitive-analysis.md`](../skills/competitive-analysis/SKILL.md) | Gap analysis against external tools, plugins, or feature sets |
| Design Interrogation | [`design-interrogation.md`](../skills/design-interrogation/SKILL.md) | Stress-test design decisions before planning |
| Design It Twice | [`design-it-twice.md`](../skills/design-it-twice/SKILL.md) | Generate parallel alternative interfaces via sub-agents |

### Technical Skills

Domain knowledge for implementation work:

| Skill | File | Purpose |
| --- | --- | --- |
| Hexagonal Architecture | [`hexagonal-architecture.md`](../skills/hexagonal-architecture/SKILL.md) | Ports & adapters pattern, dependency rule, project structure |
| Domain-Driven Design | [`domain-driven-design.md`](../skills/domain-driven-design/SKILL.md) | Bounded contexts, aggregates, domain events, ubiquitous language |
| API Design | [`api-design.md`](../skills/api-design/SKILL.md) | Contract-first design, versioning, REST conventions |
| Threat Modeling | [`threat-modeling.md`](../skills/threat-modeling/SKILL.md) | STRIDE analysis, trust boundaries, mitigation strategies |
| Legacy Code | [`legacy-code.md`](../skills/legacy-code/SKILL.md) | Characterization testing, safe refactoring in untested code |
| Mutation Testing | [`mutation-testing.md`](../skills/mutation-testing/SKILL.md) | Evaluating test suite effectiveness against behavioral mutations |
| Docker Image Create | [`docker-image-create/SKILL.md`](../skills/docker-image-create/SKILL.md) | Generate production Dockerfiles with multi-stage builds, slim/distroless bases |
| Docker Image Audit | [`docker-image-audit/SKILL.md`](../skills/docker-image-audit/SKILL.md) | Audit Dockerfiles and images with hadolint, Trivy, Grype; structured severity report |
| Performance Benchmark | [`performance-benchmark/SKILL.md`](../skills/performance-benchmark/SKILL.md) | Runtime performance measurement: Core Web Vitals, resource sizes, baseline comparison, performance budgets, trend tracking |
| JS Project Init | [`js-project-init/SKILL.md`](../skills/js-project-init/SKILL.md) | Scaffold a JavaScript project with ESM, functional style, prettier, eslint, editorconfig, vitest, and gitignore |

### Subagent Prompt Templates

Concrete templates in `prompts/` for reproducible subagent dispatch:

| Template | File | Purpose |
| --- | --- | --- |
| Implementer | [`implementer.md`](../prompts/implementer.md) | Phase 3 implementation dispatch with TDD enforcement |
| Spec Reviewer | [`spec-reviewer.md`](../prompts/spec-reviewer.md) | Two-stage review gate 1: does code match spec? |
| Quality Reviewer | [`quality-reviewer.md`](../prompts/quality-reviewer.md) | Two-stage review gate 2: is code high quality? |
| Plan Reviewer | [`plan-reviewer.md`](../prompts/plan-reviewer.md) | Phase 2 automated pre-check before human review |
| Plan Review — Acceptance | [`plan-review-acceptance.md`](../prompts/plan-review-acceptance.md) | Criteria verifiability, scenario completeness, error paths, TDD traceability |
| Plan Review — Design | [`plan-review-design.md`](../prompts/plan-review-design.md) | Coupling, abstraction quality, structural risks, pattern consistency |
| Plan Review — UX | [`plan-review-ux.md`](../prompts/plan-review-ux.md) | User journey, error experience, cognitive load, accessibility |
| Plan Review — Strategic | [`plan-review-strategic.md`](../prompts/plan-review-strategic.md) | Problem-solution fit, scope, risk, opportunity cost |
| Plan Review — Parallelization | [`plan-review-parallelization.md`](../prompts/plan-review-parallelization.md) | Same-wave independence: file-overlap collisions, disjoint-file behavioral coupling, residual cycles |

## User-Invocable Skills Catalog

User-invocable skills are invoked as slash commands (e.g., `/code-review`) and executed under Orchestrator direction. Each review agent declares a tier alias in its `model:` frontmatter; the PreToolUse hook `hooks/agent-model-resolve.sh` resolves it to the active snapshot per the Resolution Procedure in `agents/orchestrator.md`.

### Review Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/code-review` | [`code-review/SKILL.md`](../skills/code-review/SKILL.md) | Run all review agents, auto-fix actionable issues, and re-run until clean (up to 5 iterations) |
| `/review-agent <name>` | [`review-agent/SKILL.md`](../skills/review-agent/SKILL.md) | Run a single named review agent; used for inline Phase 3 checkpoints |
| `/apply-fixes` | [`apply-fixes/SKILL.md`](../skills/apply-fixes/SKILL.md) | Apply correction prompts generated by `/code-review` |
| `/review-summary` | [`review-summary/SKILL.md`](../skills/review-summary/SKILL.md) | Generate a compact session summary for cross-session context continuity |
| `/semgrep-analyze` | [`semgrep-analyze/SKILL.md`](../skills/semgrep-analyze/SKILL.md) | Run Semgrep static analysis and return structured findings |

### Eval Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-audit` | [`agent-audit/SKILL.md`](../skills/agent-audit/SKILL.md) | Audit agents and skills for structural compliance |
| `/agent-eval` | [`agent-eval/SKILL.md`](../skills/agent-eval/SKILL.md) | Run eval fixtures, grade review agent accuracy, detect regressions |
| `/harness-audit` | [`harness-audit/SKILL.md`](../skills/harness-audit/SKILL.md) | Analyze harness effectiveness, flag stale components |

### Scaffolding Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-add` | [`agent-add/SKILL.md`](../skills/agent-add/SKILL.md) | Scaffold a new review agent with eval compliance check and doc updates |
| `/agent-remove` | [`agent-remove/SKILL.md`](../skills/agent-remove/SKILL.md) | Remove an agent and all its registry entries and doc references |
| `/add-plugin` | [`add-plugin/SKILL.md`](../skills/add-plugin/SKILL.md) | Install a plugin and register it in `settings.json` |

### Workflow Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/plan` | [`plan/SKILL.md`](../skills/plan/SKILL.md) | Decompose a feature into vertical slices — each with its Gherkin scenarios and TDD steps |
| `/build` | [`build/SKILL.md`](../skills/build/SKILL.md) | Execute an approved plan with TDD, inline reviews, and verification evidence |
| `/pr` | [`pr/SKILL.md`](../skills/pr/SKILL.md) | Run quality gates and create a pull request (enables auto-merge by default) |
| `/ship` | [`ship/SKILL.md`](../skills/ship/SKILL.md) | Run the full spec→plan→build→review→PR pipeline as one command, pausing at the human gates |
| `/setup` | [`setup/SKILL.md`](../skills/setup/SKILL.md) | Detect tech stack, generate project-level config and hooks |
| `/init-dev-team` | [`init-dev-team/SKILL.md`](../skills/init-dev-team/SKILL.md) | Install plugin prerequisites (jq, python3, mutation tools), offer CodeGraph, and optionally probe Anthropic model availability for restricted endpoints |
| `/continue` | [`continue/SKILL.md`](../skills/continue/SKILL.md) | Resume work from a prior session using phase progress files |
| `/browse` | [`browse/SKILL.md`](../skills/browse/SKILL.md) | Browser-based QA via Playwright: navigate, screenshot, click, fill forms |
| `/triage` | [`triage/SKILL.md`](../skills/triage/SKILL.md) | Investigate a bug, find root cause, write a triage record to `.triage/<slug>.md` with a TDD fix plan |
| `/issues-from-plan` | [`issues-from-plan/SKILL.md`](../skills/issues-from-plan/SKILL.md) | Break a plan into independently-grabbable GitHub issues |
| `/benchmark` | [`benchmark/SKILL.md`](../skills/benchmark/SKILL.md) | Capture runtime performance metrics (Core Web Vitals, resource sizes) and compare against baselines |

### Safety Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/careful` | [`careful/SKILL.md`](../skills/careful/SKILL.md) | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE) |
| `/freeze <glob>` | [`freeze/SKILL.md`](../skills/freeze/SKILL.md) | Scope-lock editing to a glob pattern |
| `/unfreeze` | [`unfreeze/SKILL.md`](../skills/unfreeze/SKILL.md) | Lift the scope lock set by `/freeze` |
| `/guard <glob>` | [`guard/SKILL.md`](../skills/guard/SKILL.md) | Combined `/careful` + `/freeze` for production-critical sessions |

### Team Agent Invocation

Team agent personas (orchestrator, architect, software-engineer, qa-engineer, security-engineer, platform-engineer, ui-ux-designer, product-manager, tech-writer) are **not exposed as slash commands**. They are dispatched as subagents via the Agent tool with `subagent_type: "dev-team:<agent-name>"`. This gives each persona a fresh context window, isolating its reading and reasoning from the parent conversation. The orchestrator routes work to these agents automatically; users typically don't dispatch them directly.

### Skill Invocation

Skills are user-invocable directly as `/<skill-name>` — there are no per-skill command wrappers. The available skills (specs, threat-modeling, hexagonal-architecture, domain-driven-design, domain-analysis, api-design, legacy-code, mutation-testing, governance-compliance, feedback-learning, context-loading-protocol, context-summarization, performance-metrics, quality-gate-pipeline, human-oversight-protocol, agent-skill-authoring, competitive-analysis, design-doc, branch-workflow, browser-testing, ci-debugging, design-interrogation, design-it-twice, feature-file-validation, performance-benchmark, static-analysis-integration, systematic-debugging, test-design-reviewer, test-design-advisor, cd-test-architecture, test-driven-development, docker-image-audit, docker-image-create, js-project-init) load their `SKILL.md` content into the current context and apply it to the task. See [`skills/`](../skills/) for full definitions.

### Utility Skills

| Command | File | Purpose |
| --- | --- | --- |
| `/upgrade` | [`upgrade/SKILL.md`](../skills/upgrade/SKILL.md) | Check for and apply plugin updates from within a session |
| `/help` | [`help/SKILL.md`](../skills/help/SKILL.md) | List all available slash commands with descriptions |
| `/version` | [`version/SKILL.md`](../skills/version/SKILL.md) | Report the installed plugin version |
| `/review` | [`review/SKILL.md`](../skills/review/SKILL.md) | Alias for `/code-review` — same arguments, same behavior |
| `/model-routing-check` | [`model-routing-check/SKILL.md`](../skills/model-routing-check/SKILL.md) | Read-only diagnostic: effective tier → snapshot map, override file contents, recent tier bumps, probe applicability |

## How Agents Use Skills

Agents reference skills in their `## Skills` section with invocation context:

```markdown
## Skills
- [Hexagonal Architecture](../skills/hexagonal-architecture/SKILL.md) - invoke when structuring new services
- [Domain-Driven Design](../skills/domain-driven-design/SKILL.md) - invoke when modeling bounded contexts
```

The annotation explains *when and why* that agent uses the skill. The skill itself defines *how* and is agent-agnostic.

## Add a Knowledge Skill

1. Create `skills/{skill-name}/SKILL.md` with the required sections (see template below). In a consuming project, the path is `.claude/skills/{skill-name}/SKILL.md`.
2. Add it to the Skills Registry table in `CLAUDE.md`
3. Reference it from each relevant agent's `## Skills` section with invocation context

### Skill Template

```markdown
---
name: skill-name
description: When to trigger this skill and what it does.
role: worker
user-invocable: false
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

See [Agent & Skill Authoring](../skills/agent-skill-authoring/SKILL.md) for detailed guidelines and anti-patterns. To create a new agent (review or team), use `/agent-add` — it invokes the [`agent-create`](../skills/agent-create/SKILL.md) skill, which enforces the canonical schema, token-efficiency budgets, and registration steps.

## Add a User-Invocable Skill

For a new review agent skill, use `/agent-add`. For a new workflow skill, create `.claude/skills/{name}/SKILL.md` following the skill structure (YAML frontmatter with `user-invocable: true`, `Role:` declaration, constraints, numbered steps). Run `/agent-audit` after creation.
