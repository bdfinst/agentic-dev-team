---
# REQUIRED — unique identifier
# Format: lowercase letters, digits, and hyphens only (e.g. code-reviewer, db-reader)
# Must match the filename convention; used by hooks as agent_type
name: your-agent-name

# REQUIRED — tells Claude when to delegate to this agent
# Write a clear, specific description. Include "Use proactively" to encourage automatic delegation.
description: >-
  One-sentence description of what this agent does and when to use it.
  Add "Use proactively when X" to encourage automatic delegation.

# OPTIONAL — tools this agent can use
# If omitted, the agent inherits ALL tools from the main conversation.
# Use this as an allowlist to restrict what the agent can do.
#
# Common tools: Read, Grep, Glob, Bash, Edit, Write, Agent, Skill
# Tool restrictions: Agent(worker, researcher) limits which subagents can be spawned
# Bash restrictions: Bash(npx *) limits Bash to matching commands only
#
# Note: To preload skill content at startup, use the `skills` field below
# instead of listing Skill here. Listing Skill here allows runtime invocation
# but does not inject skill content into context automatically.
tools: Read, Grep, Glob

# OPTIONAL — tools to deny (removed from inherited or specified list)
# Use when you want to inherit most tools but block a few specific ones.
# disallowedTools: Write, Edit

# OPTIONAL — model to use
# Use a tier alias: sonnet | opus | haiku | inherit
# Tier → snapshot resolution flows through knowledge/model-routing.json
# and the PreToolUse hook hooks/agent-model-resolve.sh. Do not pin a
# snapshot ID here; the hook is the authoritative dispatch gate.
# inherit: use the same model as the main conversation (default if omitted)
#
# Routing guidance:
#   haiku  — high-volume, structured extraction, simple classification
#   sonnet — balanced capability and speed; most agents
#   opus   — frontier reasoning, security analysis, architectural judgment
model: sonnet

# OPTIONAL — permission mode
# WARNING: Ignored for plugin agents (silently has no effect).
# Only works for project agents (.claude/agents/) or user agents (~/.claude/agents/).
# Values: default | acceptEdits | auto | dontAsk | bypassPermissions | plan
# permissionMode: default

# OPTIONAL — maximum agentic turns before the agent stops
# maxTurns: 10

# OPTIONAL — skills to preload into this agent's context at startup
# The full content of each skill is injected before the agent runs.
# This is different from listing Skill in tools (which allows runtime invocation).
# Use skill names as they appear in the skills registry.
# skills:
#   - api-conventions
#   - error-handling-patterns

# OPTIONAL — MCP servers available to this agent
# WARNING: Ignored for plugin agents (silently has no effect).
# Only works for project agents (.claude/agents/) or user agents (~/.claude/agents/).
# mcpServers:
#   - playwright:
#       type: stdio
#       command: npx
#       args: ["-y", "@playwright/mcp@latest"]

# OPTIONAL — lifecycle hooks scoped to this agent
# WARNING: Ignored for plugin agents (silently has no effect).
# Only works for project agents (.claude/agents/) or user agents (~/.claude/agents/).
# hooks:
#   PreToolUse:
#     - matcher: "Bash"
#       hooks:
#         - type: command
#           command: "./scripts/validate-command.sh"

# OPTIONAL — persistent memory directory that survives across conversations
# Values: user | project | local
#   user:    ~/.claude/agent-memory/<name>/    (all projects)
#   project: .claude/agent-memory/<name>/      (this project, check in to VCS)
#   local:   .claude/agent-memory-local/<name>/ (this project, do NOT check in)
# memory: project

# OPTIONAL — always run this agent as a background task (non-blocking)
# Default: false (agent runs in foreground, blocking the main conversation)
# background: false

# OPTIONAL — effort level for this agent's model calls
# Overrides the session effort level while this agent is active.
# Values: low | medium | high | xhigh | max (available levels depend on model)
# effort: medium

# OPTIONAL — run agent in an isolated git worktree
# Set to "worktree" to give the agent a temporary copy of the repository.
# The worktree is cleaned up automatically if the agent makes no changes.
# Values: worktree
# isolation: worktree

# OPTIONAL — display color in the task list and transcript
# Values: red | blue | green | yellow | purple | orange | pink | cyan
# color: blue

# OPTIONAL — auto-submitted first turn when this agent runs as the main session
# (via --agent flag or `agent` setting in settings.json)
# Commands and skills in this prompt are processed.
# initialPrompt: "Load the project context and summarize the current state."
---

# Agent Name

One-sentence description of what this agent is for and what distinguishes it.

## Responsibilities

- Primary responsibility
- Secondary responsibility
- What it explicitly does NOT do (scope boundary)

## Process

Step-by-step description of how this agent approaches its task.

1. First step
2. Second step
3. Third step

## Output Format

Describe the expected output format. For review agents:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

## Skip

Return skip status when:

- Condition that makes this agent inapplicable

## Ignore

What this agent explicitly does not check (handled by other agents or out of scope).
