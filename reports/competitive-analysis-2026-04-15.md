# Competitive Analysis: agentic-dev-team vs superpowers

**Date**: 2026-04-15
**Target**: [obra/superpowers](https://github.com/obra/superpowers) (v5.0.7, 431 commits, MIT license)
**Source type**: URL
**Author of target**: Jesse Vincent

## Executive Summary

superpowers is a focused, workflow-discipline plugin targeting 6 agent platforms (Claude Code, Cursor, Codex, OpenCode, Gemini CLI, GitHub Copilot CLI). It has 14 skills, 1 agent, and 3 deprecated commands. agentic-dev-team is broader (60+ capabilities across all SDLC phases) but narrower in platform support (Claude Code only). The key finding: superpowers excels at **depth per skill** — anti-rationalization techniques, pressure-tested documentation, and a novel "TDD for skills" authoring methodology — while agentic-dev-team excels at **breadth of coverage** across the full development lifecycle. There are 5 actionable gaps where superpowers does something we don't or does it better.

## Capability Comparison

### Workflow / Orchestration

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Design-before-code gate | `/specs` + `/design-doc` + `/design-interrogation` | `brainstorming` skill with visual companion + spec reviewer subagent | Different approach |
| Implementation planning | `/plan` command | `writing-plans` skill with 2-5 min task decomposition | Different approach |
| Subagent orchestration | Orchestrator agent with model routing table | `subagent-driven-development` skill with 4 status codes (DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED) | Different approach |
| Plan execution | `/build` command with TDD | `executing-plans` (inline) + `subagent-driven-development` (parallel) | Different approach |
| Code review | `/code-review` with 19 specialized review agents + static analysis pre-pass | Single `code-reviewer` agent with 2-stage subagent review (spec then quality) | Stronger |
| Branch completion | `/pr` command with quality gates | `finishing-a-development-branch` with 4 options (merge/push+PR/keep/discard) | Stronger |
| Session continuity | `/continue` with memory-based phase progress files | None | Stronger |
| Git worktree workflow | `isolation: "worktree"` on subagent calls | Dedicated `using-git-worktrees` skill with language-specific setup (npm/cargo/pip/go) | Weaker |
| Visual design companion | None | `visual-companion.md` — browser-based mockup server with HTML hot-reload and JSON event recording | Missing |

### Discipline / Behavioral Constraints

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| TDD enforcement | `test-driven-development` skill with RED-GREEN-REFACTOR | `test-driven-development` skill with "Iron Law" (delete code written before tests), 13 red flags, rationalization table, testing anti-patterns reference | Weaker |
| Verification before completion | `quality-gate-pipeline` skill (3-phase) | `verification-before-completion` skill citing "24 failure memories" as motivation | Different approach |
| Code review reception | No equivalent | `receiving-code-review` — forbids performative agreement, requires technical verification before implementing suggestions, mandates pushback when feedback is wrong | Missing |
| Anti-rationalization techniques | None | Embedded across skills — Cialdini-cited rationalization tables, pressure scenarios, explicit "this is what rationalization sounds like" examples | Missing |
| Destructive command protection | `/careful`, `/freeze`, `/guard` commands | None | Stronger |

### Review / Quality

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Specialized review agents | 19 agents (security, a11y, arch, domain, naming, complexity, concurrency, etc.) | 1 code-reviewer agent | Stronger |
| Static analysis integration | Semgrep + ESLint pre-pass via `/semgrep-analyze` | None | Stronger |
| Mutation testing | `/mutation-testing` with Stryker/pitest/mutmut | None | Stronger |
| Test design quality scoring | Test Design Reviewer with Farley Score | None | Stronger |
| Review agent eval framework | `/agent-eval` with fixtures and grading | None | Stronger |

### Architecture / Design

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Domain-driven design | DDD skill + domain analysis + domain-review agent | None | Stronger |
| Hexagonal architecture | Dedicated skill + arch-review agent | None | Stronger |
| Threat modeling / STRIDE | Dedicated skill + security-engineer agent | None | Stronger |
| API design | Contract-first skill | None | Stronger |
| Design alternatives | `/design-it-twice` | None | Stronger |

### Infrastructure / DevOps

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Docker image creation/audit | Two dedicated skills | None | Stronger |
| CI debugging | Dedicated skill | None | Stronger |
| Performance benchmarking | `/benchmark` with Core Web Vitals | None | Stronger |

### Meta / Authoring

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Skill/agent authoring guide | `agent-skill-authoring` skill + `/agent-add` scaffold | `writing-skills` skill — TDD for docs, Claude Search Optimization (CSO), pressure scenario methodology, rationalization bulletproofing | Weaker |
| Plugin self-audit | `/agent-audit` + `/harness-audit` | None | Stronger |
| Skill triggering methodology | Skill descriptions in command frontmatter | CSO guidance — key finding: "summarizing workflow in descriptions causes Claude to skip reading the actual skill content" | Weaker |

### Platform Support

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Claude Code | Full support | Full support | — |
| Cursor | None | Full adapter + hooks-cursor.json | Missing |
| Codex / OpenAI | None | Full adapter + AGENTS.md + INSTALL.md | Missing |
| OpenCode | None | Full adapter + INSTALL.md | Missing |
| Gemini CLI | None | Extension manifest + GEMINI.md | Missing |
| GitHub Copilot CLI | None | Supported | Missing |
| Windows | Assumed (no special handling) | Explicit Windows support with run-hook.cmd wrapper | Weaker |

### Debugging

| Capability | agentic-dev-team | superpowers | Classification |
|-----------|-----------------|----------|----------------|
| Systematic debugging | `systematic-debugging` skill (4-phase) | `systematic-debugging` skill with 6 supporting files: root-cause-tracing, defense-in-depth, condition-based-waiting (with example), find-polluter.sh | Weaker |

## Gap Specs

### Gap: Anti-Rationalization Techniques

**Classification**: Missing
**Layer**: Skill / Knowledge
**Priority**: High

**What superpowers does**:
Embeds anti-rationalization tables throughout skills — explicit examples of what rationalization sounds like ("I'll just write this small helper first", "The test is basically the same as..."), Cialdini-cited persuasion patterns, and pressure scenarios that test whether skills hold up under common LLM failure modes. This is their core innovation — treating LLM behavioral drift as a first-class problem.

**Proposed addition**:
- **Type**: knowledge file + skill enhancement
- **File**: `knowledge/anti-rationalization.md` + updates to `skills/test-driven-development/SKILL.md` and `skills/quality-gate-pipeline/SKILL.md`
- **Description**: Create a shared knowledge file of rationalization patterns specific to LLM agents (skipping tests, claiming completion without verification, writing implementation before tests, expanding scope). Embed "this is what rationalization sounds like" examples in the TDD and Quality Gate skills. Add a "pressure scenarios" section to skill authoring guidance.
- **Dependencies**: TDD skill, Quality Gate Pipeline skill, Agent & Skill Authoring skill
- **Estimated complexity**: Small
- **Model tier**: N/A (documentation only)

### Gap: Code Review Reception Discipline

**Classification**: Missing
**Layer**: Skill
**Priority**: High

**What superpowers does**:
The `receiving-code-review` skill explicitly forbids performative agreement ("You're absolutely right!"), requires the agent to technically verify suggestions before implementing them, mandates pushback with reasoning when feedback is wrong, and includes a YAGNI check. This addresses a known LLM failure mode: blindly accepting all review feedback without critical evaluation.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/receiving-code-review/SKILL.md`
- **Description**: Define behavioral constraints for how agents respond to code review findings (from `/code-review` or human feedback). Require technical verification before implementing suggestions. Forbid performative agreement. Mandate reasoned pushback when a suggestion would make the code worse. Include a YAGNI gate to prevent gold-plating in response to reviews.
- **Dependencies**: `/apply-fixes` command, Quality Gate Pipeline
- **Estimated complexity**: Small
- **Model tier**: N/A (behavioral constraint, loaded into any agent receiving review)

### Gap: Skill Authoring — TDD for Docs & Claude Search Optimization

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What superpowers does**:
The `writing-skills` skill applies TDD to skill documentation: write pressure scenarios, test whether the skill holds up under adversarial conditions, iterate. It also documents a key finding called "Claude Search Optimization" (CSO) — when a skill description summarizes the workflow, Claude may follow the description instead of reading the full skill content. This means descriptions should state *when* to use the skill, not *how* it works.

**What we have now**:
`agent-skill-authoring` skill covers structure, frontmatter format, and registration. It lacks pressure testing methodology and has no guidance on description optimization for skill discovery.

**Proposed addition**:
- **Type**: skill enhancement
- **File**: Update `skills/agent-skill-authoring/SKILL.md`
- **Description**: Add two sections: (1) "Pressure Testing" — how to write adversarial scenarios that probe whether a skill's instructions hold up under common LLM drift patterns, (2) "Description Optimization" — guidance that skill descriptions should specify *when* to trigger, not *how* the skill works, to prevent Claude from using the description as a shortcut. Reference superpowers' CSO finding.
- **Dependencies**: Agent & Skill Authoring skill
- **Estimated complexity**: Small
- **Model tier**: N/A (documentation)

### Gap: Systematic Debugging — Supporting Reference Files

**Classification**: Weaker
**Layer**: Skill + Knowledge
**Priority**: Medium

**What superpowers does**:
Their systematic-debugging skill includes 6 supporting files beyond the main SKILL.md: root-cause-tracing (backward tracing through call chains), defense-in-depth (4-layer validation pattern), condition-based-waiting (replace arbitrary timeouts with condition polling — claims "pass rate: 60% → 100%"), find-polluter.sh (shell script for bisecting test pollution), plus TypeScript examples.

**What we have now**:
Our `systematic-debugging` skill covers the 4-phase process (reproduce, investigate, root-cause, fix) but has no supporting reference files with concrete techniques.

**Proposed addition**:
- **Type**: knowledge files within the skill directory
- **File**: `skills/systematic-debugging/root-cause-tracing.md`, `skills/systematic-debugging/condition-based-waiting.md`, `skills/systematic-debugging/find-polluter.sh`
- **Description**: Add supporting reference files that agents can load on demand during debugging. Root-cause tracing: backward call-chain analysis technique. Condition-based waiting: replace arbitrary sleep/timeout in tests with polling. Test polluter finder: bisection script for identifying test pollution sources.
- **Dependencies**: Systematic Debugging skill
- **Estimated complexity**: Small
- **Model tier**: N/A (reference files loaded by debugging agents)

### Gap: Git Worktree — Language-Specific Setup

**Classification**: Weaker
**Layer**: Skill
**Priority**: Low

**What superpowers does**:
The `using-git-worktrees` skill includes auto-detection of worktree directories, gitignore safety checks, and language-specific setup commands (npm install, cargo build, pip install, go mod download) plus baseline test verification after setup.

**What we have now**:
We use `isolation: "worktree"` on subagent calls, which creates the worktree. But there's no language-specific dependency installation or baseline verification step.

**Proposed addition**:
- **Type**: skill enhancement or hook
- **File**: Update worktree handling in orchestrator or add `hooks/post-worktree-setup.sh`
- **Description**: After creating a worktree, detect the language/framework and run dependency installation (npm ci, cargo build, pip install -r requirements.txt, go mod download). Run the baseline test suite to verify the worktree is healthy before dispatching implementation work.
- **Dependencies**: Orchestrator worktree dispatch
- **Estimated complexity**: Medium
- **Model tier**: N/A (shell script / orchestrator logic)

## Different Approaches Worth Examining

### Design-Before-Code: `/specs` + `/design-doc` vs `brainstorming`

Both plugins enforce design before code, but with different structures:
- **superpowers**: Single `brainstorming` skill that flows from questions → approach proposals → spec document → review. Includes a visual companion (browser-based mockup server with hot-reload) for UI work. More opinionated: the conversation IS the design artifact.
- **agentic-dev-team**: Separates concerns — `/specs` produces 4 formal artifacts (intent, BDD scenarios, architecture notes, acceptance criteria), `/design-doc` produces a written document, `/design-interrogation` stress-tests the design. More structured, more artifacts, more review gates.

**Tradeoff**: superpowers' approach is lighter-weight and faster for small features. Our approach is more thorough for complex features but adds overhead. The visual companion is genuinely useful for UI work and has no equivalent in our plugin — worth considering as an independent addition.

### Subagent Orchestration: Orchestrator Agent vs Skill-Based

- **superpowers**: `subagent-driven-development` defines the dispatch protocol inline within the skill. Uses 4 status codes (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED) for subagent reporting. Model selection is "cheapest model that works."
- **agentic-dev-team**: Dedicated orchestrator agent with a model routing table, phase-based context management, and multiple prompt templates.

**Tradeoff**: superpowers' approach is simpler and more portable (works across platforms). Our approach is more sophisticated — model routing per agent, context budgets, phase transitions. The 4-status-code pattern from superpowers is worth adopting regardless: NEEDS_CONTEXT and BLOCKED are clearer than our current subagent error handling.

### Platform Strategy: Multi-Platform vs Claude Code Native

- **superpowers**: Explicitly targets 6 platforms with dedicated adapters. Skills are written to be platform-agnostic.
- **agentic-dev-team**: Deep Claude Code integration using platform-specific features (Agent tool with model override, hooks, plugin manifest).

**Tradeoff**: Multi-platform reach vs platform depth. Our hooks, review agent fleet, and model routing depend on Claude Code's Agent tool and plugin system. Porting these to Cursor or Codex would require significant adaptation. However, skills and knowledge files are largely platform-agnostic already. If multi-platform support becomes a priority, the path would be: (1) extract platform-dependent features into adapter layers, (2) add platform manifests, (3) degrade gracefully on platforms without subagent support (similar to superpowers' `executing-plans` fallback).

## Our Strengths

Areas where agentic-dev-team is clearly ahead:

1. **Review depth**: 19 specialized review agents vs 1 generic code-reviewer. Our agents catch domain-specific issues (security, a11y, concurrency, architecture, naming) that a single reviewer cannot.
2. **Static analysis integration**: Semgrep pre-pass deduplicates findings before AI agents run, reducing cost and improving signal.
3. **Architecture & design skills**: DDD, hexagonal architecture, threat modeling, API design, design-it-twice — superpowers has none of these.
4. **Infrastructure tooling**: Docker creation/audit, CI debugging, performance benchmarking — entirely absent from superpowers.
5. **Session continuity**: `/continue` with memory-based phase progress files allows multi-session work. superpowers has no equivalent.
6. **Destructive command protection**: `/careful`, `/freeze`, `/guard` provide safety rails that superpowers lacks.
7. **Metrics & governance**: Cost tracking, hallucination logging, audit trails, compliance procedures.
8. **Agent eval framework**: `/agent-eval` with fixtures and grading ensures review agents maintain accuracy over time.
9. **Language-specific templates**: 9 agent templates scaffolded per-project by `/setup` (TypeScript, Python, Go, C#, React, Angular, etc.).
10. **Bug triage workflow**: `/triage` investigates bugs and files GitHub issues with TDD fix plans.

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1 | Anti-rationalization techniques | Knowledge + Skill | Small | Addresses the #1 LLM failure mode (behavioral drift). superpowers' core innovation. Low effort, high impact across all agents. |
| 2 | Code review reception discipline | Skill | Small | Prevents agents from blindly accepting bad feedback — a known failure mode we currently don't guard against. Quick win. |
| 3 | Skill authoring — pressure testing & CSO | Skill enhancement | Small | Improves quality of every future skill we write. The CSO finding about descriptions is immediately actionable. |
| 4 | Systematic debugging supporting files | Knowledge | Small | Concrete techniques (root-cause tracing, condition-based waiting, polluter finder) make our debugging skill actionable rather than procedural. |
| 5 | Subagent status codes (NEEDS_CONTEXT / BLOCKED) | Orchestrator | Medium | Clearer subagent reporting improves orchestrator decision-making. Currently subagent errors are less structured. |

## Next Steps

**Quick wins (can implement now):**
1. Create `knowledge/anti-rationalization.md` and embed rationalization examples in TDD and Quality Gate skills
2. Create `skills/receiving-code-review/SKILL.md` with behavioral constraints for review reception
3. Add pressure testing and CSO guidance to `skills/agent-skill-authoring/SKILL.md`

**Medium-term:**
4. Add supporting reference files to the systematic-debugging skill directory
5. Adopt 4-status-code pattern (DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED) for subagent reporting in the orchestrator
6. Evaluate the visual companion concept for UI-heavy brainstorming sessions

**Research needed:**
7. Multi-platform support: audit which of our capabilities are platform-dependent vs platform-agnostic. If demand exists, design an adapter layer.
8. Review superpowers' `find-polluter.sh` script for test pollution bisection — could be valuable as a hook or standalone tool.
