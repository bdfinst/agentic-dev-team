---
name: review
description: >-
  Alias for /code-review. Run all enabled review agents against target files.
  Use this whenever the user asks for a code review, wants feedback on their
  code, says "review my code", "check this before I PR", "what's wrong with
  this", "run the agents", or has just finished implementing a feature.
argument-hint: >-
  [--agent <name>] [--since <ref>] [--path <dir>] [--all] [--json]
  [--force --reason "<text>"] [--static-analysis|--no-static-analysis]
  [--init-risks] [--background]
user-invocable: true
allowed-tools: >-
  Read, Edit, Grep, Glob, AskUserQuestion,
  Bash(git diff *), Bash(npx *), Bash(npm run *),
  Bash(pnpm *), Bash(yarn *), Bash(tsc *), Bash(eslint *),
  Bash(git log *), Bash(gh run *), Bash(semgrep *),
  Bash(pylint *), Skill(review-agent *)
---

# Review (alias)

This is an alias for `/code-review`. Read and follow
`commands/code-review.md` with all arguments passed through.

> **Keep frontmatter in sync.** This alias delegates the entire `/code-review`
> flow, so its `allowed-tools` and `argument-hint` MUST mirror
> `commands/code-review.md`. `allowed-tools` is an allowlist — omitting a tool
> the canonical command needs (e.g. `Edit` for the fix loop, `AskUserQuestion`
> for the fix/report prompt, `Bash(pylint *)` for Python lint) silently breaks
> that capability under `/review`.

Arguments: $ARGUMENTS
