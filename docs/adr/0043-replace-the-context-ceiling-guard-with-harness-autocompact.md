# 43. Replace the context ceiling guard with harness autocompact

Date: 2026-09-30

## Status

Accepted

Supersedes [11. Enforce the context ceiling with a transcript-measured PreToolUse hook](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md)

Supersedes [16. Rely on harness-native compaction; the plugin performs structured summarization only](0016-rely-on-harness-native-compaction-the-plugin-performs-structured-summarization-only.md)

Supersedes [37. Block by default at the context ceiling](0037-block-by-default-at-the-context-ceiling-2000.md)

Supersedes [38. Raise the absolute context ceiling from 150K to 350K](0038-raise-the-absolute-context-ceiling-to-350k.md)

Supersedes [39. Only Skill loads are worth blocking at the context ceiling](0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md)

Tracked in [#2177](https://github.com/bdfinst/agentic-dev-team/issues/2177).

## Context

The plugin enforced a context ceiling with `hooks/context_ceiling_guard.py`, a PreToolUse hook that measured transcript occupancy and, past `min(40% of the window, 350K)`, blocked `Skill` loads and warned on `Agent` dispatch until the model wrote a structured `/handoff` file ([ADR 11](0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md), [ADR 37](0037-block-by-default-at-the-context-ceiling-2000.md), [ADR 38](0038-raise-the-absolute-context-ceiling-to-350k.md), [ADR 39](0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md)). [ADR 16](0016-rely-on-harness-native-compaction-the-plugin-performs-structured-summarization-only.md) kept harness auto-compact as the backstop and chose not to lower it.

That guard approximated a capability the harness owns natively and exposes as `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`. The data behind ADR 37 (76+ sessions past 500K under warn-only, 18 past 900K) showed the ceiling mattered; the decision here is that the harness's own threshold is the better place to enforce it, configured per repo by `/dev-team:setup`, instead of a plugin-side blocking hook.

## Decision

1. **Remove `context_ceiling_guard.py`**, its registrations and its tests, together with `scripts/context_ceiling_report.py` and its validation doc. There is no warn-only replacement and no plugin-side context signal.
2. **`/dev-team:setup` writes `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` into the target repo's `.claude/settings.json` `env` block**, default `40`, configurable (`--autocompact-pct N` or a prompt), merged into existing `env` entries and never overwriting other keys.
3. **An advisory SessionStart hook** (`autocompact_setup_nudge.py`, matcher `startup|resume|clear`) prints one line recommending `/dev-team:setup` when the key is absent or invalid. It never blocks and is silenceable.
4. **A SessionStart hook with matcher `compact`** (`post_compact_state_reinject.py`) re-injects the active `/build` phase, step, plan path and unchecked plan items as `additionalContext`, best-effort and fail-open, because a generic harness summary can drop plan-step state (the finding behind ADR 16).
5. **The 350K absolute cap is deliberately dropped.** Only the percent-only threshold applies: 40% of a 1M window is 400K. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (a token-based knob) is deliberately not used anywhere: one knob, one unit, and no second setting that can disagree with the first. This was a stakeholder decision.
6. **`/handoff` remains**, as a manually invoked tool (continue and fork modes). Nothing forces or blocks on it any more.
7. **One clause of ADR 16 is carried forward verbatim:** the plugin never implements compaction itself. Its other clauses (guard-driven summarization, `DEV_TEAM_CONTEXT_STRICT`) are retired.

## Harness constraints this design accepts

Each is tagged **verified** (read from the primary Claude Code documentation, code.claude.com env-vars and hooks references, on 2026-09-30, or observed) or **reported** (taken from secondary sources or memory and not yet confirmed).

- **No plugin-triggered compaction (verified).** Hooks cannot start a compaction or inject `/compact`. `PreCompact` can only block a compaction (exit code 2) and cannot supply focus or summary instructions. The native threshold is the only way to compact at a chosen point.
- **Lower-only threshold (verified).** `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is an integer 1-100, a percentage of the auto-compact window; values above the harness default are ignored. 40 is a lowering, never a raise. The harness default itself (about 83%) is **reported**.
- **The variable works in a real session (verified).** Observed by the repository owner on 2026-09-30: a session compacted at the configured percentage.
- **Fires between turns, not per tool call (reported).** The guard checked every tool call; a long tool loop can overshoot the threshold before compaction runs.
- **Applies to subagents as well as the main session (verified).**
- **Coverage is per repo.** The setting lives in each target repo's settings. A repo that never runs `/setup` keeps the harness default, where the guard used to protect every repo automatically. The nudge only advises; it does not enforce.
- **A `compact` SessionStart hook firing after compaction is documented but not observed here (reported).** The hooks reference lists the `compact` matcher and its `additionalContext` (capped at 10,000 characters, **verified** in the docs); that it fires in a real session and reaches the model is tracked in [#2233](https://github.com/bdfinst/agentic-dev-team/issues/2233). Until that is confirmed, the re-injection hook is best-effort by design.
- **What the harness re-injects after compaction (reported).** It reloads CLAUDE.md and the most recently modified files and invoked skill bodies (capped per skill); plan-step state, file:line anchors and acceptance criteria are not guaranteed to survive.

## Consequences

- Protection depends on each repo running `/dev-team:setup`; unconfigured repos get only the harness default and a one-line nudge.
- The plugin's context handling shrinks to a config writer, two small advisory hooks and a manual `/handoff`; the plugin's most bug-prone hook and its report tooling are gone.
- Compaction is lossier than a structured handoff. The re-injection hook narrows the gap for `/build` state only, and only while `build-phase.json` is present (it is cleared at step completion).
- The 350K cap no longer holds on 1M-window models: sessions can now reach 400K before compaction at the default 40%. Repos that want an earlier point set a lower percentage.
- The "reported" items above must be re-tagged verified or corrected when #2233 and any later observation resolve them.
