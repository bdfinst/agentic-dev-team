# Competitive Analysis: agentic-dev-team vs Kodus AI

**Date**: 2026-04-01
**Target**: [Kodus AI](https://github.com/kodustech/kodus-ai) — open-source AI code review platform
**Source type**: URL

## Executive Summary

Kodus AI is an open-source, model-agnostic code review platform that operates as a deployed SaaS/self-hosted service integrated into Git provider PR workflows. It competes on a fundamentally different axis than agentic-dev-team: Kodus is a **hosted CI/CD-adjacent review service** with dashboards, team management, and engineering metrics, while agentic-dev-team is a **local-first Claude Code plugin** that orchestrates an entire development lifecycle (research, plan, implement, review). The analysis found 7 gaps where Kodus offers capabilities we lack, 3 areas where approaches differ meaningfully, and 8 areas where agentic-dev-team is significantly stronger.

## Capability Comparison

### Code Review

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Automated PR review | 19 specialized review agents with confidence filtering | Single AI reviewer ("Kody") with AST + LLM hybrid | **Stronger** |
| Review specialization | Dedicated agents for security, a11y, domain, naming, complexity, etc. | General-purpose reviewer with custom rules | **Stronger** |
| Model routing per review type | Orchestrator routes haiku/sonnet/opus by review category | User picks one model for all reviews | **Stronger** |
| AST-based analysis | No — relies on LLM code understanding | Yes — language-aware AST parsing reduces noise | **Weaker** |
| Custom review rules (plain language) | No equivalent — rules are baked into agent definitions | Users define rules in natural language; auto-detects from Cursor/Copilot/Claude configs | **Missing** |
| Rule synchronization from other tools | No — standalone rule definitions | Auto-imports standards from Cursor, Copilot, Claude | **Missing** |
| Review noise reduction | Confidence-based filtering per agent | AST + LLM hybrid claims reduced false positives | **Different approach** |
| Correction loops | Max 2 automated fix iterations before escalating to human | Suggestions posted as PR comments; manual application | **Stronger** |

### Git Platform Integration

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| GitHub integration | Via `gh` CLI (PR creation, issue filing) | Native webhook-based PR integration | **Weaker** |
| GitLab support | No | Yes | **Missing** |
| Bitbucket support | No | Yes | **Missing** |
| Azure DevOps support | No | Yes | **Missing** |
| PR comment threading | No — review results go to files or chat | Direct inline PR comments and suggestions | **Weaker** |

### Development Lifecycle

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Research phase | Codebase exploration, design docs, design interrogation | None | **Stronger** |
| Planning phase | Structured plans with TDD steps, automated plan review | None | **Stronger** |
| Implementation phase | TDD-driven implementation with inline review checkpoints | None — review only, no code generation | **Stronger** |
| Spec authoring (BDD) | Full spec workflow: Intent → Scenarios → Architecture → AC | None | **Stronger** |
| Bug triage | `/triage` investigates and files GitHub issues | None | **Stronger** |
| Domain-driven design | Domain analysis, bounded context assessment | None | **Stronger** |
| Threat modeling | STRIDE-based analysis skill | None | **Stronger** |

### Engineering Metrics & Dashboards

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Engineering dashboard | No — metrics logged to local JSONL files | Web dashboard with team-level analytics | **Weaker** |
| DORA metrics (deploy frequency, cycle time) | No | Yes — deployment frequency, cycle time tracking | **Missing** |
| PR analytics | No | PR metrics, bug ratio monitoring | **Missing** |
| Technical debt tracking | No formal tracking — review agents flag issues per-run | Converts unimplemented suggestions into tracked issues | **Weaker** |

### Team & Organization Management

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Multi-user team management | No — single-user CLI plugin | Role-based team membership and control | **Different approach** |
| Per-team/org custom standards | Project-level CLAUDE.md + REVIEW-CONTEXT.md | Per-team, per-org, per-repo rule customization | **Different approach** |
| Audit compliance (SOC 2) | No formal compliance | SOC 2 compliant | **Missing** |

### Model & Provider Management

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Model routing | Orchestrator routes tasks to haiku/sonnet/opus tiers | User picks any model (Claude, GPT, Gemini, Llama, etc.) | **Different approach** |
| Model agnosticism | Claude-only (Anthropic models) | Any OpenAI-compatible endpoint | **Weaker** |
| Cost transparency | No cost tracking beyond token logging | Zero markup on LLM API costs; pay providers directly | **Missing** |

### Deployment & Architecture

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Deployment model | Local CLI plugin (no deployment needed) | Cloud or self-hosted (Docker, Railway, VM) | **Different approach** |
| Security posture | Local-only — code never leaves machine (except to LLM) | Code not stored; encryption in transit/at rest | **Different approach** |

### Knowledge & Learning

| Capability | agentic-dev-team | Kodus AI | Classification |
|-----------|-----------------|----------|----------------|
| Institutional knowledge capture | Knowledge Capture agent, ADR Author, memory system | None | **Stronger** |
| Learning from team patterns | Feedback & Learning skill (user-triggered) | Auto-learns from historical PRs and team conventions | **Weaker** |
| Context continuity across sessions | Memory system, `/continue`, phase progress files | Persistent per-org/team configuration | **Different approach** |

## Gap Specs

### Gap: AST-Based Code Analysis

**Classification**: Weaker
**Layer**: Skill / Hook
**Priority**: Medium

**What the other plugin does**:
Uses Abstract Syntax Tree parsing alongside LLM analysis to provide language-aware code understanding. This reduces noise by distinguishing syntactic patterns (unused variables, unreachable code, type mismatches) from semantic patterns that need LLM reasoning.

**What we have now**:
All analysis is LLM-based. Review agents rely entirely on the model's code comprehension. This works well for semantic analysis (domain boundaries, architecture violations) but is less efficient for syntactic checks that a parser handles deterministically.

**Proposed addition**:
- **Type**: skill + hook integration
- **File**: `skills/static-analysis-integration.md`
- **Description**: A skill that integrates external static analysis tools (Semgrep, ESLint, tree-sitter) into the review pipeline. Rather than building our own AST parser, leverage existing tools and feed their structured output to review agents as additional context. The existing `/semgrep-analyze` command is a starting point but isn't integrated into the review pipeline.
- **Dependencies**: `/semgrep-analyze`, `/code-review` pipeline, review agents
- **Estimated complexity**: Medium
- **Model tier**: N/A (tool integration, not model-dependent)

### Gap: Git Platform Support (GitLab, Bitbucket, Azure DevOps)

**Classification**: Missing
**Layer**: Workflow
**Priority**: Low

**What the other plugin does**:
Native webhook-based integration with GitHub, GitLab, Bitbucket, and Azure DevOps. Reviews trigger automatically on PR/MR creation.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/git-platform-integration.md`
- **Description**: Extend `/pr` and `/code-review` to detect the active Git platform and use appropriate CLI tools (`glab` for GitLab, etc.). Since agentic-dev-team runs locally via Claude Code, the integration would be CLI-based rather than webhook-based. This is lower priority because Claude Code itself is the integration point, and most Claude Code users are on GitHub.
- **Dependencies**: `/pr`, `/code-review`, branch-workflow skill
- **Estimated complexity**: Medium
- **Model tier**: N/A

### Gap: Plain-Language Custom Review Rules

**Classification**: Missing
**Layer**: Knowledge / Agent
**Priority**: High

**What the other plugin does**:
Users define review rules in natural language (e.g., "All API handlers must validate input using zod schemas"). Kodus also auto-detects rules from Cursor, Copilot, and Claude configuration files.

**Proposed addition**:
- **Type**: knowledge file + command enhancement
- **File**: `knowledge/custom-review-rules.md` (user-editable per project)
- **Description**: Allow users to define custom review rules in a structured file that review agents load as additional context. Rules would be natural language statements with optional severity and scope (file patterns). The existing `REVIEW-CONTEXT.md` provides some of this, but it's unstructured. A dedicated rules file with a defined schema would make rules more actionable. Additionally, auto-import from `.cursorrules`, `.github/copilot-instructions.md`, and existing `CLAUDE.md` rules.
- **Dependencies**: All review agents, `/code-review` pipeline
- **Estimated complexity**: Small
- **Model tier**: N/A (loaded as context, not a model task)

### Gap: PR Inline Comment Integration

**Classification**: Weaker
**Layer**: Command
**Priority**: High

**What the other plugin does**:
Posts review findings as inline comments directly on PR diffs in the Git platform UI. Developers see findings in context without leaving their PR workflow.

**What we have now**:
Review results are written to local files or displayed in chat. The `/pr` command creates PRs but doesn't post review findings as PR comments.

**Proposed addition**:
- **Type**: command enhancement
- **File**: Enhancement to `commands/code-review.md` + new `skills/pr-comment-integration.md`
- **Description**: After `/code-review` completes, optionally post findings as inline PR comments using `gh api` (GitHub) or equivalent CLI tools. Each finding maps to a file + line number, which the review agents already produce. A `--post-to-pr` flag on `/code-review` would trigger this. Respects existing review severity filtering — only post FAIL and WARN findings.
- **Dependencies**: `/code-review`, `gh` CLI, review agents (must output file:line consistently)
- **Estimated complexity**: Medium
- **Model tier**: N/A

### Gap: DORA / Engineering Metrics Dashboard

**Classification**: Missing
**Layer**: Skill
**Priority**: Low

**What the other plugin does**:
Web dashboard tracking deployment frequency, cycle time, PR metrics, and bug ratios. Provides team-level visibility into engineering performance.

**Proposed addition**:
- **Type**: skill + command
- **File**: `skills/engineering-metrics.md`, `commands/metrics-report.md`
- **Description**: Extend the existing `metrics/` JSONL logging to compute DORA-style metrics from Git history (deploy frequency from tags/releases, lead time from first commit to merge, change failure rate from reverted PRs). Generate a local markdown report rather than a web dashboard — fits the local-first model. Could optionally push to a team-shared location.
- **Dependencies**: Performance Metrics skill, Git history access
- **Estimated complexity**: Medium
- **Model tier**: haiku (data extraction and formatting)

### Gap: Automated Learning from PR History

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What the other plugin does**:
Automatically learns team conventions, patterns, and standards from historical PR reviews and merged code. Adapts review behavior over time without explicit user configuration.

**What we have now**:
The Feedback & Learning skill requires explicit user triggers (`amend`, `learn`, `remember`, `forget`). No passive learning from code patterns.

**Proposed addition**:
- **Type**: skill
- **File**: `skills/pattern-learning.md`
- **Description**: Periodically analyze recent merged PRs and their review comments to extract recurring patterns, conventions, and standards. Store as structured rules in `knowledge/learned-patterns.md`. Surface new patterns to the user for approval before activating them as review criteria. Keeps the human-in-the-loop principle while reducing the burden of explicit rule definition.
- **Dependencies**: Feedback & Learning skill, Git history, review agents
- **Estimated complexity**: Large
- **Model tier**: sonnet (pattern extraction requires reasoning)

### Gap: LLM Cost Transparency

**Classification**: Missing
**Layer**: Skill
**Priority**: Low

**What the other plugin does**:
Zero markup on LLM API costs with full transparency. Users pay model providers directly at standard rates.

**Proposed addition**:
- **Type**: enhancement to Performance Metrics skill
- **File**: Enhancement to `skills/performance-metrics.md`
- **Description**: Track estimated token costs per review run and per task, using published model pricing. Include cost breakdown in `/review-summary` output and metrics reports. This is informational — agentic-dev-team doesn't control Claude Code's billing — but visibility into per-task costs helps users optimize their model routing and review scope.
- **Dependencies**: Performance Metrics skill, model routing table
- **Estimated complexity**: Small
- **Model tier**: N/A

## Different Approaches Worth Examining

### Review Noise Reduction: Confidence Filtering vs AST + LLM Hybrid

**agentic-dev-team** uses confidence-based filtering within each review agent — agents report findings with confidence levels and the pipeline filters low-confidence results. This is flexible and works across any language, but relies entirely on the LLM's self-assessment of confidence.

**Kodus** combines AST parsing (deterministic, precise) with LLM analysis (semantic, contextual). Syntactic issues are caught by the parser with zero false positives; the LLM handles semantic concerns.

**Tradeoff**: Our approach is simpler and more portable across languages. Kodus's approach requires AST infrastructure per language but produces more precise syntactic findings. The best path for agentic-dev-team is likely to integrate existing static analysis tools (Semgrep, ESLint) rather than building AST parsing — getting the precision benefit without the infrastructure cost.

### Model Selection: Orchestrated Routing vs User Choice

**agentic-dev-team** assigns models based on task complexity (haiku for simple checks, opus for security/architecture). The user doesn't choose — the orchestrator optimizes for cost/quality.

**Kodus** lets users pick any model from any provider (Claude, GPT, Gemini, Llama, etc.) for all reviews.

**Tradeoff**: Our approach optimizes cost/quality automatically but locks users into Anthropic models. Kodus's approach gives flexibility but uses the same model for naming checks and security analysis. Our routing is more efficient; their flexibility appeals to teams with existing model preferences or cost constraints. Since Claude Code itself is Anthropic-locked, model agnosticism isn't a realistic goal for this plugin — but better cost optimization visibility (see Gap: LLM Cost Transparency) would address the underlying user concern.

### Deployment: Local CLI vs Hosted Service

**agentic-dev-team** runs entirely within Claude Code as a local plugin. No infrastructure to manage, no data leaves the developer's machine (except to the LLM API).

**Kodus** runs as a hosted service (cloud or self-hosted) with webhooks, workers, and a web dashboard. Reviews trigger automatically on PR creation.

**Tradeoff**: Local-first means zero setup cost and maximum privacy, but no team-wide visibility, no automatic triggers, and no persistent dashboards. Kodus's hosted model enables team features but requires infrastructure and raises data handling questions. These are fundamentally different product categories — a CLI plugin vs. a platform. The right response is not to become a platform, but to ensure our local outputs (review reports, metrics) can be shared or consumed by team tools when desired.

## Our Strengths

- **Full development lifecycle**: Research → Plan → Implement → Review. Kodus only does review.
- **19 specialized review agents** with domain-specific expertise vs. one general reviewer.
- **Model routing optimization**: Right-sized models per task type reduce cost without sacrificing quality.
- **TDD-driven implementation**: Built-in test-driven development with RED-GREEN-REFACTOR workflow.
- **Spec authoring and planning**: BDD scenarios, structured plans, automated plan review.
- **Institutional knowledge**: Knowledge Capture agent, ADR Author, persistent memory system.
- **Bug triage workflow**: `/triage` investigates bugs and files actionable GitHub issues.
- **Domain-driven design**: Domain analysis, bounded context assessment, domain review agent.
- **Threat modeling**: STRIDE-based security analysis before implementation.
- **Context management**: 40% utilization ceiling, phase-based context isolation, summarization.
- **Correction loops**: Automated fix iterations with escalation — not just "here's a comment."
- **Zero infrastructure**: No deployment, no webhooks, no workers — just install the plugin.

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1 | Plain-language custom review rules | Knowledge | Small | Quick win — users can define project-specific review criteria without editing agent files. Addresses the most common customization need. |
| 2 | PR inline comment integration | Command | Medium | Review findings posted to PRs are immediately actionable by the whole team, not just the local developer. Bridges the gap between local-first and team visibility. |
| 3 | Static analysis integration (AST/Semgrep) | Skill | Medium | Integrating Semgrep into the review pipeline reduces LLM noise on syntactic issues and adds deterministic precision. Foundation already exists in `/semgrep-analyze`. |
| 4 | Automated learning from PR history | Skill | Large | Passive pattern learning would significantly reduce the manual effort of configuring review rules. High value but high complexity — consider a phased approach. |
| 5 | DORA / engineering metrics | Skill | Medium | Local DORA metrics from Git history would help teams quantify improvement. Low effort relative to value, but lower priority than review-focused gaps. |

## Next Steps

1. **Quick win — Custom review rules**: Create `knowledge/custom-review-rules.md` with a simple schema. Update `/code-review` to load it. Auto-import from `.cursorrules` and `.github/copilot-instructions.md` if present. Could ship in a single session.

2. **PR comment integration**: Prototype `--post-to-pr` on `/code-review` using `gh api` to post inline comments. Requires review agents to consistently output `file:line` references (audit current agents for compliance).

3. **Semgrep pipeline integration**: The `/semgrep-analyze` command exists but isn't wired into `/code-review`. Wire it as an optional pre-pass that feeds structured findings to review agents as additional context.

4. **Defer platform expansion**: GitLab/Bitbucket/Azure DevOps support is low priority given the Claude Code user base. Revisit if user demand signals change.

5. **Defer dashboard/metrics**: Local DORA metrics are useful but not differentiating. The existing `metrics/` JSONL logging is sufficient for now. Revisit when the metrics skill is next touched.
