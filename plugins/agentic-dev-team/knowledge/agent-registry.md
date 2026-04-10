# Agent & Skill Registry (Full)

This file contains the complete registry tables. CLAUDE.md references this file for on-demand loading — the orchestrator reads it when routing decisions require the full catalog.

## Team Agents

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
| ADR Author | `agents/adr.md` | 320 | Creates and manages Architecture Decision Records |
| **All team agents** | | **~3,900** | |

## Review Agents

Spawned by the orchestrator during Phase 3 inline checkpoints and full `/code-review` runs. Model selection follows the **Orchestrator Model Routing Table** in `agents/orchestrator.md`.

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
| token-efficiency-review | `agents/token-efficiency-review.md` | small | File/function size, LLM anti-patterns, token usage |
| progress-guardian | `agents/progress-guardian.md` | mid | Plan adherence, commit discipline, scope creep detection |
| refactoring-review | `agents/refactor-scan.md` | mid | Post-GREEN refactoring opportunities, semantic vs structural duplication |
| data-flow-tracer | `agents/use-case-data-patterns.md` | mid | Data flow tracing through architecture layers (analysis-only) |

## Skills Registry

Skills are reusable knowledge modules in `.claude/skills/` that agents reference. They define patterns, guidelines, and project structures without being tied to any single agent persona.

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Context Loading Protocol | `skills/context-loading-protocol.md` | 600 | Orchestrator |
| Context Summarization | `skills/context-summarization.md` | 500 | Orchestrator |
| Feedback & Learning | `skills/feedback-learning.md` | 1,010 | Orchestrator |
| Human Oversight Protocol | `skills/human-oversight-protocol.md` | 1,020 | Orchestrator, Product Manager |
| Performance Metrics | `skills/performance-metrics.md` | 890 | Orchestrator |
| Quality Gate Pipeline | `skills/quality-gate-pipeline.md` | 900 | All agents |
| Governance & Compliance | `skills/governance-compliance.md` | 990 | QA Engineer, Technical Writer |
| Agent & Skill Authoring | `skills/agent-skill-authoring.md` | 990 | Orchestrator |
| Hexagonal Architecture | `skills/hexagonal-architecture.md` | 420 | Architect, Software Engineer |
| Domain-Driven Design | `skills/domain-driven-design.md` | 710 | Architect, Software Engineer, Product Manager |
| Domain Analysis | `skills/domain-analysis.md` | 650 | Architect, Product Manager, Orchestrator |
| Specs | `skills/specs.md` | 800 | Product Manager, Architect, QA Engineer, Orchestrator |
| Threat Modeling | `skills/threat-modeling.md` | 600 | Security Engineer, Architect |
| API Design | `skills/api-design.md` | 600 | Architect, Software Engineer |
| Legacy Code | `skills/legacy-code.md` | 700 | Software Engineer, QA Engineer, Architect |
| Mutation Testing | `skills/mutation-testing.md` | 700 | QA Engineer, Software Engineer |


| Test-Driven Development | `skills/test-driven-development.md` | 600 | Software Engineer, QA Engineer, Orchestrator |
| Systematic Debugging | `skills/systematic-debugging.md` | 600 | Software Engineer, QA Engineer |
| Design Doc | `skills/design-doc.md` | 500 | Architect, Product Manager, Orchestrator |
| Branch Workflow | `skills/branch-workflow.md` | 450 | Orchestrator, Software Engineer |
| CI Debugging | `skills/ci-debugging.md` | 550 | DevOps/SRE Engineer, Software Engineer, QA Engineer |
| Test Design Reviewer | `skills/test-design-reviewer.md` | 600 | QA Engineer, test-review |
| Browser Testing | `skills/browser-testing.md` | 700 | QA Engineer |
| Competitive Analysis | `skills/competitive-analysis.md` | 600 | Orchestrator, Product Manager |
| Design Interrogation | `skills/design-interrogation.md` | 500 | Architect, Product Manager, Orchestrator |
| Design It Twice | `skills/design-it-twice.md` | 550 | Architect, Software Engineer |
| Static Analysis Integration | `skills/static-analysis-integration.md` | 650 | Orchestrator, `/code-review` |
| Feature File Validation | `skills/feature-file-validation.md` | 700 | test-review, QA Engineer, spec-compliance-review |
| Docker Image Create | `skills/docker-image-create/SKILL.md` | 800 | DevOps/SRE Engineer, Software Engineer |
| Docker Image Audit | `skills/docker-image-audit/SKILL.md` | 750 | Orchestrator (inline review), DevOps/SRE Engineer, Security Engineer |
| Performance Benchmark | `skills/performance-benchmark/SKILL.md` | 800 | QA Engineer, DevOps/SRE Engineer, `/benchmark` command |

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

## Knowledge Files

Knowledge files in `knowledge/` provide progressive disclosure — agents read them on demand during analysis rather than carrying all detection patterns inline.

| File | ~Tokens | Used By |
|------|---------|---------|
| Agent Registry | `knowledge/agent-registry.md` | 1,200 | Orchestrator (routing decisions) |
| Review Template | `knowledge/review-template.md` | 400 | `/code-review` (report assembly) |
| Review Rubric | `knowledge/review-rubric.md` | 300 | `/code-review` (health scoring) |
| OWASP Detection | `knowledge/owasp-detection.md` | 600 | security-review |
| Domain Modeling | `knowledge/domain-modeling.md` | 500 | domain-review |
| Architecture Assessment | `knowledge/architecture-assessment.md` | 450 | arch-review |

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
