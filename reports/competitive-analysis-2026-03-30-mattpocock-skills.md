# Competitive Analysis: agentic-dev-team vs mattpocock/skills

**Date**: 2026-03-30
**Target**: mattpocock/skills (https://github.com/mattpocock/skills)
**Source type**: URL

## Executive Summary

mattpocock/skills is a collection of 18 standalone Claude Code skills by Matt Pocock, focused on developer workflow — from PRD writing through planning, TDD implementation, and refactoring. The comparison reveals 5 gaps where Pocock's skills offer capabilities agentic-dev-team lacks or does more weakly, 3 areas with fundamentally different approaches worth examining, and 8 areas where agentic-dev-team is substantially stronger. The top finding: Pocock's skills excel at **interactive, conversational design exploration** (grill-me, design-an-interface, write-a-prd) — a category agentic-dev-team barely touches. Our plugin automates workflows; his interrogates the developer's thinking.

## Capability Comparison

### Planning & Requirements

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| PRD creation via interactive interview | `/specs` produces Intent, BDD scenarios, Architecture notes, Acceptance Criteria — structured but less conversational | `write-a-prd` runs an exhaustive user interview, explores the codebase to verify assertions, then files a GitHub issue with user stories, implementation decisions, and testing decisions | **Weaker** |
| Relentless design interrogation | No equivalent | `grill-me` — walks every branch of a decision tree one question at a time, providing recommended answers, answering its own questions by exploring the codebase when possible | **Missing** |
| PRD to implementation plan | `/plan` creates structured TDD steps from a goal and acceptance criteria | `prd-to-plan` turns a PRD into phased vertical slices with durable architectural decisions, saves to `./plans/`, quizzes user on granularity | **Different approach** |
| PRD to GitHub issues | No equivalent — plans stay as local files or memory artifacts | `prd-to-issues` breaks a PRD into independently-grabbable GitHub issues using vertical slices | **Missing** |

### Interface Design

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Multi-variant interface design | No equivalent | `design-an-interface` spawns 3+ parallel sub-agents with different constraints (minimize methods, maximize flexibility, optimize for common case), presents radically different designs, compares in prose | **Missing** |
| Architecture improvement discovery | `arch-review` checks ADR compliance and layer boundaries; `domain-analysis` assesses DDD health | `improve-codebase-architecture` explores organically for friction, identifies shallow modules, then spawns parallel sub-agents to design deeper alternatives, files as GitHub RFC | **Different approach** |

### Test-Driven Development

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| TDD workflow | `skills/test-driven-development.md` + TDD guard hook enforcing RED-GREEN-REFACTOR hard gates | `tdd` skill with vertical-slice emphasis, anti-pattern warnings against horizontal slicing, bundled reference files for deep modules, mocking, refactoring, and test design | **Different approach** |
| Bug triage with TDD fix plan | `skills/systematic-debugging.md` for debugging; no automatic issue creation | `triage-issue` investigates the codebase hands-off, identifies root cause, creates a GitHub issue with a TDD fix plan of RED-GREEN cycles | **Weaker** |

### Refactoring

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Refactor planning | `refactoring-review` agent identifies post-GREEN refactoring opportunities | `request-refactor-plan` runs user interview, explores codebase, breaks into tiny commits following Martin Fowler's advice, files as GitHub issue | **Weaker** |

### Tooling & Setup

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Pre-commit hooks | `/setup` generates hooks; `pre-tool-guard.sh` and `destructive-guard.sh` | `setup-pre-commit` sets up Husky + lint-staged + Prettier + type checking + tests | **Stronger** |
| Git guardrails | `/careful` toggles destructive command blocking; `/guard` combines with `/freeze` | `git-guardrails-claude-code` blocks dangerous git commands via Claude Code hooks | **Stronger** |

### Code Review & Quality

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Multi-agent code review (19 agents) | 19 specialized review agents with model routing, correction loops, and inline checkpoints | No code review capability | **Stronger** |
| Spec compliance gating | spec-compliance-review checks code against BDD scenarios | No equivalent | **Stronger** |

### Orchestration & Workflow

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Multi-phase workflow (Research → Plan → Implement) | Full three-phase orchestration with human review gates | No orchestration — skills are standalone, invoked one at a time | **Stronger** |
| Context management | 40% utilization ceiling, phased loading, LSTM-inspired summarization | No context management | **Stronger** |
| Model routing | Automatic haiku/sonnet/opus routing per agent | No model routing | **Stronger** |

### Knowledge & Documentation

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| DDD / ubiquitous language | `skills/domain-driven-design.md` + `domain-review` agent + `domain-analysis` skill | `ubiquitous-language` extracts a DDD glossary from conversation | **Stronger** |
| Article editing | No equivalent | `edit-article` restructures sections, improves clarity, tightens prose | **Missing** |
| Obsidian vault management | No equivalent | `obsidian-vault` creates and manages notes with wikilinks and index notes | Not applicable (personal knowledge management, outside plugin scope) |

### GitHub Integration

| Capability | agentic-dev-team | mattpocock/skills | Classification |
|-----------|-----------------|-------------------|----------------|
| Automatic GitHub issue creation from plans | Plans stay as local files; `/pr` creates PRs but no issue creation from specs/plans | `write-a-prd`, `triage-issue`, `request-refactor-plan`, `improve-codebase-architecture` all auto-create GitHub issues | **Weaker** |

## Gap Specs

### Gap: Relentless Design Interrogation (grill-me)

**Classification**: Missing
**Layer**: Skill
**Priority**: High

**What the other plugin does**:
`grill-me` interviews the user about a plan or design, walking every branch of the decision tree one at a time, providing recommended answers for each question, and exploring the codebase to self-answer when possible. It forces the developer to think through decisions they'd otherwise skip.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/design-interrogation.md`
- **Description**: A skill that takes a plan, design doc, or feature spec and systematically interrogates the developer about unresolved decisions, edge cases, and implicit assumptions. Unlike `/specs` which produces artifacts, this skill produces *clarity* — it's a thinking tool, not a documentation tool. Could integrate with the Research phase to stress-test findings before the Plan phase begins.
- **Dependencies**: Orchestrator (Research phase integration), `/specs` (complementary)
- **Estimated complexity**: Small
- **Model tier**: sonnet

### Gap: Parallel Multi-Variant Interface Design

**Classification**: Missing
**Layer**: Skill
**Priority**: Medium

**What the other plugin does**:
`design-an-interface` spawns 3+ parallel sub-agents, each with a different design constraint (minimize methods, maximize flexibility, optimize for common case, ports & adapters). Each produces a radically different interface design. Designs are compared in prose, then the user picks one or synthesizes a hybrid. Based on John Ousterhout's "Design It Twice" principle.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/design-it-twice.md`
- **Description**: A skill that generates multiple radically different interface designs for a module by dispatching parallel sub-agents with divergent constraints. Integrates with the Architect agent during the Research/Plan phases. The key insight is that the first design is rarely the best — forced divergence produces better designs than iterative refinement.
- **Dependencies**: Architect agent, Agent tool (parallel sub-agents)
- **Estimated complexity**: Medium
- **Model tier**: sonnet (sub-agents), opus (synthesis/comparison)

### Gap: PRD to GitHub Issues

**Classification**: Missing
**Layer**: Command
**Priority**: Medium

**What the other plugin does**:
`prd-to-issues` takes a completed PRD and breaks it into independently-grabbable GitHub issues using vertical slices. Each issue is self-contained enough for a different developer (or agent) to pick up.

**Proposed addition**:
- **Type**: command
- **File**: `commands/issues-from-plan.md`
- **Description**: A command that takes a plan (from `/plan` or a design doc) and creates GitHub issues for each implementation step. Each issue includes acceptance criteria, dependencies on other issues, and enough context to be worked independently. This bridges the gap between planning (which we do well) and team-scale execution (which requires ticketing).
- **Dependencies**: `/plan`, `gh` CLI, Orchestrator
- **Estimated complexity**: Medium
- **Model tier**: sonnet

### Gap: Bug Triage with Automatic Issue Creation

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What the other plugin does**:
`triage-issue` takes a bug report, investigates the codebase hands-off (minimal user questions), traces the code path, identifies root cause, and creates a GitHub issue with a TDD fix plan of RED-GREEN cycles. The output is an actionable, self-contained issue — not a conversation.

**What we have now**:
`skills/systematic-debugging.md` guides debugging but produces findings in conversation, not as a filed issue. There's no automatic GitHub issue creation from debugging sessions.

**Proposed addition**:
- **Type**: skill enhancement + command
- **File**: `skills/systematic-debugging.md` (update) + `commands/triage.md`
- **Description**: Extend the debugging skill to optionally create a GitHub issue with root cause analysis and a TDD fix plan when the bug is identified but the fix is deferred. Add a `/triage` command that wraps the workflow: investigate → diagnose → file issue → share URL.
- **Dependencies**: Systematic Debugging skill, `gh` CLI, TDD skill
- **Estimated complexity**: Small
- **Model tier**: sonnet

### Gap: Refactor Plan with Tiny Commits

**Classification**: Weaker
**Layer**: Skill
**Priority**: Low

**What the other plugin does**:
`request-refactor-plan` interviews the developer, explores the codebase, considers alternatives, checks test coverage, then breaks the refactor into the tiniest possible commits — each leaving the codebase in a working state. Filed as a GitHub issue.

**What we have now**:
`refactoring-review` identifies refactoring opportunities after tests pass, but it's reactive (post-implementation) rather than proactive (pre-implementation planning). The `/plan` command can plan refactors but doesn't enforce the "tiny commits" discipline or file issues.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/refactor-planning.md`
- **Description**: A skill for planning large refactors as sequences of tiny, safe commits. Interviews the developer about scope and alternatives, explores test coverage, then produces a commit-by-commit plan where each step is independently verifiable. Can output as a GitHub issue or a local plan file.
- **Dependencies**: Architect agent, QA Engineer agent (test coverage assessment), `gh` CLI
- **Estimated complexity**: Small
- **Model tier**: sonnet

### Gap: Article/Prose Editing

**Classification**: Missing
**Layer**: Skill
**Priority**: Low

**What the other plugin does**:
`edit-article` restructures sections, improves clarity, and tightens prose for written content.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/prose-editing.md`
- **Description**: A writing improvement skill that restructures, clarifies, and tightens prose. Useful for READMEs, blog posts, documentation, and ADRs. The Technical Writer agent could reference it for doc quality beyond just accuracy checking.
- **Dependencies**: Technical Writer agent
- **Estimated complexity**: Small
- **Model tier**: sonnet

## Different Approaches Worth Examining

### PRD → Plan: Vertical Slices vs TDD Steps

**agentic-dev-team** `/plan` produces implementation steps oriented around TDD (RED-GREEN-REFACTOR per step), with acceptance criteria and a pre-PR quality gate. **mattpocock** `prd-to-plan` produces phased vertical slices with durable architectural decisions upfront, each slice cutting through all layers end-to-end.

**Tradeoff**: Our approach is more prescriptive (every step has a test cycle), which enforces quality but can feel rigid for exploratory work. Pocock's approach separates *what to build* from *how to build it* — the plan says "build this vertical slice" and the `tdd` skill handles the how. This is arguably cleaner separation of concerns. Worth considering: should `/plan` focus on vertical slices and leave TDD mechanics to `/build`?

### Architecture Improvement: Review vs Exploration

**agentic-dev-team** `arch-review` checks compliance against existing ADRs and patterns — it's a validator. **mattpocock** `improve-codebase-architecture` explores the codebase organically for *friction*, identifies shallow modules, and proposes deepening refactors — it's a discoverer.

**Tradeoff**: Our approach catches violations of documented decisions. His approach discovers problems that haven't been documented yet. These are complementary — an "architecture exploration" mode that discovers issues, followed by arch-review that validates proposed fixes, would cover both. The "deep modules" framing (from Ousterhout's "A Philosophy of Software Design") is a valuable lens we don't currently use.

