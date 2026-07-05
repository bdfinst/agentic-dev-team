# CodeGraph vs Graphify

Two optional, non-overlapping code-intelligence tools may show up in a
project this plugin operates on. Neither is required — a project may have
one, both, or neither, and nothing in the plugin assumes either exists.

## What each tool is

### CodeGraph

Third-party tool (<https://github.com/colbymchenry/codegraph>). Builds a
tree-sitter AST index of source code into a local SQLite database
(`.codegraph/codegraph.db`). Code-symbols-only — it indexes functions,
classes, and call relationships, not prose or non-code artifacts. Queries
(callers, callees, impact analysis) run sub-millisecond against the local
index. It has no knowledge of documentation, schemas, or infrastructure
files.

### Graphify

A knowledge-graph tool (`graphifyy` on PyPI) that is multi-modal: it ingests
code *and* docs, PDFs, schemas, infra files, images, and video into one
graph, using both semantic (embedding-based) and structural (AST/reference)
extraction. Output is a queryable graph (`graphify-out/graph.json`) plus a
plain-language `GRAPH_REPORT.md` and an interactive HTML view, with
community detection to surface cross-document relationships. Because it
spans code and non-code content, it is the better tool for
architecture-level and onboarding questions, not just "what calls this
function."

## How each is installed and invoked here

### CodeGraph

- Offered opt-in during `/init-dev-team`'s "Step 2.5 — Offer CodeGraph"
  ([`skills/init-dev-team/SKILL.md`](../skills/init-dev-team/SKILL.md)):
  the skill checks `command -v codegraph` and the presence of `.codegraph/`,
  then prompts to install and/or run `codegraph init -i`, recording the
  choice in `.claude/init-state.json`.
- Once initialized, a project-root `.mcp.json` registers a `codegraph`
  MCP server (`codegraph serve --mcp`), exposing `mcp__codegraph__*` tools
  (e.g. `codegraph_context`, `codegraph_explore`) to any Claude Code session
  opened in that project.
- `hooks/codegraph_nudge.py` (PreToolUse on `Read`/`Grep`/`Glob`) recommends
  the `codegraph_*` MCP tools over multi-file Read/Grep/Glob exploration
  whenever `.codegraph/` exists and no CodeGraph tool has been used yet in
  the current turn; see
  [`docs/codegraph-nudge.md`](../docs/codegraph-nudge.md) for the full
  sentinel mechanism. `hooks/codegraph_bootstrap.py` (SessionStart) rebuilds
  the local `.db` on a fresh clone when `.codegraph/` is committed but the
  machine-local database is missing.

### Graphify

- A repo-level tool with its own native `/graphify` skill
  (`.claude/skills/graphify/SKILL.md` in this repo), not part of the
  `dev-team` plugin's shipped skill set.
- Build a graph with `graphify extract .` (or the full `/graphify` pipeline),
  which writes `graphify-out/graph.json` (gitignored) plus
  `graphify-out/GRAPH_REPORT.md` and an HTML visualization.
- Query the graph with `graphify query "<question>"` (broad, BFS-style
  context), `graphify path "<A>" "<B>"` (shortest path between two
  concepts), and `graphify explain "<concept>"` (plain-language explanation
  of a single node).
- PreToolUse nudge hooks in `.claude/settings.json` (this repo's own,
  separate from the plugin's `codegraph-nudge`) steer codebase questions
  toward `graphify query` when `graphify-out/graph.json` already exists.
- Keep the graph current after edits with `graphify update .`
  (incremental, AST-only, no LLM cost).

## When to use which

- **CodeGraph** for fast structural queries while editing — callers,
  callees, impact analysis, sub-millisecond lookups against a local SQLite
  index of code symbols.
- **Graphify** for architecture and onboarding questions that span code
  *and* docs, schemas, and infrastructure — anything broader than "who
  calls this function."

## Neither is guaranteed to be present

Both are optional and independently adopted per project:

- CodeGraph requires an explicit `/init-dev-team` opt-in and a successful
  `codegraph init`; a project can decline both the install and the init
  prompts and never have `.codegraph/`.
- Graphify requires someone to run `/graphify` (or `graphify extract`) at
  least once; a project can go its entire life without `graphify-out/`.

Plugin behavior must not assume either tool exists. The `codegraph-nudge`
hook already fails open when `.codegraph/` is absent, and no shipped
`dev-team` skill or agent depends on `graphify-out/` being present.
