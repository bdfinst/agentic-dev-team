# Competitive Analysis: agentic-dev-team vs Claude Code

**Date**: 2026-03-30
**Target**: Claude Code (https://github.com/anthropics/claude-code) — Anthropic's official agentic coding CLI
**Source type**: URL

## Executive Summary

Claude Code is Anthropic's first-party agentic coding tool — the runtime that agentic-dev-team runs on top of as a plugin. This comparison identified 8 gaps (3 Missing, 5 Weaker), 4 areas where the approaches differ fundamentally, and 7 areas where agentic-dev-team is stronger. The top finding is that Claude Code ships strong primitives (tools, hooks, subagents, MCP, memory) but deliberately avoids opinionated workflows, while agentic-dev-team layers structured orchestration, persona-driven agents, and quality gates on top of those primitives. The biggest gaps are in IDE integration, MCP ecosystem leverage, and interactive debugging.

## Capability Comparison

### Team Agents

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Specialized role personas (12 agents) | 12 team agents with behavioral specs, psychological profiles, and model routing | No persona system — single general-purpose agent | **Stronger** |
| Multi-agent orchestration | Orchestrator dispatches sub-agents with context isolation, phase transitions, memory handoff | Subagent primitive available (Task tool) but no built-in orchestration | **Stronger** |
| Model routing per agent | Explicit haiku/sonnet/opus routing table per agent | User can set model via `--model` flag or `/model` command; no automatic per-task routing | **Stronger** |

### Review Agents

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Automated multi-agent code review | 19 specialized review agents (security, a11y, naming, complexity, etc.) dispatched by orchestrator | No built-in review agents — relies on user prompting or external tools | **Stronger** |
| Spec compliance checking | spec-compliance-review agent gates code against BDD scenarios | No equivalent | **Stronger** |
| Review correction loops | Max 2 iteration correction cycle with escalation to human | No equivalent — user manually re-prompts | **Stronger** |

### Skills (Reusable Knowledge Modules)

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Structured skills library | 24 skills with token budgets and agent mappings | No skill system — knowledge is in CLAUDE.md or user prompts | **Stronger** |
| TDD workflow | Dedicated TDD skill with RED-GREEN-REFACTOR enforcement | Can follow TDD if prompted, but no enforced workflow | **Stronger** |
| Domain-Driven Design | DDD skill + domain analysis skill + domain-review agent | No built-in DDD support | **Stronger** |
| Threat modeling | STRIDE-based threat modeling skill | No built-in threat modeling | **Stronger** |

### Commands (User-Invocable Workflows)

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Structured plan-then-build workflow | `/plan` + `/build` with human review gates between phases | Users can ask Claude to plan, but no enforced phase gates | **Stronger** |
| PR creation with quality gates | `/pr` runs tests + typecheck + lint + code review before PR | `/pr` creates PRs but without multi-agent pre-flight review | **Weaker** |
| Session continuity | `/continue` reads memory/ progress files to resume | Built-in memory system with `~/.claude/memory/` for cross-session persistence | **Weaker** |
| Plugin management | `/add-plugin`, `/upgrade` | Built-in plugin install/management in CLI (`claude plugin install`) | **Different approach** |
| Browser testing | `/browse` via Playwright skill | No built-in browser tool — available via MCP servers | **Different approach** |
| Init/setup | `/setup` detects stack, generates CLAUDE.md, hooks, templates | `claude init` generates CLAUDE.md with interactive setup | **Different approach** |
| Interactive help | `/help` lists commands | Built-in `/help`, `/status`, `/model`, `/config`, `/memory` and more | **Weaker** |

### Hooks (Automated Guards)

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Pre-tool guards | `pre-tool-guard.sh` blocks writes to secrets; `destructive-guard.sh` warns on dangerous commands | Native hook system (PreToolUse, PostToolUse, PreCommit) with JSON-configurable matchers | **Weaker** |
| Scope locking | `/freeze` + `/unfreeze` to restrict edits to a glob | File permissions via `settings.json` (`allowedPaths`, `blockedPaths`) | **Different approach** |
| Careful mode | `/careful` escalates destructive warnings to blocks | No equivalent toggle — users configure permissions statically | **Stronger** |

### Templates (Language-Specific Scaffolding)

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Stack-specific review agents | 9 templates (TS, ESM, React, Angular, Python, Go, C#, etc.) scaffolded by `/setup` | No template system — generic agent handles all languages | **Stronger** |

### Workflows (Multi-Phase Orchestration)

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Research-Plan-Implement pipeline | Three-phase workflow with human gates, progress files, context summarization | No structured multi-phase workflow — user drives the conversation | **Stronger** |
| Context management | 40% utilization ceiling, LSTM-inspired summarization, phased loading | Automatic context management with compaction; users can configure via `/compact` | **Weaker** |
| Memory/learning | `memory/` directory + feedback-learning skill + config changelog | Built-in memory system (`/memory`, project-level memory, auto-memory via CLAUDE.md) with semantic search | **Weaker** |

### IDE & Platform Integration

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| VS Code integration | None — terminal-only plugin | Native VS Code extension with inline diff view, file decorations, chat panel | **Missing** |
| GitHub integration | `/pr` command for PR creation | `@claude` mentions in PRs/issues, automated PR review, CI integration | **Missing** |
| MCP server ecosystem | No MCP integration | Native MCP support — filesystem, database, API servers, Puppeteer, Sentry, etc. | **Missing** |

### Configuration & Settings

| Capability | agentic-dev-team | Claude Code | Classification |
|-----------|-----------------|----------|----------------|
| Project configuration | `CLAUDE.md` + `settings.json` + agent files | `CLAUDE.md` + `settings.json` + `.claude/` directory with commands, hooks, agents | **Different approach** |
| User-level configuration | Federated learning via feedback keywords | `~/.claude/settings.json` + `~/.claude/CLAUDE.md` for global defaults | **Weaker** |

## Gap Specs

### Gap: IDE Integration (VS Code Extension)

**Classification**: Missing
**Layer**: Workflow
**Priority**: Low

**What Claude Code does**:
Native VS Code extension provides inline diff acceptance, file decorations showing modified lines, integrated chat panel, and the ability to invoke Claude Code without leaving the editor.

**Proposed addition**:
- **Type**: Out of scope — agentic-dev-team is a plugin that runs inside Claude Code, which already has VS Code integration. No action needed. Users get IDE integration by running Claude Code with the plugin installed in VS Code.
- **Note**: This is an inherent architectural boundary, not a true gap. The plugin rides on the host's IDE support.

### Gap: GitHub Native Integration (@claude mentions)

**Classification**: Missing
**Layer**: Workflow
**Priority**: High

**What Claude Code does**:
Users can tag `@claude` in GitHub PR comments and issues to trigger Claude Code actions: automated PR review, issue triage, code suggestions directly in GitHub's UI. This enables asynchronous, team-wide AI interaction without anyone needing a local Claude Code install.

**Proposed addition**:
- **Type**: skill + command
- **File**: `skills/github-integration.md` and `commands/github-review.md`
- **Description**: A skill that formats agentic-dev-team review output for GitHub PR comments, and a command that can be triggered via GitHub Actions to run the full review suite on PRs. This would bring the 19-agent review pipeline to GitHub-native workflows.
- **Dependencies**: `/code-review`, review agents, `gh` CLI
- **Estimated complexity**: Large
- **Model tier**: sonnet (orchestration)

### Gap: MCP Server Ecosystem Leverage

**Classification**: Missing
**Layer**: Skill / Knowledge
**Priority**: Medium

**What Claude Code does**:
Claude Code natively supports MCP (Model Context Protocol) servers, allowing it to connect to databases, APIs, monitoring tools (Sentry, Datadog), browsers (Puppeteer), and more. Users configure MCP servers in `settings.json` and Claude Code can call them as tools.

**Proposed addition**:
- **Type**: skill + knowledge file
- **File**: `skills/mcp-integration.md` and `knowledge/mcp-catalog.md`
- **Description**: A skill that teaches agents how to discover and use available MCP servers in the current project. The knowledge file would catalog common MCP servers and their capabilities so agents can recommend appropriate MCP tools during `/setup`. The orchestrator would check for available MCP tools before dispatching sub-agents.
- **Dependencies**: Orchestrator, `/setup` command
- **Estimated complexity**: Medium
- **Model tier**: N/A (knowledge, not agent)

### Gap: Context Management Sophistication

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What Claude Code does**:
Claude Code has automatic context compaction that triggers transparently when the context window fills. Users can also manually trigger `/compact` with a custom focus prompt. The system manages this without requiring explicit phase transitions or progress files.

**What we have now**:
The 40% utilization ceiling and LSTM-inspired summarization in `skills/context-summarization.md` are well-designed but rely on proxy signals since plugins cannot directly measure token counts. The phase-transition approach (write to `memory/`, start fresh context) is effective but heavier-weight than Claude Code's automatic compaction.

**Proposed addition**:
- **Type**: skill improvement
- **File**: `skills/context-summarization.md` (update)
- **Description**: Integrate with Claude Code's native compaction signals. When automatic compaction fires, detect it (via PostToolUse hook or context length heuristics) and ensure the summarization skill writes structured progress state before context is lost. This would make the two systems complementary rather than redundant.
- **Dependencies**: Context Loading Protocol skill, hooks system
- **Estimated complexity**: Medium
- **Model tier**: N/A

### Gap: Memory System Integration

**Classification**: Weaker
**Layer**: Skill
**Priority**: Medium

**What Claude Code does**:
Built-in `/memory` command with semantic memory search, automatic memory creation from CLAUDE.md, project-level and user-level memory that persists across sessions without manual file management.

**What we have now**:
`memory/` directory with structured progress files and `feedback-learning.md` skill. Effective for phase handoff but requires explicit file writes. No semantic search — agents must know which file to read.

**Proposed addition**:
- **Type**: skill improvement
- **File**: `skills/feedback-learning.md` (update)
- **Description**: Leverage Claude Code's native memory system for lightweight learnings (gotchas, preferences, team patterns) while keeping the structured `memory/` files for phase-transition state. Add a convention: feedback-learning writes to both `memory/` files AND Claude Code's native memory, so learnings survive even when `memory/` is cleaned up.
- **Dependencies**: Feedback & Learning skill
- **Estimated complexity**: Small
- **Model tier**: N/A

### Gap: Built-in Hook Configuration Richness

**Classification**: Weaker
**Layer**: Hook
**Priority**: Low

**What Claude Code does**:
Native hook system supports PreToolUse, PostToolUse, PreCommit, Notification, and Stop hooks. Hooks are configured in `settings.json` with JSON matchers (tool name, command patterns) and can run any executable. Supports both project-level and user-level hooks.

**What we have now**:
`pre-tool-guard.sh` and `destructive-guard.sh` are effective but configured via a separate `hooks/guards.json` rather than the standard `settings.json` hook format. The `/setup` command generates hooks, but the hook configuration is not fully aligned with Claude Code's native hook schema.

**Proposed addition**:
- **Type**: hook improvement
- **File**: `hooks/` directory + `/setup` command update
- **Description**: Migrate hook configuration to use Claude Code's native `settings.json` hook format exclusively. Remove the custom `guards.json` indirection. This reduces cognitive load for users who already understand Claude Code's hook system.
- **Dependencies**: `/setup`, `/careful`, `/freeze` commands
- **Estimated complexity**: Small
- **Model tier**: N/A

### Gap: Interactive Help and Status

**Classification**: Weaker
**Layer**: Command
**Priority**: Low

**What Claude Code does**:
Rich set of built-in slash commands: `/help`, `/status` (shows current config, model, context usage), `/model` (switch models mid-session), `/config` (view/edit settings), `/memory` (manage memory), `/compact` (manual compaction), `/pr` (create PRs). Each provides real-time introspection into the system state.

**What we have now**:
`/help` lists commands. No equivalent of `/status` for seeing current agent context load, model routing state, or review agent health at a glance.

**Proposed addition**:
- **Type**: command
- **File**: `commands/status.md`
- **Description**: A `/status` command that shows: current phase (Research/Plan/Implement), loaded agents and their model assignments, context utilization estimate, active `/freeze` or `/careful` locks, and recent review results. Gives users visibility into the orchestration state.
- **Dependencies**: Orchestrator, Context Loading Protocol
- **Estimated complexity**: Small
- **Model tier**: haiku

## Different Approaches Worth Examining

### Plugin Management vs Built-in CLI

**agentic-dev-team** uses `/add-plugin` and `/upgrade` commands to manage plugins from within a session, tracking installs in `settings.json` for team replication. **Claude Code** uses `claude plugin install` as a CLI command outside sessions.

**Tradeoff**: The in-session approach is more discoverable (users find it via `/help`) but creates a dependency on the plugin being loaded before it can manage itself. Claude Code's CLI approach is more standard (similar to `npm install`) but less visible to users who live inside sessions. Both are reasonable. No change recommended — the current approach is fine for a plugin that orchestrates workflows.

### Browser Testing vs MCP

**agentic-dev-team** bundles a `/browse` command with a Playwright-based browser testing skill. **Claude Code** delegates browser interaction to MCP servers (Puppeteer MCP, Browserbase MCP) configured by the user.

**Tradeoff**: The bundled approach is zero-config and works out of the box for QA workflows. The MCP approach is more flexible (any browser tool) but requires setup. For a plugin focused on development team workflows, the bundled approach is the right call — QA engineers should not need to configure MCP to run visual regression tests.

### Project Setup

**agentic-dev-team** `/setup` detects the tech stack and generates CLAUDE.md, hooks, and language-specific agent templates automatically. **Claude Code** `claude init` generates a CLAUDE.md interactively.

**Tradeoff**: `/setup` is more opinionated and produces more artifacts (agent templates, hooks), which is appropriate for a plugin that needs stack-specific review agents. `claude init` is intentionally minimal. These complement each other — `/setup` can run after `claude init` to layer on the plugin's configuration.

### Scope Locking

**agentic-dev-team** uses `/freeze` and `/unfreeze` as dynamic session toggles. **Claude Code** uses static `allowedPaths`/`blockedPaths` in `settings.json`.

**Tradeoff**: The dynamic approach is better for production debugging sessions where you want temporary guardrails. The static approach is better for permanent boundaries (e.g., "never edit `node_modules/`"). Both have value. Consider making `/freeze` also update `settings.json` temporarily so the lock survives context compaction.

## Our Strengths

1. **Structured multi-phase workflow** (Research, Plan, Implement) with human review gates — Claude Code has no equivalent enforced workflow
2. **19 specialized review agents** with automatic dispatch based on change type — Claude Code relies on user prompting for review
3. **12 persona-driven team agents** with behavioral specs and model routing — Claude Code is a single general-purpose agent
4. **Automatic model tiering** (haiku/sonnet/opus per agent) optimizes cost without user intervention
5. **TDD enforcement** via RED-GREEN-REFACTOR hard gates — Claude Code can do TDD but does not enforce it
6. **24 reusable skills** with progressive disclosure — reduces token usage while maintaining deep capability
7. **Spec compliance checking** — the spec-compliance-review agent gates all code against BDD scenarios before quality review runs

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1 | GitHub Native Integration (@claude) | Workflow | Large | Unlocks team-wide async review without local installs; multiplies the value of the 19-agent review pipeline |
| 2 | MCP Server Ecosystem Leverage | Skill/Knowledge | Medium | MCP is becoming the standard integration layer; agents that discover and use MCP tools will be more capable |
| 3 | Context Management Integration | Skill | Medium | Aligning with Claude Code's native compaction prevents data loss during automatic context management |
| 4 | Memory System Integration | Skill | Small | Quick win — leverage native memory for lightweight learnings while keeping structured files for phase state |
| 5 | Status Command | Command | Small | Quick win — gives users visibility into orchestration state, reducing confusion about what the plugin is doing |

## Next Steps

1. **Quick wins first**: Memory system integration (rank 4) and the `/status` command (rank 5) are both Small complexity. Implement these in a single sprint to improve daily usability.
2. **GitHub integration needs research**: The @claude integration (rank 1) requires understanding GitHub Actions workflows and how to package the review pipeline as a CI step. Start with a design doc.
3. **MCP awareness** (rank 2): Begin with the knowledge file (`knowledge/mcp-catalog.md`) cataloging common MCP servers. Then update the orchestrator to check for available MCP tools before dispatching sub-agents.
4. **Context compaction alignment** (rank 3): Experiment with PostToolUse hooks that detect context compaction events and trigger the summarization skill proactively.
5. **Do not pursue IDE integration** — agentic-dev-team runs inside Claude Code, which already provides VS Code support. Building a separate IDE extension would be redundant.
