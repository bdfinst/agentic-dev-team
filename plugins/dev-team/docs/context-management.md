# Context Management

How the plugin keeps a session's context in check: the harness compacts at a
percentage `/dev-team:setup` configures, a pair of small SessionStart hooks
nudge and restore state, and `/handoff` stays available by hand. For the
runtime procedure (what to load, when), see [Context Loading
Protocol](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/context-loading-protocol/SKILL.md);
for manual compression and side-task forks, see
[Handoff](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/handoff/SKILL.md).

The design record is [ADR 0043](../../../docs/adr/0043-replace-the-context-ceiling-guard-with-harness-autocompact.md),
which replaced the former context-ceiling hook (ADRs 0011, 0016, 0037-0039).

## How it works

1. **Harness autocompact, configured per repo.** `/dev-team:setup` writes
   `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` into the repo's `.claude/settings.json`
   `env` block (default `40`). The harness then compacts the conversation
   when it reaches that percentage of its auto-compact window. It applies to
   subagents as well as the main session.
2. **A setup nudge.** On `startup`, `resume` and `clear`, the SessionStart
   hook `autocompact_setup_nudge.py` prints one line recommending
   `/dev-team:setup` when the key is absent or invalid in the process env,
   `.claude/settings.local.json`, `.claude/settings.json` and user settings.
   It is advisory, never blocks, and never fires on `compact`.
3. **State restore after compaction.** A SessionStart hook with matcher
   `compact`, `post_compact_state_reinject.py`, re-injects the active `/build`
   phase, step, plan path and unchecked `## Build Progress` items as
   `additionalContext` (at most 10,000 characters; phase and step survive
   truncation first). It reads `.claude/memory/build-phase.json`, so it only
   has something to restore while a build is in progress (a step, or
   between steps). It is
   best-effort and fail-open.
4. **`/handoff` is manual.** Run it yourself to compress the conversation
   (continue mode) or split off a side task (fork mode).
   Write a full summary to `.claude/memory/` so the next phase starts from a
   file. Nothing forces or blocks on it.

## Configuring the threshold

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/set_autocompact_env.py" --project-dir . --yes
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/set_autocompact_env.py" --project-dir . --autocompact-pct 30
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/set_autocompact_env.py" --project-dir . --no-autocompact
```

`/dev-team:setup` runs the same script (Step 9b). The value is an integer
1-100 written as a string, merged into existing `env` entries. The harness
can only lower its threshold; values above its default (about 83%, reported)
have no effect, and the script warns when you pick one. It also warns when a
process-env or `settings.local.json` entry shadows the project value.

There is no absolute token cap: the percentage applies to the window, so 40%
of a 1M window is 400K. The former 350K cap was deliberately dropped.

To silence the nudge without configuring autocompact, set
`DEV_TEAM_AUTOCOMPACT_NUDGE=0` or create `.claude/memory/autocompact-nudge-off`
(`--no-autocompact` creates it).

## What to expect

- **Coverage is per repo.** A repo that never runs `/setup` keeps the harness
  default, which is much later than 40%. The nudge advises; it does not
  enforce.
- **Compaction is generic.** The harness summary can drop plan-step state,
  file:line anchors and acceptance criteria. The re-inject hook restores
  `/build` phase/step and plan progress only; for anything else, write a
  structured summary with `/handoff` before you need it.
- **Timing.** The threshold is checked between turns (reported, not
  verified), so one long tool loop can overshoot it.
- **`compact` SessionStart firing is unconfirmed.** That it fires after a
  real compaction and reaches the model is tracked in
  [#2233](https://github.com/bdfinst/agentic-dev-team/issues/2233).

## Why a low threshold

The 40% default is a conservative planning target, not a claimed accuracy
cliff:

- Chroma's [Context Rot study](https://www.trychroma.com/research/context-rot)
  found degradation across 18 models (including Claude 4) is gradual, not a
  sharp drop at any single percentage.
- Needle-in-a-haystack benchmarks like RULER and NoLiMa show a model's
  *effective* context is often only about half its advertised window.
- Anthropic's [effective context engineering
  guidance](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  recommends proactive compaction well ahead of the limit.

## Troubleshooting

**"The nudge keeps firing after I ran setup."** A process-env or
`settings.local.json` value can shadow the project one; the nudge names the
source of an invalid value. Fix or remove that entry.

**"Nothing restored after compaction."** `build-phase.json` is deleted when the plan
completes, and records older than four hours are ignored; with no active
build there is nothing to restore. Also check #2233.

**"The setup script refuses to write."** It aborts, leaving the file
untouched, when `.claude/settings.json` is malformed, is a symlink, is not a
JSON object, or has a non-object `env`. Fix the file and re-run.

## Source

- `plugins/dev-team/scripts/set_autocompact_env.py` (writer),
  `plugins/dev-team/hooks/lib/autocompact_config.py` (shared detector).
- `plugins/dev-team/hooks/autocompact_setup_nudge.py`,
  `plugins/dev-team/hooks/post_compact_state_reinject.py`,
  `plugins/dev-team/hooks/lib/build_state.py`.
- Registered in `plugins/dev-team/hooks/hooks.json` and
  `plugins/dev-team/settings.json` under `SessionStart`.
