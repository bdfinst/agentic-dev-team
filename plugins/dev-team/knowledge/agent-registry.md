# Agent & Skill Registry (Full)

This file contains the complete registry tables. CLAUDE.md references this file for on-demand loading — the orchestrator reads it when routing decisions require the full catalog.

## Team Agents

| Agent | File | ~Tokens | Primary Focus |
|-------|------|---------|---------------|
| Orchestrator | `agents/orchestrator.md` | 500 | Task routing, model selection, review coordination |
| Software Engineer | `agents/software-engineer.md` | 320 | Code generation, implementation |
| QA/SQA Engineer | `agents/qa-engineer.md` | 320 | Testing, quality assurance |
| UI/UX Designer | `agents/ui-ux-designer.md` | 300 | Interface design, UX |
| Architect | `agents/architect.md` | 360 | System design, architecture |
| Product Manager | `agents/product-manager.md` | 300 | Requirements, prioritization |
| Technical Writer | `agents/tech-writer.md` | 560 | Documentation, style consistency |
| Security Engineer | `agents/security-engineer.md` | 320 | Security analysis, threat modeling |
| Platform Engineer | `agents/platform-engineer.md` | 320 | Pipeline, deployment, reliability |
| ADR Author | `agents/adr-author.md` | 320 | Creates and manages Architecture Decision Records |
| Codebase Recon | `agents/codebase-recon.md` | ~900 | Repo reconnaissance — surfaces entry points, dependencies, security surface, git history. Produces RECON artifact per security-primitives-contract. Dispatched on demand by architect and domain-analysis. |
| **All team agents** | | **~4,510** | |

## Review Agents

Spawned by the orchestrator during Phase 3 inline checkpoints and full `/code-review` runs. Each agent declares a tier alias in its `model:` frontmatter; the PreToolUse hook `hooks/agent-model-resolve.sh` resolves it to the active snapshot per the **Resolution Procedure** in `agents/orchestrator.md`.

| Agent | File | Model Tier | What It Checks |
|-------|------|------------|----------------|
| spec-compliance-review | `agents/spec-compliance-review.md` | mid | Spec-to-code matching — first gate before quality review |
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
| test-smell-review | `agents/test-smell-review.md` | mid | xUnit test smells, test-double selection, test-pyramid layer placement |
| token-efficiency-review | `agents/token-efficiency-review.md` | small | File/function size, LLM anti-patterns, token usage |
| progress-guardian | `agents/progress-guardian.md` | mid | Plan adherence, commit discipline, scope creep detection |
| refactor-opportunity-review | `agents/refactor-opportunity-review.md` | mid | Post-GREEN refactoring opportunities, semantic vs structural duplication |
| data-flow-tracer | `agents/data-flow-tracer.md` | mid | Data flow tracing through architecture layers (analysis-only) |
| test-modernization-review | `agents/test-modernization-review.md` | mid | Gate-keeper for `/test-modernize` — verifies each phase's deliverable matches its acceptance criteria before the workflow advances |

## Skills Registry

