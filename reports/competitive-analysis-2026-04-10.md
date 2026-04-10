# Competitive Analysis: agentic-dev-team vs gstack

**Date**: 2026-04-10
**Target**: gstack by Garry Tan — https://github.com/garrytan/gstack
**Source type**: URL

## Executive Summary

gstack is a 23+ skill Claude Code toolkit focused on the full product delivery lifecycle (Think → Plan → Build → Review → Test → Ship → Reflect) with strong emphasis on design systems, browser-based QA, multi-host AI support, and post-deploy monitoring. Compared to agentic-dev-team, gstack has **7 notable gaps we should examine** — primarily in design workflows, deployment/operations tooling, multi-AI-host support, retrospective/metrics visibility, and parallel sprint orchestration. However, agentic-dev-team is significantly stronger in structured code review (19 specialized review agents vs. 1), domain-driven design, context management, and the formal Research → Plan → Implement workflow with human gates.

## Capability Comparison

### Planning & Strategy

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Product strategy review | `/specs` (collaborative spec workflow) | `/office-hours` (YC mentor forcing questions) | Different approach |
| Executive scope review | — | `/plan-ceo-review` (CEO/Founder perspective, 4 modes) | Missing |
| Engineering plan review | `/plan` (structured TDD plan) | `/plan-eng-review` (architecture, data flows, edge cases) | Different approach |
| Design plan review | — | `/plan-design-review` (0-10 dimension scoring, AI slop detection) | Missing |
| DX plan review | — | `/plan-devex-review` (20-45 forcing questions) | Missing |
| Design interrogation | `/design-interrogation` (stress-test plans) | — | Stronger |
| Design It Twice | `/design-it-twice` (parallel interface alternatives) | — | Stronger |

### Design & UI

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Design system creation | UI/UX Designer agent (advisory) | `/design-consultation` (full design system from research) | Weaker |
| Mockup generation | — | `/design-shotgun` (4-6 variants, iterative feedback) | Missing |
| Design-to-HTML conversion | — | `/design-html` (production HTML, 30KB, zero deps) | Missing |
| Design review | UI/UX Designer agent | `/design-review` (audit + atomic fix commits) | Weaker |
| A11y review | `a11y-review` agent (WCAG 2.1 AA) | — | Stronger |

### Code Review & Quality

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Code review breadth | 19 specialized review agents | `/review` (single staff engineer persona) | Stronger |
| Spec compliance checking | `spec-compliance-review` agent | — | Stronger |
| Domain boundary review | `domain-review` agent | — | Stronger |
| Architecture review | `arch-review` agent | — | Stronger |
| Security review | `security-review` + OWASP detection patterns | `/cso` (OWASP Top 10 + STRIDE, zero false positives) | Different approach |
| Naming review | `naming-review` agent | — | Stronger |
| Performance review | `performance-review` agent | — | Stronger |
| Concurrency review | `concurrency-review` agent | — | Stronger |
| JS functional patterns | `js-fp-review` agent | — | Stronger |
| Test quality review | `test-review` + Test Design Reviewer skill | — | Stronger |
| Static analysis integration | Semgrep + ESLint pre-pass | — | Stronger |
| Model routing for reviews | Orchestrator routing table (haiku/sonnet/opus) | — | Stronger |

### Testing & QA

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Browser-based QA | `/browse` (Playwright patterns) | `/qa` (browser testing + atomic commits + regression) | Weaker |
| QA without code changes | — | `/qa-only` (report-only mode) | Missing |
| TDD enforcement | TDD skill (RED-GREEN-REFACTOR gates) | — | Stronger |
| Mutation testing | `/mutation-testing` (Stryker/pitest/mutmut) | — | Stronger |
| Feature file validation | Feature File Validation skill (Gherkin) | — | Stronger |
| Performance benchmarking | — | `/benchmark` (Core Web Vitals, resource sizing, trends) | Missing |

