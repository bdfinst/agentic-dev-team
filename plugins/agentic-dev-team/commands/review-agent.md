---
name: review-agent
description: >-
  Run a single named review agent against target files. Use this when the
  user names a specific agent (e.g. "run security-review", "check for test
  issues", "run js-fp-review on this file") rather than wanting the full
  suite. Prefer this over /code-review when only one concern is relevant or
  speed matters. Also used by the orchestrator for inline review checkpoints
  during Phase 3 implementation.
argument-hint: "<agent-name> [--changed | --since <ref>] [--path <dir>]"
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *)
---

# Review Agent

Role: worker. This skill performs the actual review using the agent
definition as its specification.

You have been invoked with the `/review-agent` skill. Run a single named review agent.

This command is executed under orchestrator direction. Model selection
follows the Orchestrator Model Routing Table in `.claude/agents/orchestrator.md`.

## Worker constraints

1. **Follow the agent definition exactly.** The agent file is your
   specification — detect what it says to detect, skip what it says
   to skip.
2. **Respect context needs.** When `--changed` or `--since` is used,
   honor the agent's `Context needs` field (diff-only, full-file, or
   project-structure).
3. **Do not add findings beyond the agent's scope.** If the agent
   says "Ignore: naming, tests" — do not flag naming or test issues.
4. **Return structured JSON only.** Output the standard result
   format. Do not add prose commentary.
5. **Be concise.** Issue messages should be one sentence. Suggested
   fixes should be actionable, not explanatory. No preambles or
   filler.

## Parse Arguments

Arguments: $ARGUMENTS

Required: agent name (`$0`, e.g., `test-review`, `js-fp-review`, `security-review`)

Optional:

- `--changed`: Review only uncommitted changes
- `--since <ref>`: Review files changed since a git ref
- `--path <dir>`: Target directory (default: current working directory)

## Steps

### 1. Load agent definition

Read `.claude/agents/<name>.md`. If the file doesn't exist, list available
review agents from `.claude/agents/` (those declaring `Model tier:`) and
ask the user to pick one.

### 2. Determine target files

Same logic as `/code-review`:

- `--changed`: `git diff --name-only` + `git diff --cached --name-only`
- `--since <ref>`: `git diff --name-only <ref>...HEAD`
- Default: glob all source files

### 3. Run review

Follow the agent definition to review each target file. Produce a JSON result:

```json
{
  "agentName": "<name>",
  "status": "pass|warn|fail",
  "issues": [
    {
      "severity": "error|warning|suggestion",
      "file": "<path>",
      "line": 0,
      "message": "<description>",
      "suggestedFix": "<fix>"
    }
  ],
  "summary": "<summary>"
}
```

### 4. Report

Display the result as a formatted summary with issues grouped by file. Include suggested fixes inline.
