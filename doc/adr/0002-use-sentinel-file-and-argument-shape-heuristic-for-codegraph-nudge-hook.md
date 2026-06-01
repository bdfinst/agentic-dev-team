# 2. Use sentinel file and argument-shape heuristic for CodeGraph nudge hook

Date: 2026-06-01

## Status

Accepted

## Context

We added a `PreToolUse` hook (`codegraph-nudge.sh`) that fires on every `Read`, `Grep`, and `Glob` tool call in projects with a CodeGraph index (`.codegraph/` in cwd). When the call looks like exploration, the hook should recommend the indexed `codegraph_*` MCP tools instead. Two implementation questions had non-obvious answers:

1. **How to detect "the agent has already used codegraph this turn"** — so the hook stays silent on the follow-up `Read` that confirms a specific detail (the pattern our own CLAUDE.md guidance recommends). Two designs were considered:
   - **Parse the transcript at PreToolUse time.** Walk `tail -n N` of the JSONL transcript backward to the last `"type":"user"` marker and grep for `mcp__codegraph__*` in the window. Stateless; no extra hook needed.
   - **Sentinel file written by a companion PostToolUse hook.** A small `codegraph-turn-mark.sh` fires after any `mcp__codegraph__.*` tool completes and writes `{transcript_id, turn_counter}` to `${CLAUDE_PROJECT_DIR}/.claude/codegraph-turn-state.json`. The nudge hook reads the sentinel and compares.

2. **How to classify a tool call as "multi-file exploration"** — without duplicating the tool's own file enumeration on every invocation. Two designs were considered:
   - **Expand the glob / walk the directory** to count matches. Accurate but slow (bash `**` needs `shopt -s globstar`, not portable; deep `**` patterns can be expensive), and the cost is paid on every Read/Grep/Glob.
   - **Argument-shape heuristic.** Read-always-single; `Grep` is multi unless `tool_input.path` is a regular file (`test -f`); `Glob` is multi when `tool_input.pattern` contains a glob metacharacter. Coarse but constant-time and zero filesystem walk.

Plan-review (round 1) flagged both questions as blockers:

- **Design & Architecture Critic** rejected transcript-walk: couples the hook to JSONL schema, depends on PostToolUse flush timing, parses MBs of transcript on every Read/Grep/Glob in long sessions, and contradicts the spec which already named `codegraph-turn-state.json`.
- **Design & Architecture Critic** rejected filesystem expansion: `shopt -s globstar` portability, glob-expansion cost, and over-coupling to the live filesystem when the hook is meant to be advisory.

Security review later flagged that even with the bounded sentinel approach, the nudge hook's transcript `grep -c "type":"user"` would scan the full transcript on every Read/Grep/Glob — unbounded growth over a long session.

## Decision

Adopt both refinements:

1. **Sentinel file written by a PostToolUse mark hook.** `codegraph-turn-mark.sh` is registered on matcher `mcp__codegraph__.*`. It writes `{transcript_id, turn_counter}` atomically (mktemp + `mv -f`) to `${CLAUDE_PROJECT_DIR}/.claude/codegraph-turn-state.json`. The nudge hook reads that file, recomputes `transcript_id` (basename of `transcript_path` minus extension) and `turn_counter` (`grep -c '"type":"user"'` over `tail -c 1048576` of the transcript), and suppresses the warning when both match.
2. **Argument-shape heuristic for breadth classification.** `Read` is always silent. `Grep` is multi unless `tool_input.path` exists and is a regular file. `Glob` is multi when `tool_input.pattern` contains `*`, `?`, or `[`. No `find`, no globstar, no expansion.
3. **Cap the transcript scan at 1 MB** (`tail -c 1048576`) on both reader and writer. The turn counter only needs to detect monotonic change within a session, not reflect the absolute all-time count — a fixed-size tail is sufficient and both sides see the same count.

Fail-open posture throughout: any internal error in either hook exits 0 (the hook is a nudge, never a gate). Careful-mode escalation (`exit 2`) is layered on top via the existing `careful-state.json` mechanism, matching `destructive-guard.sh`.

## Consequences

**Easier:**

- Constant-time hook overhead per call (~36–49 ms median wall-clock on the hot path, dominated by process startup, not hook logic). Scales independently of session length and project size.
- Adding the same nudge to another plugin (e.g., the writing-team mirror tracked in `bdfinst/agentic-writing-team#36`) reuses the same mechanism without re-deciding.
- The sentinel is one small JSON file; the schema is documented in `docs/codegraph-nudge.md` and pinned by `tests/hooks/codegraph_nudge.bats`.

**Harder:**

- The mark hook must fire reliably on every `mcp__codegraph__.*` PostToolUse — if Claude Code changes that matcher convention, the suppression silently regresses to "always warn." Fail-open posture absorbs this without breaking workflows.
- Argument-shape heuristic has known false positives (a `Grep` against a directory that happens to contain a single file still warns). Accepted because the warning is advisory, not blocking — false positives nudge the agent toward `codegraph_*`, which is the point.
- Two scripts to maintain instead of one. Mitigated by their shared single-page `docs/codegraph-nudge.md` and a single bats file covering both.

**Risks:**

- **Sentinel timing.** PostToolUse must complete before the next PreToolUse fires. Claude Code's hook ordering guarantees this in practice; if it ever drifts, the user sees one spurious warning per affected turn — never a broken tool call.
- **Transcript schema drift.** If the JSONL schema changes (`"type":"user"` ever stops being the per-user-message marker), the turn counter freezes and the suppression breaks closed (always warns). Detection: bats fixtures in `tests/hooks/fixtures/transcripts/` mirror the current schema; if they need regenerating, that's the signal to update both hooks together.

## References

- Spec: `docs/specs/codegraph-integration.md`
- Plan: `plans/codegraph-integration.md`
- Hook docs: `plugins/agentic-dev-team/docs/codegraph-nudge.md`
- PR: <https://github.com/bdfinst/agentic-dev-team/pull/36>
- Companion (writing-team): <https://github.com/bdfinst/agentic-writing-team/issues/36>