### Deployment & Operations

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| PR creation workflow | `/pr` (quality gates → PR) | `/ship` (sync, test, coverage audit, PR) | Different approach |
| Merge + deploy | — | `/land-and-deploy` (merge, CI/CD wait, prod verification) | Missing |
| Post-deploy monitoring | — | `/canary` (console errors, perf regression, visual diff) | Missing |
| Release documentation | Tech Writer agent (verify docs current) | `/document-release` (auto-update docs to match shipped code) | Different approach |
| CI debugging | CI Debugging skill | — | Stronger |

### Browser & Tooling

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Browser automation | Playwright skill (patterns only) | GStack Browser (anti-bot stealth, sidebar, cookie import) | Weaker |
| Cookie/auth management | — | `/setup-browser-cookies` (Chrome, Arc, Brave, Edge import) | Missing |
| Multi-AI-host support | Claude Code only | 8 hosts (Claude, Codex, Cursor, Kiro, OpenCode, Slate, Factory, OpenClaw) | Missing |
| Cross-model second opinion | — | `/codex` (OpenAI Codex CLI independent review) | Missing |
| Multi-agent browser sharing | — | `/pair-agent` (tab isolation, scoped tokens, attribution) | Missing |

### Retrospectives & Metrics

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Engineering retrospectives | — | `/retro` (weekly retros, per-person metrics, velocity trends) | Missing |
| Performance metrics logging | Performance Metrics skill (JSONL) | — | Different approach |
| Persistent learnings DB | Feedback & Learning skill | `/learn` (patterns, preferences, pitfalls) | Different approach |

### Orchestration & Context

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Multi-phase workflow | Research → Plan → Implement (with human gates) | Think → Plan → Build → Review → Test → Ship → Reflect | Different approach |
| Context management | Context Loading Protocol + Summarization (40% rule) | — | Stronger |
| Parallel sprint orchestration | — | Conductor (10-15 parallel Claude sessions) | Missing |
| Phase progress persistence | `memory/` progress files | — | Stronger |
| Human review gates | Explicit gates between each phase | — | Stronger |

### Domain & Architecture

| Capability | agentic-dev-team | gstack | Classification |
|-----------|-----------------|--------|----------------|
| Domain-Driven Design | Full DDD skill + domain-review agent | — | Stronger |
| Domain Analysis | `/domain-analysis` (bounded contexts, event flows) | — | Stronger |
| Hexagonal Architecture | Hexagonal Architecture skill | — | Stronger |
| API Design | Contract-first API Design skill | — | Stronger |
| ADR management | ADR Author agent | — | Stronger |
| Threat modeling | STRIDE Threat Modeling skill | — | Stronger |

## Gap Specs

### Gap: Design Mockup Generation

**Classification**: Missing
**Layer**: Skill
**Priority**: Medium

**What gstack does**:
`/design-shotgun` generates 4-6 visual mockup variants from a design brief, then runs an iterative feedback loop to refine the chosen direction. `/design-html` then converts the approved mockup to production-ready HTML (30KB, zero external dependencies).

**Proposed addition**:
- **Type**: skill
- **File**: `skills/design-mockup/SKILL.md`
- **Description**: Generate multiple visual mockup variants as HTML files, score them against design dimensions, and convert the winner to production-ready markup. Would extend the existing UI/UX Designer agent with generative capabilities rather than just advisory review.
- **Dependencies**: UI/UX Designer agent, Browser Testing skill (for visual verification)
- **Estimated complexity**: Medium
- **Model tier**: opus (design judgment requires frontier reasoning)

### Gap: Post-Deploy Monitoring (Canary)

**Classification**: Missing
**Layer**: Skill + Command
**Priority**: High

**What gstack does**:
`/canary` monitors a live application after deployment — captures console errors, checks for performance regressions against baselines, validates page health, and takes screenshot diffs to detect visual anomalies. Runs a 7-phase workflow from baseline capture through continuous monitoring to health report.

