# code-intelligence-nudge

A PreToolUse hook that recommends whichever of **CodeGraph**, **Repowise**,
and **Graphify** are indexed in the project over multi-file `Read` / `Grep` /
`Glob` exploration. The hook was renamed and generalized from `codegraph-nudge` (#1368).
The original only ever recommended CodeGraph, even on projects where
Repowise or Graphify were also indexed. It pushed agents toward the
narrowest tool even when the question called for a different one.

## What it does

The hook fires on every `Read`, `Grep`, and `Glob` tool call. It exits 0
silently unless **all** of the following are true:

1. The tool call looks like multi-file exploration:
   - `Grep` with `path` unset, `path` pointing to a directory, or `path` containing glob metacharacters.
   - `Glob` with a `pattern` containing `*`, `?`, or `[`.
   - Single-file `Read` calls are always silent, because `Read` is one path.
2. At least one of `.codegraph/`, `.repowise/`, or `graphify-out/graph.json`
   is present in the project's cwd.
3. The tool has not already been used earlier in the current turn (see
   "Sentinel mechanism" below). Graphify is the one exception. See
   "Known asymmetry: Graphify never suppresses" below.

Detection is independent per tool:

- `.codegraph/` must be a directory.
- `.repowise/` must be a directory.
- `graphify-out/graph.json` must be a regular file.

The hook treats a path that exists but has the wrong type as "not present," never as a crash. Examples are `.repowise` as
a plain file, or `graphify-out/graph.json` as a directory. A `graphify-out/` directory without
`graph.json` inside it produces no Graphify nudge.

**One tool present**: the hook prints a single-tool nudge to stderr, for example:

```text
[code-intelligence-nudge] CodeGraph is initialized in this project. Prefer codegraph_explore — structure, call graph, blast radius (not risk, rationale, or non-code content) for multi-file exploration; Grep/Glob/Read for confirming a specific detail.
```

**Two or more tools present**: the hook composes one combined message
naming each present-and-unused tool. The order is **fixed precedence**
(Graphify, then Repowise, then CodeGraph), never the order in which the
filesystem checks happened to run. Each tool gets a short differentiator clause,
so a reader knows *why* to pick one tool over another, not just its name:

```text
[code-intelligence-nudge] Multiple code-intelligence indexes found. Pick whichever matches your question:
- graphify query "<question>" — cross-artifact: code + docs + schemas + infra (non-code content; not a faster CodeGraph/Repowise)
- repowise get_context / get_risk / get_why — risk, rationale, code health, dead code (not raw call-graph structure)
- codegraph_explore — structure, call graph, blast radius (not risk, rationale, or non-code content)
Grep/Glob/Read for confirming a specific detail.
```

Only the present-and-not-yet-used-this-turn tools appear in the bulleted
list. A tool already used this turn (per the sentinel) drops out of the
message entirely. If that leaves zero qualifying tools, the hook is fully
silent (no output at all, not an empty bulleted list).

The hook **always exits 0** unless `/careful` mode is active. In that
case it exits 2 (blocking the tool call) and appends `[blocked by /careful]`
to the message. This matches the precedent set by `hooks/destructive_guard.py`.

## Fail-open

Any internal error exits 0 without output. Examples are malformed JSON on stdin, an unreadable transcript, a
missing or corrupt sentinel, and a wrong-type `.codegraph/`/`.repowise/`
directory or `graphify-out/graph.json` file. The
hook is a nudge, never a gate. A broken hook must never block legitimate
`Read` / `Grep` / `Glob` calls. The hook always reads a malformed sentinel as
"no tool used this turn" rather than raising an error.

## Sentinel mechanism

A companion hook, `hooks/code_intelligence_turn_mark.py`, runs as a
`PostToolUse` hook on two matchers: `mcp__codegraph__.*` and
`mcp__plugin_repowise_repowise__.*`. Each time a recognized CodeGraph or
Repowise MCP tool completes, the hook writes a small JSON sentinel to
`${CLAUDE_PROJECT_DIR}/.claude/code-intelligence-turn-state.json`:

```json
{ "transcript_id": "<basename of transcript_path minus extension>",
  "turn_counter": <count of `"type":"user"` markers in the last ~1 MiB of the transcript>,
  "tools_used": ["codegraph", "repowise"] }
```

`tools_used` **accumulates** rather than overwrites within the same turn.
Suppose a `codegraph_*` tool ran earlier this turn and a `repowise` tool runs
next. The sentinel then lists both families, deduplicated, in
first-used order. A new turn or a new `transcript_id` resets the
list to the family that triggered the write. A new turn means the transcript's `turn_counter` incremented,
because the user sent another message. The accumulation never
carries across a turn boundary.

The nudge hook reads this sentinel on each invocation. It re-computes the
current `transcript_id` and `turn_counter` from the live transcript. If
both match the sentinel, the hook subtracts every family listed in `tools_used`
from the set of qualifying tools before composing the message. A
two-tool project where CodeGraph was already used this turn shows only the
Repowise line (or is fully silent if Repowise was used too).

The hook treats the sentinel as an empty list ("no tool used this turn") in these cases, never as a crash:

- The sentinel is missing or unparseable.
- The sentinel has no `tools_used` field at all (the pre-upgrade schema).
- The `tools_used` field is not a list.

This design avoids walking the full transcript on every `Read` / `Grep` / `Glob`
call. The mark hook does the lookup once, after the CodeGraph/Repowise tool
runs.

### Known asymmetry: Graphify never suppresses

Graphify has no MCP surface. You conventionally invoke it via `Bash`
(`graphify query "<question>"`, `graphify explain "<concept>"`, and so on). No `Bash` matcher
writes into the sentinel. This was a deliberate
scope decision, not an
oversight (see the plan's "Decision-defaults stances" section). CodeGraph's and Repowise's nudge lines drop out of the combined
message once you have used either tool this turn. Graphify's line
cannot be suppressed the same way. It can re-fire immediately after a
CLI-based `graphify query` call, even within the same turn. This is an
accepted tradeoff, not an unfixed bug. This section flags it so a future
contributor does not mistake the asymmetry for a regression.

## How to silence it

1. Run a `codegraph_*` MCP tool, a `repowise` MCP tool, or both first in the
   same turn. The rest of the turn's `Read` / `Grep` / `Glob` calls omit
   that tool's line (or go fully silent if you have used every present tool).
   Graphify is the exception. See "Known asymmetry" above.
2. Use single-file shapes when you want raw file IO:
   - `Read` is always silent.
   - `Grep` with `path` set to an explicit file is silent.
   - `Glob` with a literal `pattern` (no metacharacters) is silent.
3. Remove `.codegraph/`, `.repowise/`, or `graphify-out/` from the
   project. The hook is project-scoped and only nudges for tools it
   detects as present.

## How to escalate it

`/careful` makes the nudge a hard block (`exit 2`). Use it for
production-critical sessions where you want to force use of an available
code-intelligence tool.

## Source

- `plugins/dev-team/hooks/code_intelligence_nudge.py`
- `plugins/dev-team/hooks/code_intelligence_turn_mark.py`
- `plugins/dev-team/hooks/lib/turn_identity.py` (shared `transcript_id`/
  `count_user_lines` computation used by both hooks)
- Registered in `plugins/dev-team/settings.json` under PreToolUse
  (`Read`, `Grep`, `Glob`) and PostToolUse (`mcp__codegraph__.*`,
  `mcp__plugin_repowise_repowise__.*`).
- Tests: `plugins/dev-team/tests/hooks/test_code_intelligence_nudge.py` and
  `plugins/dev-team/tests/hooks/test_code_intelligence_turn_mark.py`.