Skills are reusable knowledge modules in `.claude/skills/` that agents reference. They define patterns, guidelines, and project structures without being tied to any single agent persona.

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Context Loading Protocol | `skills/context-loading-protocol/SKILL.md` | 600 | Orchestrator |
| Context Summarization | `skills/context-summarization/SKILL.md` | 500 | Orchestrator |
| Feedback & Learning | `skills/feedback-learning/SKILL.md` | 1,010 | Orchestrator |
| Human Oversight Protocol | `skills/human-oversight-protocol/SKILL.md` | 1,020 | Orchestrator, Product Manager |
| Performance Metrics | `skills/performance-metrics/SKILL.md` | 890 | Orchestrator |
| Quality Gate Pipeline | `skills/quality-gate-pipeline/SKILL.md` | 900 | All agents |
| Governance & Compliance | `skills/governance-compliance/SKILL.md` | 990 | QA Engineer, Technical Writer |
| Agent & Skill Authoring | `skills/agent-skill-authoring/SKILL.md` | 1,300 | Orchestrator, Technical Writer |
| Hexagonal Architecture | `skills/hexagonal-architecture/SKILL.md` | 420 | Architect, Software Engineer |
| Domain-Driven Design | `skills/domain-driven-design/SKILL.md` | 710 | Architect, Software Engineer, Product Manager |
| Domain Analysis | `skills/domain-analysis/SKILL.md` | 650 | Architect, Product Manager, Orchestrator |
| Specs | `skills/specs/SKILL.md` | 800 | Product Manager, Architect, QA Engineer, Orchestrator |
| Threat Modeling | `skills/threat-modeling/SKILL.md` | 600 | Security Engineer, Architect |
| API Design | `skills/api-design/SKILL.md` | 600 | Architect, Software Engineer |
| Legacy Code | `skills/legacy-code/SKILL.md` | 700 | Software Engineer, QA Engineer, Architect |
| Mutation Testing | `skills/mutation-testing/SKILL.md` | 700 | QA Engineer, Software Engineer |
| Test-Driven Development | `skills/test-driven-development/SKILL.md` | 600 | Software Engineer, QA Engineer, Orchestrator |
| Systematic Debugging | `skills/systematic-debugging/SKILL.md` | 600 | Software Engineer, QA Engineer |
| Design Doc | `skills/design-doc/SKILL.md` | 500 | Architect, Product Manager, Orchestrator |
| Branch Workflow | `skills/branch-workflow/SKILL.md` | 450 | Orchestrator, Software Engineer |
| CI Debugging | `skills/ci-debugging/SKILL.md` | 550 | Platform Engineer, Software Engineer, QA Engineer |
| Test Design Reviewer | `skills/test-design-reviewer/SKILL.md` | 600 | QA Engineer, test-review, `/build` (final branch score), `/test-design` (all existing tests; reached by `/test-health` via `/test-design`) |
| Test Design Advisor | `skills/test-design-advisor/SKILL.md` | ~700 | QA Engineer, Software Engineer, `/test-design` command |
| CD Test Architecture | `skills/cd-test-architecture/SKILL.md` | ~900 | QA Engineer, Architect, Platform Engineer, Software Engineer |
| Test Health | `skills/test-health/SKILL.md` | ~900 | QA Engineer, `/test-health` command |
| Browser Testing | `skills/browser-testing/SKILL.md` | 700 | QA Engineer |
| Exploratory Testing | `skills/exploratory-testing/SKILL.md` | ~900 | QA Engineer, `/explore` command |
| Competitive Analysis | `skills/competitive-analysis/SKILL.md` | 600 | Orchestrator, Product Manager |
| Design Interrogation | `skills/design-interrogation/SKILL.md` | 500 | Architect, Product Manager, Orchestrator |
| Design It Twice | `skills/design-it-twice/SKILL.md` | 550 | Architect, Software Engineer |
| Static Analysis Integration | `skills/static-analysis-integration/SKILL.md` | 650 | Orchestrator, `/code-review` |
| Feature File Validation | `skills/feature-file-validation/SKILL.md` | 700 | test-review, QA Engineer, spec-compliance-review |
| Docker Image Create | `skills/docker-image-create/SKILL.md` | 800 | Platform Engineer, Software Engineer |
| Docker Image Audit | `skills/docker-image-audit/SKILL.md` | 750 | Orchestrator (inline review), Platform Engineer, Security Engineer |
| Performance Benchmark | `skills/performance-benchmark/SKILL.md` | 800 | QA Engineer, Platform Engineer, `/benchmark` command |
| Semantic Duplication Scan | `skills/semantic-duplication-scan/SKILL.md` | ~4,500 | Orchestrator, Software Engineer, Architect |
| Agent Create | `skills/agent-create/SKILL.md` | ~2,100 | Orchestrator, Software Engineer, all team agents |
| ADR Tools | `skills/adr-tools/SKILL.md` | ~1,350 | Orchestrator, adr-author, Software Engineer, Architect |
| Mermaid Diagramming | `skills/mermaid-diagramming/SKILL.md` | ~400 | Architect, Software Engineer, Tech Writer |
| Ubiquitous Language | `skills/ubiquitous-language/SKILL.md` | ~800 | Architect, domain-review, Product Manager |
| Test Modernize | `skills/test-modernize/SKILL.md` | ~900 | Orchestrator, QA Engineer, `/test-modernize` command |
| Issues from Assessment | `skills/issues-from-assessment/SKILL.md` | ~750 | `/test-modernize` (Phase 1), QA Engineer |
| Gherkin Public | `skills/gherkin-public/SKILL.md` | ~700 | `/test-modernize` (Phase 2), QA Engineer, Product Manager |
| Test Audit + Disable | `skills/test-audit-disable/SKILL.md` | ~650 | `/test-modernize` (Phase 3), QA Engineer |
| Coverage Baseline | `skills/coverage-baseline/SKILL.md` | ~600 | `/test-modernize` (Phase 3), QA Engineer, Platform Engineer |
| Coverage Delta | `skills/coverage-delta/SKILL.md` | ~450 | `/test-modernize` (Phases 4–5), QA Engineer |
| Quality Targets Converge | `skills/quality-targets-converge/SKILL.md` | ~750 | `/test-modernize` (Phase 5), QA Engineer, Software Engineer |

## Subagent Prompt Templates

Concrete prompt templates in `prompts/` that the orchestrator and `/code-review` use when dispatching subagents, making behavior reproducible.

