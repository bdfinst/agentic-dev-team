# Agent & Skill Registry (Full)

This file contains the complete registry tables. CLAUDE.md references this file for on-demand loading — the orchestrator reads it when routing decisions require the full catalog.

## Team Agents

| Agent | File | ~Tokens | Primary Focus |
|-------|------|---------|---------------|
| ADR Author | `agents/adr-author.md` | 320 | Creates and manages Architecture Decision Records |
| Architect | `agents/architect.md` | 360 | System design, architecture |
| Codebase Recon | `agents/codebase-recon.md` | ~900 | Repo reconnaissance — surfaces entry points, dependencies, security surface, git history. Produces RECON artifact per security-primitives-contract. Dispatched on demand by architect and domain-analysis. |
| Orchestrator | `agents/orchestrator.md` | 500 | Task routing, model selection, review coordination |
| Platform Engineer | `agents/platform-engineer.md` | 320 | Pipeline, deployment, reliability |
| Product Manager | `agents/product-manager.md` | 300 | Requirements, prioritization |
| QA/SQA Engineer | `agents/qa-engineer.md` | 320 | Testing, quality assurance |
| Security Engineer | `agents/security-engineer.md` | 320 | Security analysis, threat modeling |
| Software Engineer | `agents/software-engineer.md` | 320 | Code generation, implementation |
| Technical Writer | `agents/tech-writer.md` | 560 | Documentation, style consistency |
| UI/UX Designer | `agents/ui-ux-designer.md` | 300 | Interface design, UX |
| **All team agents** | | **~4,510** | |

## Review Agents

Spawned by the orchestrator during Phase 3 inline checkpoints and full `/code-review` runs. Each agent declares its reasoning-effort band (`effort: low|medium|high`) in frontmatter; the PreToolUse hook `hooks/agent-model-resolve.sh` resolves the band to the active model per the **Resolution Procedure** in `agents/orchestrator.md`. The band is the single source of truth — run `/model-routing-check` for the live band→model map rather than mirroring tiers here.

| Agent | File | What It Checks |
|-------|------|----------------|
| a11y-review | `agents/a11y-review.md` | WCAG 2.1 AA, ARIA, keyboard nav, focus management |
| arch-review | `agents/arch-review.md` | ADR compliance, layer boundary violations, dependency direction, pattern consistency |
| claude-setup-review | `agents/claude-setup-review.md` | CLAUDE.md completeness, rules, skills, path accuracy |
| complexity-review | `agents/complexity-review.md` | Function size, cyclomatic complexity, nesting, parameters |
| concurrency-review | `agents/concurrency-review.md` | Race conditions, async pitfalls, shared state |
| data-flow-tracer | `agents/data-flow-tracer.md` | Data flow tracing through architecture layers (analysis-only) |
| doc-review | `agents/doc-review.md` | README accuracy, API doc alignment, inline comment drift, ADR update triggers |
| domain-review | `agents/domain-review.md` | Domain boundaries, abstraction leaks, entity/DTO confusion |
| js-fp-review | `agents/js-fp-review.md` | Array mutations, impure patterns, global state |
| naming-review | `agents/naming-review.md` | Intent-revealing names, boolean prefixes, magic values |
| performance-review | `agents/performance-review.md` | Resource leaks, N+1 queries, unbounded growth |
| progress-guardian | `agents/progress-guardian.md` | Plan adherence, commit discipline, scope creep detection |
| refactor-opportunity-review | `agents/refactor-opportunity-review.md` | Post-GREEN refactoring opportunities, semantic vs structural duplication |
| security-review | `agents/security-review.md` | Injection, auth/authz, data exposure, crypto |
| session-analysis | `agents/session-analysis.md` | Maps an aggregated session digest to probable plugin causes and ranked, tagged improvement suggestions (analysis-only) |
| spec-compliance-review | `agents/spec-compliance-review.md` | Spec-to-code matching — first gate before quality review |
| structure-review | `agents/structure-review.md` | SRP violations, DRY, coupling, file organization |
| svelte-review | `agents/svelte-review.md` | Svelte reactivity pitfalls, closure state leaks |
| test-modernization-review | `agents/test-modernization-review.md` | Gate-keeper for `/test-modernize` — verifies each phase's deliverable matches its acceptance criteria before the workflow advances |
| test-review | `agents/test-review.md` | Coverage gaps, assertion quality, test hygiene |
| test-smell-review | `agents/test-smell-review.md` | xUnit test smells, test-double selection, test-pyramid layer placement |
| token-efficiency-review | `agents/token-efficiency-review.md` | File/function size, LLM anti-patterns, token usage |