**Proposed addition**:
- **Type**: skill + command
- **File**: `skills/canary-monitoring/SKILL.md`, `commands/canary.md`
- **Description**: Post-deploy smoke testing and monitoring. Uses Playwright to load key pages, capture console errors, measure performance metrics against baselines, and screenshot-diff for visual regressions. Produces a health report. Integrates with the Branch Workflow skill as a post-merge step.
- **Dependencies**: Browser Testing skill, DevOps/SRE Engineer agent
- **Estimated complexity**: Large
- **Model tier**: sonnet

### Gap: Performance Benchmarking

**Classification**: Missing
**Layer**: Skill + Command
**Priority**: Medium

**What gstack does**:
`/benchmark` tracks Core Web Vitals, page load times, resource sizes, and performance budgets across PRs. Maintains trend data for historical comparison and identifies bottleneck assets.

**Proposed addition**:
- **Type**: skill + command
- **File**: `skills/performance-benchmark/SKILL.md`, `commands/benchmark.md`
- **Description**: Capture and track frontend performance metrics (Core Web Vitals, resource sizes, load times) against defined budgets. Compare current state to baselines, flag regressions, and maintain trend history. Complements the existing `performance-review` agent which focuses on code-level issues rather than runtime metrics.
- **Dependencies**: Browser Testing skill, DevOps/SRE Engineer agent
- **Estimated complexity**: Medium
- **Model tier**: sonnet

### Gap: Engineering Retrospectives

**Classification**: Missing
**Layer**: Skill + Command
**Priority**: Medium

**What gstack does**:
`/retro` analyzes git history to compute commit velocity, work session patterns, code hotspots, PR sizing distribution, focus scores, and per-person breakdowns. Compares week-over-week trends and maintains a persistent learnings database. Supports both single-project and global (cross-repo) modes.

**Proposed addition**:
- **Type**: skill + command
- **File**: `skills/retro/SKILL.md`, `commands/retro.md`
- **Description**: Weekly engineering retrospective that analyzes git history, computes shipping velocity metrics, identifies work patterns, and produces a narrative report with trends. Would complement the existing Performance Metrics skill (which tracks per-task AI metrics) with team-level engineering health metrics.
- **Dependencies**: Performance Metrics skill, git history access
- **Estimated complexity**: Medium
- **Model tier**: sonnet

### Gap: Merge + Deploy Workflow

**Classification**: Missing
**Layer**: Skill
**Priority**: High

**What gstack does**:
`/land-and-deploy` handles post-PR merge: merges the PR, waits for CI/CD to complete, then verifies production deployment succeeded. Closes the loop from code to running production.

**What we have now**:
The Branch Workflow skill handles PR creation and merge strategy selection but stops at merge. There's no post-merge CI monitoring or production verification step.

**Proposed addition**:
- **Type**: skill extension
- **File**: Update `skills/branch-workflow/SKILL.md` to add a "Land & Verify" phase
- **Description**: Extend Branch Workflow with post-merge steps: monitor CI/CD pipeline completion, verify deployment status, and optionally trigger canary monitoring. This closes the gap between "PR merged" and "confirmed working in production."
- **Dependencies**: Branch Workflow skill, CI Debugging skill (for failure diagnosis), proposed Canary skill
- **Estimated complexity**: Medium
- **Model tier**: sonnet

### Gap: Multi-AI-Host Support

**Classification**: Missing
**Layer**: Workflow
**Priority**: Low

**What gstack does**:
The `hosts/` directory provides typed configurations for 8 AI coding tools (Claude, Codex, Cursor, Kiro, OpenCode, Slate, Factory, OpenClaw). Skills are portable across hosts. `/pair-agent` enables multiple AI tools to share a browser with tab isolation and scoped tokens.