### TDD: Hard Gates vs Philosophy

**agentic-dev-team** enforces TDD with a PreToolUse hook (`tdd-guard`) that blocks implementation without a failing test. **mattpocock** teaches TDD philosophy with detailed anti-pattern warnings (horizontal slicing) and bundled reference files for deep modules, mocking, and refactoring.

**Tradeoff**: Our hard gates prevent deviation but can feel mechanical. His approach explains *why* — the anti-pattern documentation ("WRONG: write all tests first, THEN all implementation") is educational and produces developers who understand TDD, not just developers who comply with it. Consider enriching our TDD skill with similar anti-pattern documentation and the "tracer bullet" framing.

## Our Strengths

1. **19 specialized review agents** with automatic model-tiered dispatch — Pocock has zero code review capability
2. **Multi-phase orchestration** (Research → Plan → Implement) with human review gates — Pocock's skills are standalone, no workflow coordination
3. **Context management** (40% ceiling, phased loading, summarization) — no equivalent in Pocock's collection
4. **Model routing** (haiku/sonnet/opus per agent) — Pocock's skills don't control model selection
5. **Spec compliance checking** — first-gate review against BDD scenarios before quality review runs
6. **9 language-specific agent templates** — stack-aware scaffolding via `/setup`
7. **Progressive-disclosure knowledge files** — OWASP detection, domain modeling, architecture assessment loaded on demand
8. **Security depth** — threat modeling skill, security-review agent with OWASP knowledge, Security Engineer agent

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1 | Design Interrogation (grill-me) | Skill | Small | Fills a fundamental gap — we automate workflows but don't challenge thinking. Small to implement, high impact on design quality. Integrates naturally with Research phase. |
| 2 | GitHub Issue Creation from Plans | Command | Medium | Bridges planning (our strength) to team execution. Multiple Pocock skills auto-create issues; we create zero. |
| 3 | Parallel Multi-Variant Interface Design | Skill | Medium | "Design It Twice" is a proven technique we don't offer. Leverages our existing sub-agent infrastructure. |
| 4 | Bug Triage with Issue Creation | Skill + Command | Small | Quick extension of existing debugging skill. The pattern (investigate → file issue) is a natural complement to our systematic debugging. |
| 5 | TDD Anti-Pattern Documentation | Skill (update) | Small | Enriching our TDD skill with vertical-slice framing and anti-pattern warnings would improve developer education at near-zero cost. |

## Next Steps

1. **Quick win — grill-me equivalent**: Write `skills/design-interrogation.md`. This is a small, self-contained skill (~200 lines) that adds a new *category* of capability. Wire it into the Research phase as an optional step before planning.
2. **Quick win — TDD enrichment**: Add anti-pattern documentation and the "tracer bullet" framing to `skills/test-driven-development.md`. Reference Pocock's vertical-slice rules. No new files needed.
3. **GitHub issue creation**: Design a `/triage` command and an `/issues-from-plan` command. These share a common pattern (produce artifact → file via `gh issue create`) and could be built together.
4. **Design-it-twice skill**: Build `skills/design-it-twice.md` with parallel sub-agent dispatch. This skill would be used by the Architect agent and naturally fits the Research phase.
5. **Explore the "deep modules" framing**: Pocock's skills consistently reference Ousterhout's "A Philosophy of Software Design" for identifying architectural improvement opportunities. Consider adding a knowledge file `knowledge/deep-modules.md` that the Architect and arch-review agents can reference.