## Skills Registry

Skills are reusable knowledge modules in `.claude/skills/` that agents reference. They define patterns, guidelines, and project structures without being tied to any single agent persona.

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| ADR Tools | `skills/adr-tools/SKILL.md` | ~1,350 | Orchestrator, adr-author, Software Engineer, Architect |
| Artifact Lifecycle | `skills/artifact-lifecycle/SKILL.md` | ~600 | Orchestrator, `/artifact-lifecycle` command |
| API Design | `skills/api-design/SKILL.md` | 600 | Architect, Software Engineer |
| Branch Workflow | `skills/branch-workflow/SKILL.md` | 450 | Orchestrator, Software Engineer |
| Browser Testing | `skills/browser-testing/SKILL.md` | 700 | QA Engineer |
| CD Test Architecture | `skills/cd-test-architecture/SKILL.md` | ~900 | QA Engineer, Architect, Platform Engineer, Software Engineer |
| CI Debugging | `skills/ci-debugging/SKILL.md` | 550 | Platform Engineer, Software Engineer, QA Engineer |
| Competitive Analysis | `skills/competitive-analysis/SKILL.md` | 600 | Orchestrator, Product Manager |
| Context Loading Protocol | `skills/context-loading-protocol/SKILL.md` | 600 | Orchestrator |
| Context Summarization | `skills/context-summarization/SKILL.md` | 500 | Orchestrator |
| Coverage Baseline | `skills/coverage-baseline/SKILL.md` | ~600 | `/test-modernize` (Phase 3), QA Engineer, Platform Engineer |
| Coverage Delta | `skills/coverage-delta/SKILL.md` | ~450 | `/test-modernize` (Phases 4–5), QA Engineer |
| Design Doc | `skills/design-doc/SKILL.md` | 500 | Architect, Product Manager, Orchestrator |
| Design Interrogation | `skills/design-interrogation/SKILL.md` | 500 | Architect, Product Manager, Orchestrator |
| Design It Twice | `skills/design-it-twice/SKILL.md` | 550 | Architect, Software Engineer |
| Docker Image Audit | `skills/docker-image-audit/SKILL.md` | 750 | Orchestrator (inline review), Platform Engineer, Security Engineer |
| Docker Image Create | `skills/docker-image-create/SKILL.md` | 800 | Platform Engineer, Software Engineer |
| Domain Analysis | `skills/domain-analysis/SKILL.md` | 650 | Architect, Product Manager, Orchestrator |
| Domain-Driven Design | `skills/domain-driven-design/SKILL.md` | 710 | Architect, Software Engineer, Product Manager |
| Exploratory Testing | `skills/exploratory-testing/SKILL.md` | ~900 | QA Engineer, `/explore` command |
| Farley Score | `skills/farley-score/SKILL.md` | 600 | QA Engineer, `/build` (final branch score), `/test-design` (all existing tests; reached by `/test-health` via `/test-design`) |
| Feature File Validation | `skills/feature-file-validation/SKILL.md` | 700 | test-review, QA Engineer, spec-compliance-review |
| Feedback & Learning | `skills/feedback-learning/SKILL.md` | 1,010 | Orchestrator |
| Gherkin Derive | `skills/gherkin-derive/SKILL.md` | ~700 | `/test-upgrade` (Phase 1b), QA Engineer, standalone |
| Gherkin Public | `skills/gherkin-public/SKILL.md` | ~700 | `/test-modernize` (Phase 2), QA Engineer, Product Manager |
| Governance & Compliance | `skills/governance-compliance/SKILL.md` | 990 | QA Engineer, Technical Writer |
| Hexagonal Architecture | `skills/hexagonal-architecture/SKILL.md` | 420 | Architect, Software Engineer |
| Human Oversight Protocol | `skills/human-oversight-protocol/SKILL.md` | 1,020 | Orchestrator, Product Manager |
| Issues from Assessment | `skills/issues-from-assessment/SKILL.md` | ~750 | `/test-modernize` (Phase 1), QA Engineer |
| Legacy Code | `skills/legacy-code/SKILL.md` | 700 | Software Engineer, QA Engineer, Architect |
| Mermaid Diagramming | `skills/mermaid-diagramming/SKILL.md` | ~400 | Architect, Software Engineer, Tech Writer |
| Mutation Testing | `skills/mutation-testing/SKILL.md` | 700 | QA Engineer, Software Engineer |
| Performance Benchmark | `skills/performance-benchmark/SKILL.md` | 800 | QA Engineer, Platform Engineer, `/benchmark` command |
| Performance Metrics | `skills/performance-metrics/SKILL.md` | 890 | Orchestrator |
| Quality Gate Pipeline | `skills/quality-gate-pipeline/SKILL.md` | 900 | All agents |
| Quality Targets Converge | `skills/quality-targets-converge/SKILL.md` | ~750 | `/test-modernize` (Phase 5), QA Engineer, Software Engineer |
| Semantic Duplication Scan | `skills/semantic-duplication-scan/SKILL.md` | ~4,500 | Orchestrator, Software Engineer, Architect |
| Specs | `skills/specs/SKILL.md` | 800 | Product Manager, Architect, QA Engineer, Orchestrator |
| Static Analysis Integration | `skills/static-analysis-integration/SKILL.md` | 650 | Orchestrator, `/code-review` |
| Systematic Debugging | `skills/systematic-debugging/SKILL.md` | 600 | Software Engineer, QA Engineer |
| Test Audit + Disable | `skills/test-audit-disable/SKILL.md` | ~650 | `/test-modernize` (Phase 3), QA Engineer |
| Test Design Advisor | `skills/test-design-advisor/SKILL.md` | ~700 | QA Engineer, Software Engineer, `/test-design` command |
| Test Health | `skills/test-health/SKILL.md` | ~900 | QA Engineer, `/test-health` command |
| Test Modernize | `skills/test-modernize/SKILL.md` | ~900 | Orchestrator, QA Engineer, `/test-modernize` command |
| Test-Driven Development | `skills/test-driven-development/SKILL.md` | 600 | Software Engineer, QA Engineer, Orchestrator |
| Threat Modeling | `skills/threat-modeling/SKILL.md` | 600 | Security Engineer, Architect |
| Ubiquitous Language | `skills/ubiquitous-language/SKILL.md` | ~800 | Architect, domain-review, Product Manager |

