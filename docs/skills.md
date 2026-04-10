# Skills and Slash Commands

There are two kinds of reusable capabilities in this system:

- **Skills** (`skills/`) — knowledge modules that agents read for domain expertise (patterns, guidelines, procedures). Agent-agnostic; any agent can reference them.
- **Slash commands** (`commands/`) — user-invocable workflows with numbered steps, argument parsing, and structured output. Executed under Orchestrator direction.

## Skills Catalog

### Orchestration Skills

Used by the Orchestrator to manage the team:

| Skill | File | Purpose |
| --- | --- | --- |
| Context Loading Protocol | [`context-loading-protocol.md`](../plugins/agentic-dev-team/skills/context-loading-protocol/SKILL.md) | Decides which agent/skill files to load and when |
| Context Summarization | [`context-summarization.md`](../plugins/agentic-dev-team/skills/context-summarization/SKILL.md) | Compresses conversation history at utilization thresholds |
| Feedback & Learning | [`feedback-learning.md`](../plugins/agentic-dev-team/skills/feedback-learning/SKILL.md) | Processes feedback keywords, audit trail, rollback |
| Human Oversight Protocol | [`human-oversight-protocol.md`](../plugins/agentic-dev-team/skills/human-oversight-protocol/SKILL.md) | Approval gates, intervention commands, escalation |
| Performance Metrics | [`performance-metrics.md`](../plugins/agentic-dev-team/skills/performance-metrics/SKILL.md) | Task logging schema and reporting procedures |
| Agent & Skill Authoring | [`agent-skill-authoring.md`](../plugins/agentic-dev-team/skills/agent-skill-authoring/SKILL.md) | How to create and maintain agents and skills |
| Specs | [`specs.md`](../plugins/agentic-dev-team/skills/specs/SKILL.md) | BDD scenario consistency gate before implementation |

### Quality Skills

Used by all agents to ensure output correctness:

| Skill | File | Purpose |
| --- | --- | --- |
| Quality Gate Pipeline | [`quality-gate-pipeline.md`](../plugins/agentic-dev-team/skills/quality-gate-pipeline/SKILL.md) | Unified quality gate: self-validation, verification evidence, review-correction loops |
| Governance & Compliance | [`governance-compliance.md`](../plugins/agentic-dev-team/skills/governance-compliance/SKILL.md) | Audit trail, quality assurance layers, ethics principles |

### Development Discipline Skills

Enforce rigorous development practices:

| Skill | File | Purpose |
| --- | --- | --- |
| Test-Driven Development | [`test-driven-development.md`](../plugins/agentic-dev-team/skills/test-driven-development/SKILL.md) | RED-GREEN-REFACTOR cycle with hard gates, rationalization prevention |
| Systematic Debugging | [`systematic-debugging.md`](../plugins/agentic-dev-team/skills/systematic-debugging/SKILL.md) | 4-phase debugging protocol (reproduce, investigate, root-cause, fix) |
| Design Doc | [`design-doc.md`](../plugins/agentic-dev-team/skills/design-doc/SKILL.md) | Written design document with alternatives analysis before planning |
| Branch Workflow | [`branch-workflow.md`](../plugins/agentic-dev-team/skills/branch-workflow/SKILL.md) | PR creation, merge strategy, and branch cleanup after Phase 3 |
| CI Debugging | [`ci-debugging.md`](../plugins/agentic-dev-team/skills/ci-debugging/SKILL.md) | CI pipeline failure investigation and resolution |
| Test Design Reviewer | [`test-design-reviewer.md`](../plugins/agentic-dev-team/skills/test-design-reviewer/SKILL.md) | Test quality patterns and anti-patterns |
| Browser Testing | [`browser-testing.md`](../plugins/agentic-dev-team/skills/browser-testing/SKILL.md) | Playwright-based browser QA for visual verification |
| Feature File Validation | [`feature-file-validation.md`](../plugins/agentic-dev-team/skills/feature-file-validation/SKILL.md) | Gherkin quality, determinism, implementation independence, test automation coverage |

### Research & Design Skills

Used during the Research phase to explore alternatives and stress-test designs:

| Skill | File | Purpose |
| --- | --- | --- |
| Competitive Analysis | [`competitive-analysis.md`](../plugins/agentic-dev-team/skills/competitive-analysis/SKILL.md) | Gap analysis against external tools, plugins, or feature sets |
| Design Interrogation | [`design-interrogation.md`](../plugins/agentic-dev-team/skills/design-interrogation/SKILL.md) | Stress-test design decisions before planning |
| Design It Twice | [`design-it-twice.md`](../plugins/agentic-dev-team/skills/design-it-twice/SKILL.md) | Generate parallel alternative interfaces via sub-agents |

### Technical Skills

Domain knowledge for implementation work:

| Skill | File | Purpose |
| --- | --- | --- |
| Hexagonal Architecture | [`hexagonal-architecture.md`](../plugins/agentic-dev-team/skills/hexagonal-architecture/SKILL.md) | Ports & adapters pattern, dependency rule, project structure |
| Domain-Driven Design | [`domain-driven-design.md`](../plugins/agentic-dev-team/skills/domain-driven-design/SKILL.md) | Bounded contexts, aggregates, domain events, ubiquitous language |
| API Design | [`api-design.md`](../plugins/agentic-dev-team/skills/api-design/SKILL.md) | Contract-first design, versioning, REST conventions |
| Threat Modeling | [`threat-modeling.md`](../plugins/agentic-dev-team/skills/threat-modeling/SKILL.md) | STRIDE analysis, trust boundaries, mitigation strategies |
| Legacy Code | [`legacy-code.md`](../plugins/agentic-dev-team/skills/legacy-code/SKILL.md) | Characterization testing, safe refactoring in untested code |
| Mutation Testing | [`mutation-testing.md`](../plugins/agentic-dev-team/skills/mutation-testing/SKILL.md) | Evaluating test suite effectiveness against behavioral mutations |
| Docker Image Create | [`docker-image-create/SKILL.md`](../plugins/agentic-dev-team/skills/docker-image-create/SKILL.md) | Generate production Dockerfiles with multi-stage builds, slim/distroless bases |
| Docker Image Audit | [`docker-image-audit/SKILL.md`](../plugins/agentic-dev-team/skills/docker-image-audit/SKILL.md) | Audit Dockerfiles and images with hadolint, Trivy, Grype; structured severity report |
| Performance Benchmark | [`performance-benchmark/SKILL.md`](../plugins/agentic-dev-team/skills/performance-benchmark/SKILL.md) | Runtime performance measurement: Core Web Vitals, resource sizes, baseline comparison, performance budgets, trend tracking |

### Subagent Prompt Templates

Concrete templates in `prompts/` for reproducible subagent dispatch:

| Template | File | Purpose |
| --- | --- | --- |
| Implementer | [`implementer.md`](../plugins/agentic-dev-team/prompts/implementer.md) | Phase 3 implementation dispatch with TDD enforcement |
| Spec Reviewer | [`spec-reviewer.md`](../plugins/agentic-dev-team/prompts/spec-reviewer.md) | Two-stage review gate 1: does code match spec? |
| Quality Reviewer | [`quality-reviewer.md`](../plugins/agentic-dev-team/prompts/quality-reviewer.md) | Two-stage review gate 2: is code high quality? |
| Plan Reviewer | [`plan-reviewer.md`](../plugins/agentic-dev-team/prompts/plan-reviewer.md) | Phase 2 automated pre-check before human review |
| Plan Review — Acceptance | [`plan-review-acceptance.md`](../plugins/agentic-dev-team/prompts/plan-review-acceptance.md) | Criteria verifiability, scenario completeness, error paths, TDD traceability |
| Plan Review — Design | [`plan-review-design.md`](../plugins/agentic-dev-team/prompts/plan-review-design.md) | Coupling, abstraction quality, structural risks, pattern consistency |
| Plan Review — UX | [`plan-review-ux.md`](../plugins/agentic-dev-team/prompts/plan-review-ux.md) | User journey, error experience, cognitive load, accessibility |
| Plan Review — Strategic | [`plan-review-strategic.md`](../plugins/agentic-dev-team/prompts/plan-review-strategic.md) | Problem-solution fit, scope, risk, opportunity cost |

## Slash Commands Catalog

Slash commands are invoked by the user (e.g., `/code-review`) and executed under Orchestrator direction. The Orchestrator's Model Routing Table controls which model runs each review agent.

### Review Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/code-review` | [`code-review.md`](../plugins/agentic-dev-team/commands/code-review.md) | Run all review agents, auto-fix actionable issues, and re-run until clean (up to 5 iterations) |
| `/review-agent <name>` | [`review-agent.md`](../plugins/agentic-dev-team/commands/review-agent.md) | Run a single named review agent; used for inline Phase 3 checkpoints |
| `/apply-fixes` | [`apply-fixes.md`](../plugins/agentic-dev-team/commands/apply-fixes.md) | Apply correction prompts generated by `/code-review` |
| `/review-summary` | [`review-summary.md`](../plugins/agentic-dev-team/commands/review-summary.md) | Generate a compact session summary for cross-session context continuity |
| `/semgrep-analyze` | [`semgrep-analyze.md`](../plugins/agentic-dev-team/commands/semgrep-analyze.md) | Run Semgrep static analysis and return structured findings |

### Eval Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-audit` | [`agent-audit.md`](../plugins/agentic-dev-team/commands/agent-audit.md) | Audit agents and commands for structural compliance |
| `/agent-eval` | [`agent-eval.md`](../plugins/agentic-dev-team/commands/agent-eval.md) | Run eval fixtures, grade review agent accuracy, detect regressions |
| `/harness-audit` | [`harness-audit.md`](../plugins/agentic-dev-team/commands/harness-audit.md) | Analyze harness effectiveness, flag stale components |

