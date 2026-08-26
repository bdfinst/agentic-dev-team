# Agent & Skill Registry (Full)

This file contains the complete registry tables. CLAUDE.md references this file for on-demand loading — the orchestrator reads it when routing decisions require the full catalog.

## Team Agents

| Agent | File | ~Tokens | Primary Focus |
| ------- | ------ | --------- | --------------- |
| ADR Author | `agents/adr-author.md` | 1,143 | Creates and manages Architecture Decision Records |
| Architect | `agents/architect.md` | 1,482 | System design, architecture |
| Codebase Recon | `agents/codebase-recon.md` | ~2,858 | Repo reconnaissance — surfaces entry points, dependencies, security surface, git history. Produces RECON artifact per security-primitives-contract. Dispatched on demand by architect and domain-analysis, and at the start of Phase 1: Research when no fresh artifact exists (see `${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#codebase-recon-dispatch`). |
| Gherkin Quality Critic | `agents/gherkin-quality-critic.md` | ~1,176 | Adversarial review of freshly-derived/authored Gherkin — coverage gaps and positive/negative balance. Dispatched by `/gherkin-derive` and `/gherkin-public`, never directly. |
| Orchestrator | `agents/orchestrator.md` | 5,510 | Task routing, model selection, review coordination |
| Plan Review Acceptance Critic | `agents/plan-review-acceptance.md` | ~1,386 | Adversarial plan review — acceptance criteria, Gherkin scenario, and TDD step traceability quality. Dispatched by `/plan` step 5b, never directly. |
| Plan Review Design Critic | `agents/plan-review-design.md` | ~1,227 | Adversarial plan review — coupling, abstraction, structural risk, and pattern-adherence quality. Dispatched by `/plan` step 5b, never directly. |
| Plan Review Parallelization Critic | `agents/plan-review-parallelization.md` | ~1,182 | Adversarial plan review — same-wave file-collision and behavioral-coupling verification. Dispatched by `/plan` step 5b, never directly. |
| Plan Review Strategic Critic | `agents/plan-review-strategic.md` | ~1,379 | Adversarial plan review — problem-solution fit, scope, risk, opportunity cost. Dispatched by `/plan` step 5b, never directly. |
| Plan Review UX Critic | `agents/plan-review-ux.md` | ~1,470 | Adversarial plan review — usability, accessibility, error experience; self-skips for non-UI plans. Dispatched by `/plan` step 5b, never directly. |
| Platform Engineer | `agents/platform-engineer.md` | 1,252 | Pipeline, deployment, reliability |
| Product Manager | `agents/product-manager.md` | 1,221 | Requirements, prioritization |
| QA/SQA Engineer | `agents/qa-engineer.md` | 4,188 | Testing, quality assurance |
| Security Engineer | `agents/security-engineer.md` | 1,115 | Security analysis, threat modeling |
| Software Engineer | `agents/software-engineer.md` | 2,122 | Code generation, implementation |
| Technical Writer | `agents/tech-writer.md` | 939 | Documentation, style consistency |
| UI/UX Designer | `agents/ui-ux-designer.md` | 583 | Interface design, UX |
| **All team agents** | | **~30,233** | |

## Review Agents

Spawned by the orchestrator during Phase 3 inline checkpoints and full `/code-review` runs. Each agent declares its own `model:`/`effort:` frontmatter — the native Claude Code sub-agent contract the harness resolves directly (see **Model/Effort Resolution** in `agents/orchestrator.md`). The frontmatter is the single source of truth; it is not mirrored here.