## Subagent Prompt Templates

Concrete prompt templates in `prompts/` that the orchestrator and `/code-review` use when dispatching subagents, making behavior reproducible.

| Template | File | Used By |
|----------|------|---------|
| Implementer | `prompts/implementer.md` | Orchestrator (Phase 3 implementation dispatch) |
| Plan Review — Acceptance | `prompts/plan-review-acceptance.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Design | `prompts/plan-review-design.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Parallelization | `prompts/plan-review-parallelization.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Strategic | `prompts/plan-review-strategic.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — UX | `prompts/plan-review-ux.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Reviewer | `prompts/plan-reviewer.md` | Orchestrator (Phase 2 automated pre-check) |
| Quality Reviewer | `prompts/quality-reviewer.md` | Orchestrator (three-stage review gate 2) |
| Spec Reviewer | `prompts/spec-reviewer.md` | Orchestrator (three-stage review gate 1) |

## Knowledge Files

Knowledge files in `knowledge/` provide progressive disclosure — agents read them on demand during analysis rather than carrying all detection patterns inline.

| Name | File | ~Tokens | Used By |
|------|------|---------|---------|
| Adversarial Review Protocol | `knowledge/adversarial-review-protocol.md` | ~600 | all 22 review agents (a11y-review, arch-review, claude-setup-review, complexity-review, concurrency-review, data-flow-tracer, doc-review, domain-review, js-fp-review, naming-review, performance-review, progress-guardian, refactor-opportunity-review, security-review, session-analysis, spec-compliance-review, structure-review, svelte-review, test-modernization-review, test-review, test-smell-review, token-efficiency-review) |
| Agent Registry | `knowledge/agent-registry.md` | 1,200 | Orchestrator (routing decisions) |
| Architecture Assessment | `knowledge/architecture-assessment.md` | 450 | arch-review |
| CD Maturity Model | `knowledge/cd-maturity-model.md` | ~870 | Platform Engineer, QA Engineer |
| CD Test Architecture | `knowledge/cd-test-architecture.md` | ~1,100 | cd-test-architecture, test-design-advisor |
| Component Test Patterns | `knowledge/component-test-patterns.md` | ~1,600 | cd-test-architecture |
| Database Change Management | `knowledge/database-change-management.md` | ~1,000 | Software Engineer, Architect, arch-review, `/plan` |
| Decision Defaults | `knowledge/decision-defaults.md` | ~350 | Orchestrator, Product Manager, `/plan` (approach contract) |
| Deployment Pipeline | `knowledge/deployment-pipeline.md` | ~1,000 | Platform Engineer |
| Task Size Classifier | `knowledge/task-size-classifier.md` | ~400 | Orchestrator (Task Size Gate, no-plan fast path routing) |
| Design Smells | `knowledge/design-smells.md` | ~600 | structure-review, complexity-review, naming-review |
| Domain Modeling | `knowledge/domain-modeling.md` | 500 | domain-review |
| Exploratory Testing Field Guide | `knowledge/exploratory-testing-field-guide.md` | ~900 | QA Engineer, `skills/exploratory-testing/SKILL.md` |
| Fixture Construction | `knowledge/fixture-construction.md` | ~750 | test-design-advisor, test-smell-review, test-review |
| Microservice Testing | `knowledge/microservice-testing.md` | ~700 | test-smell-review, test-design-advisor |
| Object Calisthenics | `knowledge/object-calisthenics.md` | ~400 | structure-review, complexity-review |
| OWASP Detection | `knowledge/owasp-detection.md` | 600 | security-review |
| Release Strategies | `knowledge/release-strategies.md` | ~910 | Platform Engineer, Architect, `/plan` |
| Result Verification | `knowledge/result-verification.md` | ~700 | test-design-advisor, test-review, test-smell-review |
| Review Rubric | `knowledge/review-rubric.md` | 300 | `/code-review` (health scoring) |
| Review Template | `knowledge/review-template.md` | 400 | `/code-review` (report assembly) |
| Test Automation Maturity | `knowledge/test-automation-maturity.md` | ~450 | test-review, test-health |
| Test Doubles | `knowledge/test-doubles.md` | ~700 | test-smell-review, test-design-advisor |
| Test File Indicators | `knowledge/test-file-indicators.md` | ~200 | test-review, test-smell-review, `/test-design`, `/build` |
| Test Layer Gates | `knowledge/test-layer-gates.md` | ~480 | test-design-advisor |
| Test Matrix Examples | `knowledge/test-matrix-examples/*.md` | ~950 | test-design-advisor (few-shot templates) |
| Test Organization | `knowledge/test-organization.md` | ~750 | test-design-advisor, test-smell-review |
| Test Pyramid | `knowledge/test-pyramid.md` | ~800 | test-smell-review, test-review, test-design-advisor, test-health |
| Test Refactoring | `knowledge/test-refactoring.md` | ~750 | test-design-advisor, test-smell-review |
| Test Review Division of Labor | `knowledge/test-review-division-of-labor.md` | ~300 | test-review, test-smell-review, `/test-design` |
| Test Smells | `knowledge/test-smells.md` | ~900 | test-smell-review, test-review, test-design-advisor |
| Test Stack Profiles | `knowledge/test-stack-profiles/*.md` | ~1,400 | test-design-advisor (tool resolution by detected stack) |
| Test Strategy | `knowledge/test-strategy.md` | ~900 | test-design-advisor, test-smell-review, test-review |
| Testability Patterns | `knowledge/testability-patterns.md` | ~500 | test-review, test-smell-review, test-design-advisor, legacy-code |
| Testing Quadrants | `knowledge/testing-quadrants.md` | ~400 | test-health, test-design-advisor |
| Testing Techniques | `knowledge/testing-techniques/*.md` | ~1,300 | test-design-advisor (overlay, on trigger), security-review |

## Agent Templates

Language-specific review agents in `templates/agents/`. Scaffolded into projects by `/setup` when the matching stack is detected. Not bundled as always-on.

| Template | File | Activates When |
|----------|------|---------------|
| angular-testing | `templates/agents/angular-testing.md` | Angular in deps |
| csharp-quality | `templates/agents/csharp-quality.md` | C#/.NET stack |
| esm-enforcer | `templates/agents/esm-enforcer.md` | Any JS/TS project (always-on) |
| front-end-testing | `templates/agents/front-end-testing.md` | Any frontend framework |
| go-quality | `templates/agents/go-quality.md` | Go stack |
| python-quality | `templates/agents/python-quality.md` | Python stack |
| react-testing | `templates/agents/react-testing.md` | React in deps |
| ts-enforcer | `templates/agents/ts-enforcer.md` | TypeScript detected |
| twelve-factor-audit | `templates/agents/twelve-factor-audit.md` | Service/API project |