| Template | File | Used By |
|----------|------|---------|
| Implementer | `prompts/implementer.md` | Orchestrator (Phase 3 implementation dispatch) |
| Spec Reviewer | `prompts/spec-reviewer.md` | Orchestrator (three-stage review gate 1) |
| Quality Reviewer | `prompts/quality-reviewer.md` | Orchestrator (three-stage review gate 2) |
| Plan Reviewer | `prompts/plan-reviewer.md` | Orchestrator (Phase 2 automated pre-check) |
| Plan Review — Acceptance | `prompts/plan-review-acceptance.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Design | `prompts/plan-review-design.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — UX | `prompts/plan-review-ux.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Strategic | `prompts/plan-review-strategic.md` | Orchestrator (Phase 2 plan review persona) |
| Plan Review — Parallelization | `prompts/plan-review-parallelization.md` | Orchestrator (Phase 2 plan review persona) |

## Knowledge Files

Knowledge files in `knowledge/` provide progressive disclosure — agents read them on demand during analysis rather than carrying all detection patterns inline.

| Name | File | ~Tokens | Used By |
|------|------|---------|---------|
| Agent Registry | `knowledge/agent-registry.md` | 1,200 | Orchestrator (routing decisions) |
| Decision Defaults | `knowledge/decision-defaults.md` | ~350 | Orchestrator, Product Manager, `/plan` (approach contract) |
| Review Template | `knowledge/review-template.md` | 400 | `/code-review` (report assembly) |
| Review Rubric | `knowledge/review-rubric.md` | 300 | `/code-review` (health scoring) |
| OWASP Detection | `knowledge/owasp-detection.md` | 600 | security-review |
| Domain Modeling | `knowledge/domain-modeling.md` | 500 | domain-review |
| Architecture Assessment | `knowledge/architecture-assessment.md` | 450 | arch-review |
| Exploratory Testing Field Guide | `knowledge/exploratory-testing-field-guide.md` | ~900 | QA Engineer, `skills/exploratory-testing/SKILL.md` |
| Adversarial Review Protocol | `knowledge/adversarial-review-protocol.md` | ~500 | security-review, test-review, test-smell-review, structure-review, complexity-review, arch-review, domain-review |
| Design Smells | `knowledge/design-smells.md` | ~600 | structure-review, complexity-review, naming-review |
| Object Calisthenics | `knowledge/object-calisthenics.md` | ~400 | structure-review, complexity-review |
| Testability Patterns | `knowledge/testability-patterns.md` | ~500 | test-review, test-smell-review, test-design-advisor, legacy-code |
| Test Smells | `knowledge/test-smells.md` | ~900 | test-smell-review, test-review, test-design-advisor |
| Test Doubles | `knowledge/test-doubles.md` | ~700 | test-smell-review, test-design-advisor |
| Test Pyramid | `knowledge/test-pyramid.md` | ~800 | test-smell-review, test-review, test-design-advisor, test-health |
| Test Strategy | `knowledge/test-strategy.md` | ~900 | test-design-advisor, test-smell-review, test-review |
| Fixture Construction | `knowledge/fixture-construction.md` | ~750 | test-design-advisor, test-smell-review, test-review |
| Result Verification | `knowledge/result-verification.md` | ~700 | test-design-advisor, test-review, test-smell-review |
| Test Organization | `knowledge/test-organization.md` | ~750 | test-design-advisor, test-smell-review |
| Test Refactoring | `knowledge/test-refactoring.md` | ~750 | test-design-advisor, test-smell-review |
| Microservice Testing | `knowledge/microservice-testing.md` | ~700 | test-smell-review, test-design-advisor |
| CD Test Architecture | `knowledge/cd-test-architecture.md` | ~1,100 | cd-test-architecture, test-design-advisor |
| Component Test Patterns | `knowledge/component-test-patterns.md` | ~1,600 | cd-test-architecture |
| Test Layer Gates | `knowledge/test-layer-gates.md` | ~480 | test-design-advisor |
| Testing Quadrants | `knowledge/testing-quadrants.md` | ~400 | test-health, test-design-advisor |
| Test Automation Maturity | `knowledge/test-automation-maturity.md` | ~450 | test-review, test-health |
| Test Matrix Examples | `knowledge/test-matrix-examples/*.md` | ~950 | test-design-advisor (few-shot templates) |
| Testing Techniques | `knowledge/testing-techniques/*.md` | ~1,300 | test-design-advisor (overlay, on trigger), security-review |
| Test Stack Profiles | `knowledge/test-stack-profiles/*.md` | ~1,400 | test-design-advisor (tool resolution by detected stack) |

## Agent Templates

Language-specific review agents in `templates/agents/`. Scaffolded into projects by `/setup` when the matching stack is detected. Not bundled as always-on.

| Template | File | Activates When |
|----------|------|---------------|
| ts-enforcer | `templates/agents/ts-enforcer.md` | TypeScript detected |
| esm-enforcer | `templates/agents/esm-enforcer.md` | Any JS/TS project (always-on) |
| react-testing | `templates/agents/react-testing.md` | React in deps |
| front-end-testing | `templates/agents/front-end-testing.md` | Any frontend framework |
| twelve-factor-audit | `templates/agents/twelve-factor-audit.md` | Service/API project |
| python-quality | `templates/agents/python-quality.md` | Python stack |
| go-quality | `templates/agents/go-quality.md` | Go stack |
| csharp-quality | `templates/agents/csharp-quality.md` | C#/.NET stack |
| angular-testing | `templates/agents/angular-testing.md` | Angular in deps |