| Agent | File | What It Checks |
| ------- | ------ | ---------------- |
| a11y-review | `agents/a11y-review.md` | WCAG 2.1 AA, ARIA, keyboard nav, focus management |
| ai-provenance-review | `agents/ai-provenance-review.md` | AI-authored test assertion verification debt, regeneration-risk candidates (magic values, unusual ordering) with no human-verification evidence |
| arch-review | `agents/arch-review.md` | ADR compliance, layer boundary violations, dependency direction, pattern consistency |
| claude-setup-review | `agents/claude-setup-review.md` | CLAUDE.md completeness, rules, skills, path accuracy |
| complexity-review | `agents/complexity-review.md` | Function size, cyclomatic complexity, nesting, parameters |
| component-architecture-review | `agents/component-architecture-review.md` | Reusable component extraction, frontend UI duplication, prop drilling, component granularity, inconsistent component APIs |
| concurrency-review | `agents/concurrency-review.md` | Race conditions, async pitfalls, shared state |
| correctness-review | `agents/correctness-review.md` | Functional/behavioral defects — implementation diverges from evident intent |
| data-flow-tracer | `agents/data-flow-tracer.md` | Data flow tracing through architecture layers (analysis-only) |
| doc-review | `agents/doc-review.md` | README accuracy, API doc alignment, inline comment drift, ADR update triggers |
| domain-review | `agents/domain-review.md` | Domain boundaries, abstraction leaks, entity/DTO confusion |
| js-fp-review | `agents/js-fp-review.md` | Array mutations, impure patterns, global state, point-free/composition opportunities |
| mutation-kill | `agents/mutation-kill.md` | Autonomous survivor-reduction loop — generates targeted tests, verifies, commits, repeats; gates on hard kills only (Go advisory). Not a reviewer; invoked per Story by `/test-improve` Phase 5 or directly |
| naming-review | `agents/naming-review.md` | Intent-revealing names, boolean prefixes, magic values |
| performance-review | `agents/performance-review.md` | Resource leaks, N+1 queries, unbounded growth |
| progress-guardian | `agents/progress-guardian.md` | Plan adherence, commit discipline, scope creep detection |
| quality-reviewer | `agents/quality-reviewer.md` | Coordinates the Inline Review Checkpoint's review agents and drives the fix loop — Stage 2 of the three-stage inline review, distinct from the `spec-reviewer`/`spec-compliance-review` spec-matching gates. Dispatched by `agents/orchestrator.md` Phase 3, never directly. |
| refactor-opportunity-review | `agents/refactor-opportunity-review.md` | Post-GREEN refactoring opportunities, semantic vs structural duplication |
| security-review | `agents/security-review.md` | Injection, auth/authz, data exposure, crypto |
| session-analysis | `agents/session-analysis.md` | Maps an aggregated session digest to probable plugin causes and ranked, tagged improvement suggestions (analysis-only) |
| spec-compliance-review | `agents/spec-compliance-review.md` | Spec-to-code matching — general first gate before quality review (final `/code-review` gate; pre-build criteria-verification mode and batched/complex-slice checkpoints in `/build`) |
| spec-reviewer | `agents/spec-reviewer.md` | Spec-to-diff matching for a single freshly-implemented unit — Stage 1 of the three-stage inline review, narrower and diff-scoped vs. `spec-compliance-review`'s broader file-scoped check. Dispatched by `agents/orchestrator.md` Phase 3, never directly. |
| structure-review | `agents/structure-review.md` | SRP violations, DRY, coupling, file organization |
| angular-reactivity-review | `agents/angular-reactivity-review.md` | Angular Zone.js change-detection pitfalls, OnPush + immutability violations, RxJS subscription leaks |
| react-reactivity-review | `agents/react-reactivity-review.md` | React hook rules, stale closures in useEffect, missing dependency arrays, subscription leaks |
| vue-reactivity-review | `agents/vue-reactivity-review.md` | Vue ref/reactive unwrapping pitfalls, watchEffect dependency tracking, subscription leaks |
| test-review | `agents/test-review.md` | Coverage gaps, assertion quality, test hygiene |
| test-smell-review | `agents/test-smell-review.md` | xUnit test smells, test-double selection, test-pyramid layer placement |
| token-efficiency-review | `agents/token-efficiency-review.md` | File/function size, LLM anti-patterns, token usage |

## Color Convention

Every agent declares `color:` (display color in the task list/transcript),
required by this-repo convention on top of the optional official field
(ADR 0027, same category as the `effort: high` convention, ADR 0026).
Derived mechanically, not hand-picked — priority order, capability checked
before naming:

1. `tools:` contains `Agent` (bare or `Agent(...)`) → **purple** (orchestrator).
2. Else `tools:` contains `Edit` or `Write` → **yellow** (changes files).
3. Else name ends `-review` or starts `plan-review-` → **green** (reviewer).
4. Else → **cyan** (all others).

Current fleet: 2 purple, 8 yellow, 32 green, 19 cyan (61 agents total, no
ties). `tests/agents/test_agent_fleet_conventions.py` asserts every agent's
declared `color:` matches the rule; `agent-create`/`agent-add` suggest the
computed value the same way they already do `model:`/`effort:`.

## Skills/Memory Convention

Two more this-repo conventions on top of optional official fields (ADR 0028,
same category as ADR 0026/0027):

- **`skills:`** — any agent with a `## Skills` section in its body must
  declare a matching, non-empty `skills:` preload list, each name traceable
  to that section's own text. No `## Skills` section → omit `skills:`.
- **`memory:`** — any agent with `Edit`/`Write` in `tools:` must declare
  exactly `memory: project` (no other value, no omission). Neither tool →
  omit `memory:`.

Current fleet: 12/61 agents carry `skills:`, 9/61 carry `memory: project`.
Same test file as color (`tests/agents/test_agent_fleet_conventions.py`)
asserts both, via pure `classify_skills_declaration()` /
`classify_memory_declaration()` functions; `agent-create`/`agent-add`
suggest-and-confirm both the same way they already do `color:`.

## Skills Registry

Skills are reusable knowledge modules in `.claude/skills/` that agents reference. They define patterns, guidelines, and project structures without being tied to any single agent persona.