**Proposed addition**:
- **Type**: architecture consideration (not a single file)
- **Description**: Currently agentic-dev-team is tightly coupled to Claude Code's plugin system. Multi-host support would require abstracting skill definitions to be host-agnostic. This is a large architectural decision — worth examining whether the market demands it, but not an immediate priority since our plugin system integration is a strength for Claude Code users.
- **Dependencies**: Would require rethinking the plugin manifest and command system
- **Estimated complexity**: Large
- **Model tier**: N/A (architectural)

### Gap: QA Report-Only Mode

**Classification**: Missing
**Layer**: Command
**Priority**: Low

**What gstack does**:
`/qa-only` runs the full QA browser testing suite but produces a bug report without making any code changes. Useful for auditing existing state without modification.

**Proposed addition**:
- **Type**: command flag
- **File**: Update `commands/browse.md` or add `commands/qa-report.md`
- **Description**: Add a `--report-only` mode to browser testing that captures screenshots, logs errors, and produces a structured report without writing any fixes. Minimal implementation — mostly about constraining the existing QA workflow.
- **Dependencies**: Browser Testing skill
- **Estimated complexity**: Small
- **Model tier**: sonnet

### Gap: Plan Review Personas (CEO, Design, DX)

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What gstack does**:
Provides 4 distinct plan review lenses: CEO/Founder (strategic scope), Engineering Manager (architecture), Senior Designer (design dimensions), and DX Lead (developer experience). Each applies a different set of forcing questions.

**What we have now**:
The `/plan` command with automated `plan-reviewer.md` pre-check and the Design Interrogation skill. The plan reviewer checks completeness and consistency but doesn't apply distinct strategic lenses.

**Proposed addition**:
- **Type**: subagent prompt templates
- **Files**: `prompts/plan-review-strategic.md`, `prompts/plan-review-design.md`, `prompts/plan-review-dx.md`
- **Description**: Additional plan review lenses that complement the existing technical plan reviewer. Strategic review questions scope and business value. Design review scores UX dimensions. DX review audits developer ergonomics. Each runs as a parallel sub-agent during plan review.
- **Dependencies**: Existing plan-reviewer.md template, Plan skill
- **Estimated complexity**: Small
- **Model tier**: sonnet

## Different Approaches Worth Examining

### Sprint Methodology vs. Phased Workflow

**gstack**: Think → Plan → Build → Review → Test → Ship → Reflect — a linear sprint model optimized for solo builders shipping features fast. Each skill is a standalone step in the pipeline.

**agentic-dev-team**: Research → Plan → Implement with explicit human gates between phases, sub-agent context isolation, and structured progress files. Optimized for correctness and auditability.

**Tradeoff**: gstack's model is faster for small features with a single developer. Our model is better for complex changes where mistakes are expensive. gstack's approach could feel heavyweight for a typo fix but lightweight for an architectural change. Our approach is the inverse. Neither is universally better — the right answer may be to support both modes (fast-track for trivial changes, full pipeline for complex ones). We already have this implicitly (the orchestrator routes trivially), but gstack makes it explicit in their documentation.

### Parallel Sprint Orchestration

**gstack**: Claims to support 10-15 parallel Claude Code sessions via a "Conductor" system. The `conductor.json` config is minimal (just setup/teardown scripts), so the actual orchestration likely lives in the CLI tooling.

**agentic-dev-team**: Uses worktree isolation for parallel independent units within a single session but doesn't orchestrate multiple concurrent Claude Code sessions.

**Tradeoff**: Multi-session orchestration is powerful for large projects but complex to manage correctly (merge conflicts, dependency ordering, integration testing). Our worktree approach is simpler and avoids coordination overhead. The question is whether users need to run 10+ parallel implementation streams — if so, this is worth investigating. If most users work in 1-2 streams, our approach is sufficient.

### Security Approach

**gstack**: `/cso` (Chief Security Officer) — a single comprehensive security persona that combines OWASP Top 10 and STRIDE analysis, claims zero false positives.

