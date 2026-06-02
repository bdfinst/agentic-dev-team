---
name: continue
description: >-
  Resume work from a prior session by reading phase progress files in memory/
  and active plans. Use this when starting a new session on in-progress work,
  or when the user says "continue", "pick up where I left off", "resume",
  or "what was I working on".
argument-hint: ""
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(git log *), Bash(git branch *), Bash(git status *), Bash(git diff *), Bash(ls *)
---

# Continue Session

Role: orchestrator. This command resumes work from a prior session — it does not start new work.

You have been invoked with the `/continue` command.

## Steps

### 1. Scan for in-progress work

Read all files in `memory/` looking for phase progress files. These follow the pattern:
- `memory/research-progress-*.md` — Research phase output
- `memory/plan-progress-*.md` — Plan phase output
- `memory/implementation-progress-*.md` — Implementation phase output
- `memory/decisions.md` — Accumulated decision log

Also check:
- `plans/` directory for active plan files
- `docs/specs/` for design documents without corresponding implementation
- `.claude/review-summaries/` for recent review results
- `corrections/` for unapplied code review fixes

### 2. Check git state

Run `git status` and `git log --oneline -5` to understand:
- Current branch and its relationship to main
- Any uncommitted changes
- Recent commit messages for context

### 3. Summarize current state

Present a structured summary:

```markdown
## Session State

**Branch**: feature/xyz (ahead of main by 3 commits)
**Last phase completed**: Plan (2026-03-17)
**Next phase**: Implement

### In-Progress Work
- [Plan] Widget refactor — 8/12 steps complete
- [Review] 2 unapplied corrections from last review

### Uncommitted Changes
- `src/widget.ts` — modified
- `src/widget.test.ts` — modified

### Recommended Next Action
Continue implementation from step 9 of the widget refactor plan.
```

### 4. Ask for confirmation

Present the recommended next action and ask: "Resume from here, or would you like to do something else?"

If the user confirms, load the appropriate phase context and continue execution.

### 5. Load phase context

Based on the identified phase:
- **Research**: Load research progress file + relevant design doc
- **Plan**: Load plan progress file + design doc
- **Implement**: Load implementation progress file + plan + any review corrections

Follow the Context Loading Protocol for phased loading.