| Skill | File | ~Tokens | Used By |
| ------- | ------ | --------- | --------- |
| ADR Tools | `skills/adr-tools/SKILL.md` | ~1,499 | Orchestrator, adr-author, Software Engineer, Architect |
| Artifact Lifecycle | `skills/artifact-lifecycle/SKILL.md` | ~1,044 | Orchestrator, `/artifact-lifecycle` command |
| Autoship | `skills/autoship/SKILL.md` | ~12,757 | Orchestrator, `/autoship` command |
| API Design | `skills/api-design/SKILL.md` | 1,437 | Architect, Software Engineer |
| Apply Test Doubles | `skills/apply-test-doubles/SKILL.md` | ~4,706 | `/apply-test-doubles` command |
| Branch Workflow | `skills/branch-workflow/SKILL.md` | 1,482 | Orchestrator, Software Engineer |
| Browser Testing | `skills/browser-testing/SKILL.md` | 901 | QA Engineer |
| CD Test Architecture | `skills/cd-test-architecture/SKILL.md` | ~9,622 | QA Engineer, Architect, Platform Engineer, Software Engineer |
| CI Debugging | `skills/ci-debugging/SKILL.md` | 1,368 | Platform Engineer, Software Engineer, QA Engineer |
| Claude Setup Review | `skills/claude-setup-review/SKILL.md` | ~1,296 | `/claude-setup-review` command, claude-setup-review |
| Competitive Analysis | `skills/competitive-analysis/SKILL.md` | 2,034 | Orchestrator, Product Manager |
| Context Loading Protocol | `skills/context-loading-protocol/SKILL.md` | 2,331 | Orchestrator |
| Coverage Baseline | `skills/coverage-baseline/SKILL.md` | ~5,115 | `/test-improve` (Phase 2), QA Engineer, Platform Engineer |
| Coverage Delta | `skills/coverage-delta/SKILL.md` | ~3,852 | `/test-improve` (Phase 5), QA Engineer |
| Design Doc | `skills/design-doc/SKILL.md` | 1,118 | Architect, Product Manager, Orchestrator |
| Design Interrogation | `skills/design-interrogation/SKILL.md` | 1,027 | Architect, Product Manager, Orchestrator |
| Design It Twice | `skills/design-it-twice/SKILL.md` | 1,025 | Architect, Software Engineer |
| Docker Image Audit | `skills/docker-image-audit/SKILL.md` | 2,298 | Orchestrator (inline review), Platform Engineer, Security Engineer |
| Docker Image Create | `skills/docker-image-create/SKILL.md` | 2,011 | Platform Engineer, Software Engineer |
| Domain Analysis | `skills/domain-analysis/SKILL.md` | 2,782 | Architect, Product Manager, Orchestrator |
| Domain-Driven Design | `skills/domain-driven-design/SKILL.md` | 2,681 | Architect, Software Engineer, Product Manager |
| Exploratory Testing | `skills/exploratory-testing/SKILL.md` | ~1,851 | QA Engineer, `/explore` command |
| Farley Score | `skills/farley-score/SKILL.md` | 2,643 | QA Engineer, `/build` (final branch score), `/test-design` (all existing tests; reached by `/test-health` via `/test-design`) |
| Feature File Validation | `skills/feature-file-validation/SKILL.md` | 933 | test-review, QA Engineer, spec-compliance-review |
| Feedback & Learning | `skills/feedback-learning/SKILL.md` | 4,780 | Orchestrator |
| Gherkin Derive | `skills/gherkin-derive/SKILL.md` | ~9,085 | `/test-improve` (Phase 3, conditional), QA Engineer, standalone |
| Gherkin Public | `skills/gherkin-public/SKILL.md` | ~3,749 | Standalone worker; QA Engineer, Product Manager |
| Governance & Compliance | `skills/governance-compliance/SKILL.md` | 1,770 | QA Engineer, Technical Writer |
| Handoff | `skills/handoff/SKILL.md` | 1,921 | Orchestrator |
| Hexagonal Architecture | `skills/hexagonal-architecture/SKILL.md` | 1,035 | Architect, Software Engineer |
| Human Oversight Protocol | `skills/human-oversight-protocol/SKILL.md` | 2,900 | Orchestrator, Product Manager |
| Issues from Assessment | `skills/issues-from-assessment/SKILL.md` | ~3,243 | `/test-improve` (Phase 4), QA Engineer |
| Legacy Code | `skills/legacy-code/SKILL.md` | 2,326 | Software Engineer, QA Engineer, Architect |
| Long Eval | `skills/long-eval/SKILL.md` | ~1,543 | QA Engineer, `/long-eval` command, standalone |
| Mermaid Diagramming | `skills/mermaid-diagramming/SKILL.md` | ~1,557 | Architect, Software Engineer, Tech Writer |
| Mutation Night-Watch | `skills/mutation-night-watch/SKILL.md` | ~2,000 | `/mutation-night-watch` command, QA Engineer, standalone |
| Mutation Testing | `skills/mutation-testing/SKILL.md` | 9,466 | QA Engineer, Software Engineer |
| Performance Benchmark | `skills/performance-benchmark/SKILL.md` | 1,406 | QA Engineer, Platform Engineer, `/benchmark` command |
| Performance Metrics | `skills/performance-metrics/SKILL.md` | 3,109 | Orchestrator |
| Proxy Resilience | `skills/proxy-resilience/SKILL.md` | ~1,024 | All agents (any session running against a corporate Anthropic proxy) |
| Quality Gate Pipeline | `skills/quality-gate-pipeline/SKILL.md` | 2,557 | All agents |
| Quality Targets Converge | `skills/quality-targets-converge/SKILL.md` | ~5,540 | `/test-improve` (Phase 8), QA Engineer, Software Engineer |
| Semantic Duplication Scan | `skills/semantic-duplication-scan/SKILL.md` | ~3,163 | Orchestrator, Software Engineer, Architect |
| Specs | `skills/specs/SKILL.md` | ~4,553 | Product Manager, Architect, QA Engineer, Orchestrator |
| Static Analysis Integration | `skills/static-analysis-integration/SKILL.md` | 3,792 | Orchestrator, `/code-review` |
| Stryker xunit.v2 Shim | `skills/stryker-xunit-v2-shim/SKILL.md` | ~3,945 | `/mutation-testing`, `/test-improve` (mutation on .NET/xunit.v3), QA Engineer, standalone |
| Systematic Debugging | `skills/systematic-debugging/SKILL.md` | 2,129 | Software Engineer, QA Engineer |
| Test Audit + Disable | `skills/test-audit-disable/SKILL.md` | ~1,619 | Standalone worker; QA Engineer |
| Test Design Advisor | `skills/test-design-advisor/SKILL.md` | ~4,235 | QA Engineer, Software Engineer, `/test-design` command |
| Test Health | `skills/test-health/SKILL.md` | ~3,709 | QA Engineer, `/test-health` command |
| Test Improve | `skills/test-improve/SKILL.md` | ~3078 | Orchestrator, QA Engineer, `/test-improve` command |
| Test-Driven Development | `skills/test-driven-development/SKILL.md` | 2,590 | Software Engineer, QA Engineer, Orchestrator |
| Threat Modeling | `skills/threat-modeling/SKILL.md` | 1,420 | Security Engineer, Architect |
| Ubiquitous Language | `skills/ubiquitous-language/SKILL.md` | ~2,199 | Architect, domain-review, Product Manager |

