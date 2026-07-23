# CodeGraph, Repowise, and Graphify

Three optional, complementary code-intelligence tools may show up in a
project this plugin operates on. None is required — a project may have any
subset (including none), and nothing in the plugin assumes any of them
exists. When present, they let agents read verified skeletons, resolved call
graphs, modification risk, and decision rationale instead of re-reading whole
files and grepping for callers — cheaper and more accurate. When absent, the
grant is inert and agents fall back to `Read`/`Grep`/`Glob`.

## What each tool is

### CodeGraph

Third-party tool (<https://github.com/colbymchenry/codegraph>). Builds a
tree-sitter AST index of source code into a local SQLite database
(`.codegraph/codegraph.db`). Code-symbols-only — it indexes functions,
classes, and call relationships, not prose or non-code artifacts. Queries
(callers, callees, impact analysis) run sub-millisecond against the local
index. It has no knowledge of documentation, schemas, or infrastructure
files.

### Repowise

A codebase-documentation / wiki engine (`repowise` on PyPI) that indexes a
repository into a queryable knowledge base and exposes it as an **MCP
server**. Its tools answer *contextual* questions about the code rather than
raw structural ones: `get_overview` returns an architecture-level summary of
the whole workspace; `get_context` / `get_symbol` return documented context
and verified skeletons for a file, module, or symbol; `search_codebase` is
semantic (natural-language) search; `get_answer` answers a free-form question
against the indexed wiki; `get_risk` estimates the modification risk of a
change; `get_why` surfaces the recorded architectural-decision rationale
behind a piece of code; `get_health` reports code-health signals (churn,
complexity, coverage-adjacent risk) and `get_dead_code` flags unreferenced
code — both workspace-scoped rather than file-scoped, so they run over the
whole indexed repo instead of a single symbol. It can index without any LLM
API key (a keyless index), writing its store under `.repowise/`. Because it
layers documentation, risk, rationale, and workspace-wide health signals on
top of structure, it complements CodeGraph's pure call-graph view.

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

- Offered opt-in during `/project-init`'s "Step 4c — Offer graph-tools"
  ([`skills/project-init/SKILL.md`](../skills/project-init/SKILL.md)) as part
  of the CodeGraph + Repowise + Graphify all-or-none group: the skill checks
  `command -v codegraph` and the presence of `.codegraph/`, and when the group
  is accepted **installs the CLI keylessly** (`npm install -g
  @colbymchenry/codegraph`) and builds the index non-interactively
  (`codegraph init .`, no `-i`), recording the choice in
  `.claude/init-state.json` (issue #1134).
- **Strictly personal, user-level tooling — never committed.** Once
  initialized, the skill prints the manual command
  (`claude mcp add codegraph -- codegraph serve --mcp`) for the user to
  register the `codegraph` MCP server at **user scope**, exposing a single
  tool, `codegraph_explore` (`mcp__codegraph__explore`), to Claude Code
  sessions on that machine. One call returns the verbatim source of the
  relevant symbols grouped by file, the call path among them, and a
  blast-radius summary of what depends on them — Read-equivalent output, but
  with structure attached. Nothing is written to a project-tracked
  `.mcp.json`, and `.codegraph/` is never committed — only
  `.codegraph/codegraph.db` stays gitignored and machine-local, per project.
- `hooks/codegraph_nudge.py` (PreToolUse on `Read`/`Grep`/`Glob`) recommends
  the `codegraph_*` MCP tools over multi-file Read/Grep/Glob exploration
  whenever `.codegraph/` exists and no CodeGraph tool has been used yet in
  the current turn; see
  [`docs/codegraph-nudge.md`](../docs/codegraph-nudge.md) for the full
  sentinel mechanism. `hooks/codegraph_bootstrap.py` (SessionStart) rebuilds
  the local `.db` on a fresh clone when `.codegraph/` is committed but the
  machine-local database is missing.

### Repowise

- Offered opt-in during `/project-init`'s "Step 4c — Offer graph-tools"
  ([`skills/project-init/SKILL.md`](../skills/project-init/SKILL.md)),
  alongside CodeGraph and Graphify as one **all-or-none** group.
- Installed keyless (`uv`/`pipx`/`pip`), it indexes without prompting for an
  LLM API key and stores its index under `.repowise/`, which is gitignored so
  the index never clutters the repo.
- Registered as an MCP server, it exposes
  `mcp__plugin_repowise_repowise__{get_overview,get_context,get_symbol,search_codebase,get_answer,get_risk,get_why,get_health,get_dead_code}`
  (and more) to Claude Code sessions.
- **Server-name coupling caveat.** The tool names agents grant use the literal
  server prefix `mcp__plugin_repowise_repowise__*`. If a given install exposes
  Repowise under a different MCP server name, those grants are **inert** — no
  error, agents just fall back to `Read`/`Grep`/`Glob`. Keep the fallback in
  mind wherever a Repowise tool is assumed.

### Graphify

- A repo-level tool with its own native `/graphify` skill
  (`.claude/skills/graphify/SKILL.md` in this repo), not part of the
  `dev-team` plugin's shipped skill set.
- Also offered opt-in during `/project-init`'s Step 4c, after the keyless
  CodeGraph + Repowise pair. **Graphify's AST structural graph builds keyless**
  — `graphify extract .` runs the AST pass with no model/API key, exits 0, and
  produces the `graph.json` the agents traverse (issue #1224). A model/API key
  is required **only** for the semantic-enrichment layer: human-readable
  community names (`graphify label`) and inferred edges (`extract --mode
  deep`). When accepted, the skill builds the keyless graph (`graphify extract
  .`, or `graphify update .` when a graph already exists) and offers enrichment
  only when a key is present; when graphify is absent, consuming agents fall
  back to `Read`/`Grep`/`Glob`.
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
- **Repowise** for *contextual* code questions — documented context and
  verified skeletons (`get_context`/`get_symbol`), semantic search
  (`search_codebase`), modification risk (`get_risk`), decision rationale
  (`get_why`), and workspace-wide code health/dead-code signals
  (`get_health`/`get_dead_code`). Reach for it when the question is "what
  does this do / why does it exist / how risky is changing it / how healthy
  is this area," not "who calls it."
- **Graphify** for architecture and onboarding questions that span code
  *and* docs, schemas, and infrastructure — anything broader than "who
  calls this function."

### Routing precedence

This is guidance for the *model* choosing which tool to reach for — it is
not hook-enforced logic; nothing in `code_intelligence_nudge.py` inspects
the question text, since only the model sees the natural-language task
behind a Read/Grep/Glob call. When more than one tool is indexed, prefer in
this order:

1. **Non-code content** (docs, schemas, infra, cross-artifact questions) →
   **Graphify**.
2. **Risk, rationale, code health, or dead code** → **Repowise**.
3. **Pure structure or call-graph** (who calls this, what does this affect)
   → **CodeGraph**.

The three overlap only lightly: CodeGraph is the fastest for pure call
graphs, Repowise adds documentation/risk/rationale over structure, and
Graphify is the widest net across non-code artifacts. Prefer whichever is
present for the question at hand; use more than one when they're all indexed.

## None is guaranteed to be present

All three are optional and independently adopted per project:

- CodeGraph requires an explicit `/project-init` opt-in and a successful
  `codegraph init`; a project can decline both the install and the init
  prompts and never have `.codegraph/`.
- Repowise requires the `/project-init` graph-tools opt-in and a keyless
  index; a project can decline it and never have `.repowise/` or the MCP
  server registered — and even when installed, the grant is inert if the
  server name differs (see the coupling caveat above).
- Graphify requires someone to run `/graphify` (or `graphify extract`) at
  least once; a project can go its entire life without `graphify-out/`.

Plugin behavior must not assume any of the three exists. The `codegraph-nudge`
hook already fails open when `.codegraph/` is absent, Repowise/CodeGraph MCP
grants are inert when their servers are absent, and no shipped `dev-team`
skill or agent depends on `graphify-out/` being present. `Read`/`Grep`/`Glob`
is the always-available fallback.