### Scaffolding Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/agent-add` | [`agent-add.md`](../plugins/agentic-dev-team/commands/agent-add.md) | Scaffold a new review agent with eval compliance check and doc updates |
| `/agent-remove` | [`agent-remove.md`](../plugins/agentic-dev-team/commands/agent-remove.md) | Remove an agent and all its registry entries and doc references |
| `/add-plugin` | [`add-plugin.md`](../plugins/agentic-dev-team/commands/add-plugin.md) | Install a plugin and register it in `settings.json` |

### Workflow Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/plan` | [`plan.md`](../plugins/agentic-dev-team/commands/plan.md) | Create a structured implementation plan with TDD steps |
| `/build` | [`build.md`](../plugins/agentic-dev-team/commands/build.md) | Execute an approved plan with TDD, inline reviews, and verification evidence |
| `/pr` | [`pr.md`](../plugins/agentic-dev-team/commands/pr.md) | Run quality gates and create a pull request |
| `/setup` | [`setup.md`](../plugins/agentic-dev-team/commands/setup.md) | Detect tech stack, generate project-level config and hooks |
| `/continue` | [`continue.md`](../plugins/agentic-dev-team/commands/continue.md) | Resume work from a prior session using phase progress files |
| `/domain-analysis` | [`domain-analysis.md`](../plugins/agentic-dev-team/commands/domain-analysis.md) | Assess DDD health: bounded contexts, context map, friction report |
| `/browse` | [`browse.md`](../plugins/agentic-dev-team/commands/browse.md) | Browser-based QA via Playwright: navigate, screenshot, click, fill forms |
| `/triage` | [`triage.md`](../plugins/agentic-dev-team/commands/triage.md) | Investigate a bug, find root cause, file a GitHub issue with TDD fix plan |
| `/issues-from-plan` | [`issues-from-plan.md`](../plugins/agentic-dev-team/commands/issues-from-plan.md) | Break a plan into independently-grabbable GitHub issues |
| `/benchmark` | [`benchmark.md`](../plugins/agentic-dev-team/commands/benchmark.md) | Capture runtime performance metrics (Core Web Vitals, resource sizes) and compare against baselines |
| `/competitive-analysis` | [`competitive-analysis.md`](../plugins/agentic-dev-team/commands/competitive-analysis.md) | Compare plugin against others to find gaps and weaknesses |

### Safety Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/careful` | [`careful.md`](../plugins/agentic-dev-team/commands/careful.md) | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE) |
| `/freeze <glob>` | [`freeze.md`](../plugins/agentic-dev-team/commands/freeze.md) | Scope-lock editing to a glob pattern |
| `/unfreeze` | [`unfreeze.md`](../plugins/agentic-dev-team/commands/unfreeze.md) | Lift the scope lock set by `/freeze` |
| `/guard <glob>` | [`guard.md`](../plugins/agentic-dev-team/commands/guard.md) | Combined `/careful` + `/freeze` for production-critical sessions |

### Utility Commands

| Command | File | Purpose |
| --- | --- | --- |
| `/upgrade` | [`upgrade.md`](../plugins/agentic-dev-team/commands/upgrade.md) | Check for and apply plugin updates from within a session |
| `/help` | [`help.md`](../plugins/agentic-dev-team/commands/help.md) | List all available slash commands with descriptions |
| `/review` | [`review.md`](../plugins/agentic-dev-team/commands/review.md) | Alias for `/code-review` — same arguments, same behavior |

## How Agents Use Skills

Agents reference skills in their `## Skills` section with invocation context:

```markdown
## Skills
- [Hexagonal Architecture](../plugins/agentic-dev-team/skills/hexagonal-architecture/SKILL.md) - invoke when structuring new services
- [Domain-Driven Design](../plugins/agentic-dev-team/skills/domain-driven-design/SKILL.md) - invoke when modeling bounded contexts
```

The annotation explains *when and why* that agent uses the skill. The skill itself defines *how* and is agent-agnostic.

## Add a Knowledge Skill

1. Create `skills/{skill-name}.md` with the required sections (see template below). In a consuming project, the path is `.claude/skills/{skill-name}.md`.
2. Add it to the Skills Registry table in `CLAUDE.md`
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

See [Agent & Skill Authoring](../plugins/agentic-dev-team/skills/agent-skill-authoring/SKILL.md) for detailed guidelines and anti-patterns.

## Add a Slash Command

For a new review agent command, use `/add-agent`. For a new workflow command, create `.claude/commands/{name}.md` following the slash command structure (YAML frontmatter with `user-invocable: true`, `Role:` declaration, constraints, numbered steps). Run `/agent-audit` after creation.
