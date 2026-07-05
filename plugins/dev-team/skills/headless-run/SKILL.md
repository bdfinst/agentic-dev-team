---
name: headless-run
description: >-
  Run a Claude Code skill or command headlessly in an isolated subprocess —
  fresh session id, clean HOME and config dir, scrubbed env, JSON result,
  timeout. Use for scripted one-shot invocations and benchmark-harness cases
  (e.g. running /code-review once per case), to run an isolated claude -p, or
  to avoid a nested run reusing the parent Remote session identity or tool
  surface. Trigger phrases include "run a skill headlessly", "isolated claude
  -p", "benchmark harness invocation", "run /code-review headlessly", "run it
  once per case", and "avoid nested session reuse".
argument-hint: "<prompt-or-slash-command> [--cwd DIR] [--model MODEL] [--timeout SECS]"
user-invocable: true
allowed-tools: Read, Bash
---

# Headless Run

Role: worker. This skill runs one Claude Code prompt in a maximally isolated
subprocess and returns its JSON result — it does not review, plan, or edit.

## When to use it

Use it for **scripted, one-shot headless invocations** — above all a benchmark
harness that shells out to `claude -p` per case (the #821 harness that runs
`/code-review` once per fixture). A plain nested `claude -p` launched inside a
live Claude Code Remote session inherits the parent's identity and tool surface
(see `docs/using-plugin-skills-in-the-web-environment.md` and issue #842):

- **Reused `session_id`** — the nested run reports the *same* session id as the
  parent, so runs are not independent.
- **Remote-injected tool surface** — the nested run sees Remote-runtime MCP
  tools a local CLI session never exposes, changing the tool set under test.

This skill is the reusable workaround for that #842 constraint.

## Isolation guarantees

The helper builds each dispatch to leak as little parent state as possible:

- **Fresh session id.** A new `uuid.uuid4()` is passed as `--session-id <uuid>`,
  so the nested run cannot reuse the parent `session_id`. This is the key fix.
- **Clean HOME + config.** A throwaway temp `HOME` and `CLAUDE_CONFIG_DIR` — no
  shared config, `memory/`, or telemetry state carries over.
- **Scrubbed env.** Inherited `CLAUDE_*` session/Remote identity vars (e.g.
  `CLAUDE_SESSION_ID`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_ENTRYPOINT`,
  `CLAUDE_CODE_REMOTE`) are removed, then `IS_SANDBOX=1` and
  `DEV_TEAM_TELEMETRY=off` are set fresh.
- **No resume.** The command never uses `--resume`/`-r` or `--fork-session`.
- **JSON result + timeout.** Runs with `--output-format json` and a hard
  subprocess timeout; prints the verified `session_id`, cost, and token usage.

It improves on the existing precedent in `scripts/run_tdd_experiment.py`
(`make_cell_home` / `cell_env` / `dispatch`), which does `env = dict(os.environ)`
and does **not** scrub identity vars.

## Honest upstream caveat

The `session_id` and **tool-surface** inheritance is an **upstream Claude Code /
Remote-runtime behavior — not fixable in this plugin repo**. This skill removes
env-carried identity and forces a fresh session id, but **Remote-injected MCP
tools are not env-carried and cannot be scrubbed here**. The fully-supported
path for a benchmark harness therefore stays a **plain local CLI checkout, not a
run nested inside a Remote session**. Use this skill to maximize isolation when a
local checkout is not available; treat its results as best-effort under that
caveat.

## How to invoke the helper

Run the shipped script, passing the prompt (a slash command works) and optional
`--cwd` / `--model` / `--timeout`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/headless-run/scripts/isolated_dispatch.py" \
  "/code-review" --cwd "$TARGET_REPO" --model sonnet --timeout 900
```

It prints one JSON object (`session_id`, `cost_usd`, token counts, `num_turns`,
`is_error`) and exits non-zero on error or timeout — parse that in the harness.
When running from files without the plugin loaded, substitute the in-repo path
`plugins/dev-team/skills/headless-run/scripts/isolated_dispatch.py`.

## Output

Report the printed JSON result (or the timeout/error line) and the fresh
`session_id` the dispatch used. Be concise — do not restate the script body.
