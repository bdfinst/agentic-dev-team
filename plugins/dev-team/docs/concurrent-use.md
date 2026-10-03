# Concurrent use — multiple agents or people on one repo

Short version: **the normal team workflow is safe. For two *agents* on one
machine, give each its own git worktree.**

This page resolves the concurrency question (#109) for the per-checkout state in
the table below. The plugin **documents** a safe pattern rather than
enforcing locks there, because git worktrees already solve the problem
cleanly.

Separately, a handful of small on-disk state files are lock-serialized (`hooks/lib/atomic_state.py`,

# 1501/#1874/#1889). A single worktree's own hooks read-modify-write or append to these files

- Session and retry counters (`bash_retry_guard.py`, `session_learning_trigger.py`).
- Four of the `.claude/metrics/*.jsonl` telemetry streams: `boundary-events.jsonl`,
  `workflow-states.jsonl`, `iteration-journal.jsonl`, and an `/autoship`
  round log.

Those races occur within one worktree, between concurrent
tool calls or sliced-mode parallel dispatches. They are not the cross-worktree case
this doc covers. Other `.claude/metrics/*.jsonl` streams are not yet
converted (#1896).

## Why the normal case is already safe

The plugin's local coordination state is per-checkout, not shared:

| State | Where | Shared across checkouts? |
| --- | --- | --- |
| Review gate `.pr-review-passed` | `.claude/memory/`, **gitignored** | No — local to each working tree |
| Plan / build progress | `plans/<name>.md` (**tracked**) | Merges through normal git |

So two developers, each with their **own clone**, never collide on these files. Plan files reconcile the way any tracked file does. "Designed for teams" holds
for the standard one-checkout-per-person workflow.

## The unsafe case: two agents sharing one working tree

Two background agents, two terminals in the same directory, or a human and an
agent in the same checkout share **one** `.git/index` and **one** set of local
state files. That is where collisions occur (reproduced in
[`../../../tests/repo/test_multiplayer_collision.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/tests/repo/test_multiplayer_collision.py),
characterized in issue #109). The shared `.pr-review-passed` gets overwritten (false blocks) and the staged
set interleaves.

## The rule: one worktree per agent

Use a separate [git worktree](https://git-scm.com/docs/git-worktree) for each
concurrent agent. Each worktree has its own working directory, its own index,
and its own gitignored local state. The agents never share a gate or a
staging area, but they still share one clone's history and branches.

```bash
# From your main checkout, create an isolated worktree per task/agent:
git worktree add ../myrepo-feature-a feature-a
git worktree add ../myrepo-feature-b feature-b

# Run each agent in its own worktree directory. When done:
git worktree remove ../myrepo-feature-a
```

Guidance:

- **One agent (or session) per worktree.** Do not point two agents at the same
  directory.
- Worktrees are cheap because they share the object store. Make one per parallel task.
- The review gate, model overrides, and staged set are now per-worktree, so the
  collisions above cannot occur.

## Known limitation (separate from concurrency)

The review gate currently binds to staged **paths**, not **content**. Editing
a file's content after review can therefore commit it unreviewed, even for a single user.
That is an independent correctness bug tracked in **#193**. Fixing it (hash the
staged patch) also hardens the shared-tree case. The worktree rule above is
still the recommended isolation.
