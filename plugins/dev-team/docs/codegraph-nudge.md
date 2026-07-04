# codegraph-nudge

A PreToolUse hook that recommends `codegraph_*` MCP tools over multi-file
`Read` / `Grep` / `Glob` exploration when the project has a CodeGraph index.

## What it does

When a project has `.codegraph/` in its cwd, the hook fires on every
`Read`, `Grep`, and `Glob` tool call. It exits 0 silently unless **all** of
the following are true:

1. The tool call looks like multi-file exploration:
   - `Grep` with `path` unset, or `path` pointing to a directory, or `path` containing glob metacharacters.
   - `Glob` with a `pattern` containing `*`, `?`, or `[`.
   - (Single-file `Read` calls are always silent; `Read` is one path.)
2. No `codegraph_*` MCP tool has been used earlier in the current turn
   (see "Sentinel mechanism" below).

When both conditions hold, the hook prints a one-line nudge to stderr:

```text
[codegraph-nudge] CodeGraph is initialized in this project. Prefer codegraph_context or codegraph_explore for multi-file exploration; Grep/Glob/Read for confirming a specific detail.
```

The hook **always exits 0** unless `/careful` mode is active, in which
case it exits 2 (blocking the tool call) and appends `[blocked by /careful]`
to the message. This matches the precedent set by `hooks/destructive_guard.py`.

## Fail-open

Any internal error — malformed JSON on stdin, missing `jq`, unreadable
transcript, missing sentinel — exits 0 without output. The hook is a nudge,
never a gate. A broken hook must never block legitimate `Read` / `Grep` /
`Glob` calls.

## Sentinel mechanism

A companion hook, `hooks/codegraph_turn_mark.py`, runs as a `PostToolUse` hook
on the matcher `mcp__codegraph__.*`. Each time a CodeGraph MCP tool
completes, it writes a small JSON sentinel to
`${CLAUDE_PROJECT_DIR}/.claude/codegraph-turn-state.json`:

```json
{ "transcript_id": "<basename of transcript_path minus extension>",
  "turn_counter": <count of `"type":"user"` lines in transcript> }
```

The nudge hook reads this sentinel on each invocation and re-computes
the current `transcript_id` and `turn_counter` from the live transcript.
If both match the sentinel, a codegraph_* tool was used in the current
turn → the nudge is suppressed. If the user sends another message
(turn boundary), `turn_counter` increments and the sentinel becomes
stale → the nudge fires again.

This avoids walking the full transcript on every `Read` / `Grep` / `Glob`
call (the mark hook does the lookup once, after the codegraph tool runs).

## How to silence it

1. Run a `codegraph_*` MCP tool first in the same turn — the rest of the
   turn's `Read` / `Grep` / `Glob` calls go silent.
2. Use single-file shapes when you really do want raw file IO:
   - `Read` is always silent.
   - `Grep` with `path` set to an explicit file is silent.
   - `Glob` with a literal `pattern` (no metacharacters) is silent.
3. Remove `.codegraph/` from the project — the hook is project-scoped.

## How to escalate it

`/careful` makes the nudge a hard block (`exit 2`). Useful for
production-critical sessions where you want to force codegraph use.

## Source

- `plugins/dev-team/hooks/codegraph_nudge.py`
- `plugins/dev-team/hooks/codegraph_turn_mark.py`
- Registered in `plugins/dev-team/settings.json` under PreToolUse
  (`Read`, `Grep`, `Glob`) and PostToolUse (`mcp__codegraph__.*`).
- Tests: `tests/hooks/codegraph_nudge.bats` and
  `tests/hooks/codegraph_settings_test.bats`.
