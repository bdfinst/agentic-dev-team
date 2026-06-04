---
name: review
description: >-
  Alias for /code-review. Run all enabled review agents against target files.
  Use this whenever the user asks for a code review, wants feedback on their
  code, says "review my code", "check this before I PR", "what's wrong with
  this", "run the agents", or has just finished implementing a feature.
argument-hint: >-
  [--agent <name>] [--since <ref>] [--path <dir>] [--all]
  [--json] [--force]
user-invocable: true
allowed-tools: >-
  Read, Grep, Glob, Bash(git diff *), Bash(npx *), Bash(npm run *),
  Bash(pnpm *), Bash(yarn *), Bash(tsc *), Bash(eslint *),
  Bash(git log *), Bash(gh run *), Bash(semgrep *),
  Skill(review-agent *)
---

# Review (alias)

Role: orchestrator.

## Orchestrator constraints

1. Pure alias — change no behavior.
2. Pass all arguments through to /code-review unchanged.
3. **Be concise.** Defer all output to code-review.md.

This is an alias for `/code-review`. Read and follow
`commands/code-review.md` with all arguments passed through.

Arguments: $ARGUMENTS

## Steps

### 1. Pass through

Read and follow `commands/code-review.md` with `$ARGUMENTS` unchanged.