**agentic-dev-team**: Separate `security-review` agent (code-level) + Threat Modeling skill (design-level) + OWASP detection knowledge file + pre-tool-guard hook (file protection). Layered defense.

**Tradeoff**: gstack's unified approach is simpler to invoke. Our layered approach catches more because different layers fire at different times (design vs. code vs. runtime). The "zero false positives" claim from gstack is aspirational but unprovable — our approach of confidence-based filtering is more honest. Keep our approach.

## Our Strengths

- **Review depth**: 19 specialized review agents vs. 1 generalist reviewer — fundamentally different coverage model
- **Model routing**: Cost-optimized routing table (haiku for simple checks, opus for security/domain) — gstack doesn't mention model routing
- **Context management**: Formal 40% utilization ceiling, context loading protocol, and summarization — gstack doesn't address context window limits
- **Domain engineering**: Full DDD support (domain analysis, domain review, hexagonal architecture, API design, ADR management) — gstack has no domain modeling capabilities
- **Human oversight**: Explicit gates between phases with structured handoff — gstack is more autonomous (which can be a weakness for high-stakes changes)
- **TDD enforcement**: Hard RED-GREEN-REFACTOR gates — gstack mentions tests but doesn't enforce the cycle
- **Mutation testing**: Validates test suite quality — gstack has no equivalent
- **Static analysis integration**: Semgrep/ESLint pre-pass deduplicates before AI review — gstack relies purely on AI review
- **Plugin architecture**: First-class Claude Code plugin with manifest, settings, hooks — gstack uses symlinked skill directories
- **Template system**: Language-specific agent templates scaffolded by `/setup` — gstack skills are language-agnostic (strength and weakness)

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1 | Post-Deploy Monitoring (Canary) | Skill + Command | Large | Closes the "ship to production" loop — currently we stop at PR merge. High value for anyone actually deploying. |
| 2 | Merge + Deploy Workflow | Skill extension | Medium | Prerequisite for canary, extends existing Branch Workflow. Quick win that completes the delivery pipeline. |
| 3 | Plan Review Personas | Prompt templates | Small | Low effort, high value — adds strategic/design/DX lenses to plan review. 3 small prompt files. |
| 4 | Engineering Retrospectives | Skill + Command | Medium | Unique value prop from gstack. Git-based metrics and trends give teams visibility into shipping health. Complements our per-task Performance Metrics. |
| 5 | Performance Benchmarking | Skill + Command | Medium | Runtime performance tracking (Core Web Vitals, resource budgets) fills a gap between our code-level performance-review agent and actual user experience metrics. |

## Next Steps

1. **Quick win — Plan Review Personas** (Rank 3): Write 3 prompt templates (`plan-review-strategic.md`, `plan-review-design.md`, `plan-review-dx.md`) and wire them into the plan review phase as optional parallel sub-agents. Estimated: 1-2 hours.

2. **Extend Branch Workflow** (Rank 2): Add a "Land & Verify" phase to the existing Branch Workflow skill — monitor CI completion and verify deployment. This is the foundation for canary monitoring. Estimated: half day.

3. **Build Canary Skill** (Rank 1): Post-deploy monitoring using Playwright. Depends on #2 being complete. Estimated: 1-2 days.

4. **Build Retro Skill** (Rank 4): Git history analysis and weekly reporting. Can be built independently. Estimated: 1 day.

5. **Build Benchmark Skill** (Rank 5): Core Web Vitals and resource tracking. Depends on Browser Testing infrastructure. Estimated: 1 day.

6. **Defer**: Multi-AI-host support (large architectural change, unclear demand), design mockup generation (medium effort, niche use case), QA report-only mode (small but low impact).

7. **Monitor but don't copy**: gstack's parallel sprint orchestration (Conductor) — interesting but our worktree isolation may be sufficient. Revisit if users request it.
