# Using a plugin's skills in the Claude Code web environment

Claude Code **plugins are a local CLI / IDE feature.** A Claude Code *web* session
(claude.ai/code) runs in a fresh managed VM that clones your repo but does **not**
load installed plugins the way your laptop does. This guide explains how to use a
plugin's skills (and agents) from inside a web session anyway — both the
zero-install path and the auto-install path — using this repo's `dev-team` plugin
as the worked example.

> TL;DR: a plugin skill is just a file. `/<skill>` ≡ "read
> `plugins/<plugin>/skills/<skill>/SKILL.md` and follow it." You can always run a
> skill manually; the install hook is an optional convenience for the *next*
> session.

---

## 1. Why plugins don't "just work" in a web session

- Plugins install via the `claude` CLI (`claude plugin install …`). A web VM may
  not even ship that CLI.
- The VM is **ephemeral and per-session**: anything installed during a session is
  gone at the end, and a plugin installed at `SessionStart` only takes effect on
  the **next** session (the slash commands aren't registered mid-session).
- Setup (env vars, the Setup script) is configured in the **cloud UI**, not from a
  repo file — see [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web).

So in a web session you have two reliable options, below. Option A always works.

---

## 2. Option A — run the skill from its files (no install)

Every skill, agent, and knowledge file is plain text in the repo. To "run" a slash
command, read its source and follow the procedure:

| You'd normally type | Do this instead |
|---|---|
| `/plan` | Read `plugins/dev-team/skills/plan/SKILL.md` and follow its steps. |
| `/code-review` | Read `plugins/dev-team/skills/code-review/SKILL.md`. |
| `/build` | Read `plugins/dev-team/skills/build/SKILL.md`. |
| a review agent | Read `plugins/dev-team/agents/<name>.md`. |
| the catalog of what's available | Read `plugins/dev-team/knowledge/agent-registry.md` (or the `## Skills Registry` table in `plugins/dev-team/CLAUDE.md`). |

Concretely, just ask the agent in your web session:

> "Read `plugins/dev-team/skills/plan/SKILL.md` and run that workflow on `<task>`."

Notes:
- **User-invocable skills** (the slash commands) have `user-invocable: true` in
  their `SKILL.md` frontmatter — those are the ones meant to be driven this way.
  Other `SKILL.md` files are agent-loaded references the procedure will pull in as
  needed.
- A skill may reference helper scripts as `${CLAUDE_PLUGIN_ROOT}/scripts/…`. When
  you run it from files, that variable isn't set — substitute the in-repo path
  (`plugins/dev-team/scripts/…`) instead.
- Helper scripts need their toolchain (`jq`, `bats`, `python3`, …); see §4.

This path is robust precisely because it has no dependency on the CLI or on plugin
loading — it's "read the recipe and cook."

---

## 3. Option B — auto-install via a gated SessionStart hook

This repo ships a **cloud-only** install hook so that, when the web VM *does* have
the `claude` CLI, the plugin is installed for the next session automatically.

How it's wired (`.claude/settings.json` → `.claude/install-dev-team.sh`):

- It is a **no-op unless `DEV_TEAM_CLOUD_INSTALL=1`** is set. Set that variable in
  your web environment's **Environment variables** field. Leave it unset locally,
  so your laptop (where the plugin is already installed) is never touched.
- In a gated cloud session it:
  - installs the plugin if `claude` is present (`marketplace add` + `install`,
    time-boxed so it can never hang session start); **effect lands next session.**
  - if `claude` is **absent**, emits `additionalContext` telling the agent to fall
    back to Option A (run skills from their files).
- It's **fail-open** — it never blocks a session from starting.

Adapting this for your own plugin: copy `.claude/install-dev-team.sh` and
`.claude/settings.json`, rename the env-var gate and the
`marketplace add`/`install` targets, and keep the no-CLI fallback message.

---

## 4. Make the toolchain available (for skills that run scripts)

Some skills shell out to `jq`, `shellcheck`, `bats`, or `python3`. In a web
session, install them up front via the environment's **Setup script** field
(cloud UI), not a repo file. Paste the body of [`.claude/cloud-setup.sh`](../.claude/cloud-setup.sh)
— it installs `jq`, `shellcheck`, `bats`, the Python dev deps
(`requirements-dev.txt`), and `gh`. Locally, `bash scripts/dev-setup.sh` does the
equivalent.

---

## 5. Caveats specific to the web environment

- **Next-session effect.** A plugin installed at `SessionStart` is available the
  *next* session, not the current one. For the current session, use Option A.
- **Ephemeral VM.** Commit and push anything you want to keep before the session
  ends; the container is reclaimed afterward.
- **Network policy.** Outbound access is governed by the environment's network
  policy chosen in the cloud UI; an install or `pip` step can fail under a
  restrictive policy — fall back to Option A.
- **No secrets store yet.** Treat environment variables as visible to anyone who
  can edit the environment; don't put secrets there.

---

## 6. Quick reference

- Slash command → file: `/<name>` ⇒ `plugins/<plugin>/skills/<name>/SKILL.md`.
- Find what's available: `plugins/<plugin>/CLAUDE.md` (registry tables) or
  `plugins/<plugin>/knowledge/agent-registry.md`.
- Enable auto-install (next session): set `DEV_TEAM_CLOUD_INSTALL=1` in the web
  environment's Environment variables.
- Provision tools: paste `.claude/cloud-setup.sh` into the Setup script field.
- Authoritative summary: `CLAUDE.md` → *Cloud sessions (claude.ai/code)*.
