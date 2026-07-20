# 12. Auto-bootstrap the CodeGraph index per clone

Date: 2026-06-25

## Status

Accepted

Builds on [2. Use sentinel file and argument-shape heuristic for CodeGraph nudge hook](0002-use-sentinel-file-and-argument-shape-heuristic-for-codegraph-nudge-hook.md).

> **Path and command note (2026-07-20):** the bash-removal effort (ADR 0014, completed by ADR 0015) rewrote `codegraph-bootstrap.sh` and `init-dev-team-linux.sh` as Python (`.py`) files, and retired their `.bats` tests in favor of pytest `test_*.py` files. Separately, `/init-dev-team` was split into `/setup` and `/project-init`. This ADR is preserved verbatim as a historical record.

## Context

CodeGraph gives agents code intelligence over an index of the repo. That index is a SQLite database (`.codegraph/codegraph.db`) **derived from source and machine-local** — `.codegraph/.gitignore` excludes `*.db`, so it is never committed. A team that adopts CodeGraph therefore faces a sharing problem: how does every teammate's clone get a working index without each developer remembering to run `codegraph init` by hand?

Two things need to travel with the repo for CodeGraph to "just work" on a fresh clone:

1. **The opt-in signal** — the committed `.codegraph/` directory (its `.gitignore`). This is the same sentinel `codegraph-nudge.sh` already keys off; a repo that never adopted CodeGraph has no `.codegraph/`, so any automation must stay a no-op there and never index a project the maintainer did not bless.
2. **A way to (re)build the local `.db`** on first use, and to keep it fresh after that.

The freshness half is already handled when an MCP server is registered: `codegraph serve --mcp` runs a file-watcher and does a connect-time catch-up. So the missing piece is the **initial** build on a clone that has the opt-in signal but no local `.db` yet.

Open questions:

- **Where to trigger the initial build.** A `SessionStart` hook can see the cloned repo before any work begins. The alternative — relying on the developer to run `codegraph init` — is exactly the manual step we want to remove.
- **Blocking vs detached build.** Indexing a large repo takes many seconds; blocking `SessionStart` on it would stall every session start.
- **Missing binary.** A teammate may not have `codegraph` installed.

## Decision

Add `hooks/codegraph-bootstrap.sh`, a `SessionStart` hook (registered in `settings.json`) that, with CWD = the session's project dir:

- **no `.codegraph/`** → exit 0 (repo has not adopted CodeGraph — never index it);
- **`.codegraph/` + local `.db` present** → exit 0 (the MCP watcher keeps it current);
- **`.codegraph/` + `.db` missing + binary present** → build the index in the **background** (`setsid`, falling back to `nohup`) so `SessionStart` never blocks, printing a one-line notice; codegraph's own lock file makes a concurrent `init` fail harmlessly, so no extra spawn guard is needed;
- **`.codegraph/` + `.db` missing + binary absent** → print a one-line install nudge and exit 0.

Fail-open throughout: malformed input or any error exits 0 — a bootstrap hook must never block a session. Test seams (`CODEGRAPH_BIN`, `CODEGRAPH_DB_FILE`, `CODEGRAPH_BOOTSTRAP_SYNC`) let the bats suite drive the foreground path against a fake binary.

Complementarily, `/init-dev-team` (and `init-dev-team-linux.sh`) — after a successful `codegraph init` — writes a project-root `.mcp.json` registering `codegraph serve --mcp` (deep-merged so existing servers are preserved) and tells the user to commit it alongside `.codegraph/.gitignore`. Committing those two artifacts is what lets every later clone bootstrap automatically. The tools never `git add`/`commit` on the user's behalf.

## Consequences

- Adopting CodeGraph becomes a commit-two-files action (`.codegraph/.gitignore` + `.mcp.json`); every clone then self-bootstraps with no per-developer `codegraph init`.
- A repo without `.codegraph/` is completely unaffected — the hook is a no-op.
- The first session on a fresh clone runs with a stale/absent index for a few seconds while the background build completes; the notice tells the user to fall back to Read/Grep/Glob until it finishes.
- Teammates without the binary get an actionable install nudge rather than a silent failure.
- Behavior is covered by `tests/hooks/codegraph_bootstrap.bats`, and the settings registration plus the init `.mcp.json` flow by `tests/hooks/codegraph_settings_test.bats` and `tests/commands/init_dev_team_codegraph_test.bats`.