## Knowledge Files

Knowledge files in `knowledge/` provide progressive disclosure — agents read them on demand during analysis rather than carrying all detection patterns inline.

| Name | File | ~Tokens | Used By |
| ------ | ------ | --------- | --------- |
| Adversarial Review Protocol | `knowledge/adversarial-review-protocol.md` | ~2,589 | all 26 review agents (a11y-review, ai-provenance-review, angular-reactivity-review, arch-review, claude-setup-review, complexity-review, component-architecture-review, concurrency-review, correctness-review, data-flow-tracer, doc-review, domain-review, js-fp-review, naming-review, performance-review, progress-guardian, react-reactivity-review, refactor-opportunity-review, security-review, session-analysis, spec-compliance-review, structure-review, test-review, test-smell-review, token-efficiency-review, vue-reactivity-review) |
| Agent Registry | `knowledge/agent-registry.md` | 5,543 | Orchestrator (routing decisions) |
| Shared Review Methodology | `knowledge/agent-review-methodology.md` | ~1,052 | correctness-review, naming-review |
| Architecture Assessment | `knowledge/architecture-assessment.md` | 1,187 | arch-review |
| CD Maturity Model | `knowledge/cd-maturity-model.md` | ~1,104 | Platform Engineer, QA Engineer |
| CD Test Architecture | `knowledge/cd-test-architecture.md` | ~4,338 | cd-test-architecture, test-design-advisor |
| Component Test Patterns | `knowledge/component-test-patterns.md` | ~4,444 | cd-test-architecture |
| Database Change Management | `knowledge/database-change-management.md` | ~1,246 | Software Engineer, Architect, arch-review, `/plan` |
| Decision Defaults | `knowledge/decision-defaults.md` | ~1,287 | Orchestrator, Product Manager, `/plan` (approach contract) |
| Deployment Pipeline | `knowledge/deployment-pipeline.md` | ~1,308 | Platform Engineer |
| Task Size Classifier | `knowledge/task-size-classifier.md` | ~1,067 | Orchestrator (Task Size Gate, no-plan fast path routing) |
| Design Smells | `knowledge/design-smells.md` | ~2,115 | structure-review, complexity-review, naming-review |
| Domain Modeling | `knowledge/domain-modeling.md` | 1,547 | domain-review |
| Exploratory Testing Field Guide | `knowledge/exploratory-testing-field-guide.md` | ~1,364 | QA Engineer, `skills/exploratory-testing/SKILL.md` |
| Failure Routing | `knowledge/failure-routing.md` | ~600 | `/build` (step 4 repair iterations), `/apply-fixes` (step 4 annotation) |
| Fixture Construction | `knowledge/fixture-construction.md` | ~1,260 | test-design-advisor, test-smell-review, test-review |
| Frontend Component Architecture | `knowledge/frontend-component-architecture.md` | ~1,883 | component-architecture-review, `/frontend-architecture` |
| Microservice Testing | `knowledge/microservice-testing.md` | ~1,837 | test-smell-review, test-design-advisor |
| Object Calisthenics | `knowledge/object-calisthenics.md` | ~1,006 | structure-review, complexity-review |
| OWASP Detection | `knowledge/owasp-detection.md` | 2,176 | security-review |
| Orchestrator Script Implementation | `knowledge/orchestrator-script-implementation.md` | 2,873 | Orchestrator (running or working on `scripts/orchestrator.py`) |
| Three-Phase Workflow | `knowledge/three-phase-workflow.md` | 4,735 | Orchestrator (per-phase detail: persona rosters, conditional dispatch, inline review, wave mechanics) |
| Release Strategies | `knowledge/release-strategies.md` | ~1,155 | Platform Engineer, Architect, `/plan` |
| Result Verification | `knowledge/result-verification.md` | ~1,120 | test-design-advisor, test-review, test-smell-review |
| Review Rubric | `knowledge/review-rubric.md` | 752 | `/code-review` (health scoring) |
| Review Template | `knowledge/review-template.md` | 757 | `/code-review` (report assembly) |
| Test Automation Maturity | `knowledge/test-automation-maturity.md` | ~881 | test-review, test-health |
| Test Cadence Tradeoffs | `knowledge/test-cadence-tradeoffs.md` | ~1000 | Orchestrator (Phase 2, `agents/orchestrator.md`) |
| Test Doubles | `knowledge/test-doubles.md` | ~2,155 | test-smell-review, test-design-advisor |
| Test File Indicators | `knowledge/test-file-indicators.md` | ~284 | test-review, test-smell-review, `/test-design`, `/build` |
| Test Layer Gates | `knowledge/test-layer-gates.md` | ~622 | test-design-advisor |
| Test Matrix Examples | `knowledge/test-matrix-examples/*.md` | ~950 | test-design-advisor (few-shot templates) |
| Test Organization | `knowledge/test-organization.md` | ~1,017 | test-design-advisor, test-smell-review |
| Test Pyramid | `knowledge/test-pyramid.md` | ~1,624 | test-smell-review, test-review, test-design-advisor, test-health |
| Test Refactoring | `knowledge/test-refactoring.md` | ~1,086 | test-design-advisor, test-smell-review |
| Test Review Division of Labor | `knowledge/test-review-division-of-labor.md` | ~1,230 | test-review, test-smell-review, `/test-design` |
| Test Smells | `knowledge/test-smells.md` | ~2,261 | test-smell-review, test-review, test-design-advisor |
| Test Stack Profiles | `knowledge/test-stack-profiles/*.md` | ~1,400 | test-design-advisor (tool resolution by detected stack) |
| Test Strategy | `knowledge/test-strategy.md` | ~1,617 | test-design-advisor, test-smell-review, test-review |
| Testability Patterns | `knowledge/testability-patterns.md` | ~3,326 | test-review, test-smell-review, test-design-advisor, legacy-code |
| Testing Quadrants | `knowledge/testing-quadrants.md` | ~723 | test-health, test-design-advisor |
| Testing Techniques | `knowledge/testing-techniques/*.md` | ~1,300 | test-design-advisor (overlay, on trigger), security-review |

## Agent Templates

Language-specific review agents in `templates/agents/`. Scaffolded into projects by `/setup` when the matching stack is detected. Not bundled as always-on.

| Template | File | Activates When |
| ---------- | ------ | --------------- |
| angular-testing | `templates/agents/angular-testing.md` | Angular in deps |
| csharp-quality | `templates/agents/csharp-quality.md` | C#/.NET stack |
| esm-enforcer | `templates/agents/esm-enforcer.md` | Any JS/TS project (always-on) |
| front-end-testing | `templates/agents/front-end-testing.md` | Any frontend framework |
| go-quality | `templates/agents/go-quality.md` | Go stack |
| python-quality | `templates/agents/python-quality.md` | Python stack |
| react-testing | `templates/agents/react-testing.md` | React in deps |
| ts-enforcer | `templates/agents/ts-enforcer.md` | TypeScript detected |
| twelve-factor-audit | `templates/agents/twelve-factor-audit.md` | Service/API project |
