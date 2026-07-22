# Concurrent use — multiple agents or people on one repo

Short version: **the normal team workflow is safe; for two *agents* on one
machine, give each its own git worktree.**

This resolves the concurrency question (#109): the plugin **documents** a safe
pattern rather than enforcing locks, because git worktrees already solve the
problem cleanly.

## Why the normal case is already safe

The plugin's local coordination state is per-checkout, not shared:

| State | Where | Shared across checkouts? |
| --- | --- | --- |
| Review gate `.review-passed` | repo root, **gitignored** | No — local to each working tree |
| Plan / build progress | `plans/<name>.md` (**tracked**) | Merges through normal git |

So two developers, each with their **own clone**, never collide on these — and
plan files reconcile the way any tracked file does. "Designed for teams" holds
for the standard one-checkout-per-person workflow.

## The unsafe case: two agents sharing ONE working tree

Two background agents, two terminals in the same directory, or a human and an
agent in the same checkout share **one** `.git/index` and **one** set of local
state files. That is where collisions occur (reproduced in
[`../../../tests/repo/test_multiplayer_collision.py`](../../../tests/repo/test_multiplayer_collision.py),
characterized in issue #109):
the shared `.review-passed` gets overwritten (false blocks) and the staged
set interleaves.

## The rule: one worktree per agent

Use a separate [git worktree](https://git-scm.com/docs/git-worktree) for each
concurrent agent. Each worktree has its own working directory, its own index,
and its own gitignored local state — so the agents never share a gate or a
staging area, while still sharing one clone's history and branches.

```bash
# From your main checkout, create an isolated worktree per task/agent:
git worktree add ../myrepo-feature-a feature-a
git worktree add ../myrepo-feature-b feature-b

# Run each agent in its own worktree directory. When done:
git worktree remove ../myrepo-feature-a
```

Guidance:

- **One agent (or session) per worktree.** Don't point two agents at the same
  directory.
- Worktrees are cheap (they share the object store) — make one per parallel task.
- The review gate, model overrides, and staged set are now per-worktree, so the
  collisions above cannot occur.

## Known limitation (separate from concurrency)

The review gate currently binds to staged **paths**, not **content**, so editing
a file's content after review can commit it unreviewed even for a single user.
That is an independent correctness bug tracked in **#193** — fixing it (hash the
staged patch) also hardens the shared-tree case, but the worktree rule above is
the recommended isolation regardless.
