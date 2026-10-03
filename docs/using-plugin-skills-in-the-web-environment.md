# Using a plugin's skills in the Claude Code web environment

Claude Code **plugins are a local CLI / IDE feature**, but you *can* get a
plugin's skills, agents, and slash commands working inside a Claude Code **web**
session (claude.ai/code). The reliable way is to install the plugin from the
environment's **Setup script**. The Setup script runs *before* Claude boots, so
the plugin is on disk before Claude starts. Claude picks it up in the **same**
session. This guide explains why that works. It also gives a file-based
fallback for restrictive environments. It uses this repo's `dev-team` plugin as
the worked example.

> TL;DR: install the plugin in the **Setup script** (cloud UI) → it loads this
> session. The `claude` CLI *is* available in cloud environments. If a network
> policy blocks the install, fall back to running each skill from its file:
> `/<skill>` ≡ "read `plugins/<plugin>/skills/<skill>/SKILL.md` and follow it."
>
> See [`docs/cloud-setup.md`](cloud-setup.md) for the focused, copy-paste setup
> recipe and the verification probe.

---

## 1. Why a plugin must be installed *before* Claude boots

Claude loads all skills, agents, and slash commands **once, when it starts**.
Anything that lands on disk *after* that is invisible to the running session.
The **Setup script** (cloud UI) runs *before* boot, so a plugin installed there
loads in the **same** session. A **`SessionStart` hook** runs *after* boot, so
its install only lands **next** session. The `claude` CLI is available in cloud
environments, so the install commands run fine from the Setup script.
[`docs/cloud-setup.md`](cloud-setup.md) is the canonical write-up of that timing
(with the mechanism-vs-session table). This guide does not repeat it.

So the recommended path is **Option A** (install via the Setup script). **Option
B** (run skills from their files) is the always-works fallback when a network
policy blocks the install.

---

## 2. Option A (recommended) — install via the Setup script

Paste this script into your environment's **Setup script** field
(claude.ai/code → Environment → Setup script). It installs the repo's toolchain
**and** the `dev-team` plugin before Claude boots. The plugin's ~86 skills
(including `/ship`) are then available in the session that starts.

The body of [`.claude/cloud-setup.sh`](https://github.com/bdfinst/agentic-dev-team/blob/main/.claude/cloud-setup.sh) is exactly that
script. It installs `jq`, `shellcheck`, the Python dev deps
(`requirements-dev.txt`), `gh`, and then the plugin
(`claude plugin marketplace add bdfinst/agentic-dev-team` +
`claude plugin install dev-team@bfinster`). Every step is best-effort. The
script ends with `exit 0` so it can never fail session startup.

For the minimal, self-contained snippet, the headless verification probe, and
the version-currency details, see [`docs/cloud-setup.md`](cloud-setup.md), the
canonical setup recipe. A non-zero `dev-team:*` skill count (≈86) from that probe
means the plugin loaded this session.

### Headless / benchmarking caveat — don't nest `claude -p` inside a Remote session

The probe above is a *one-shot* headless call, which is fine. A **headless
benchmark harness** is different. It shells out to
`claude -p "/code-review … --json"` to score runs (for example, the #821
benchmark harness). Run it from a **plain local CLI checkout, not nested inside
a live Claude Code Remote session.**

A nested `claude -p` launched inside a running Remote session is **not
process-isolated the way you would expect**. It inherits the parent's identity
and tool surface from the surrounding Remote runtime. It has two tell-tale
symptoms:

- **Shared `session_id`** — the nested run reports the *same* `session_id` as the
  parent instead of minting a fresh one, so runs are not independent.
- **Remote-injected tool surface** — the nested run sees Remote-runtime tools
  (`CronCreate`, `PushNotification`, `ScheduleWakeup`, and others) that a local
  CLI session never exposes. This changes the tool set under test.

If you ever touch `ScheduleWakeup` directly, know its calling contract. It
requires `prompt` (and `reason`) on every call unless you pass `stop: true`
instead. No "just wait, no prompt" shape exists. This is upstream Remote-runtime
tool-contract behavior. This plugin neither defines nor can wrap it. The skills
that tell an agent to wait on a long-running job now carry that contract in
[`plugins/dev-team/knowledge/long-run-waiting.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/knowledge/long-run-waiting.md).
A malformed arm call therefore cannot silently lose a backstop timer.

This inheritance is an **upstream Claude Code / Remote-runtime behavior. This
plugin repo cannot fix it.** No plugin setting, hook, or config removes the
inherited identity or tools. The behavior is being reported upstream to Claude
Code. Until then, run benchmark harnesses locally.

**Reusable workaround — the `/headless-run` skill.** When you must run a one-shot
headless invocation (a harness case) with maximum isolation, use
[`plugins/dev-team/skills/headless-run/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/headless-run/SKILL.md).
Its helper (`skills/headless-run/scripts/isolated_dispatch.py`) mints a fresh
`--session-id <uuid>` and a clean temp `HOME` + `CLAUDE_CONFIG_DIR`. It also
builds a **scrubbed env** that drops inherited `CLAUDE_*` session/Remote vars.
It runs `--output-format json` with a timeout and no `--resume`. The helper
directly fixes the reused-`session_id` symptom. It cannot remove the
Remote-injected MCP tools, because env vars do not carry them. The
fully supported path is therefore still a local checkout. See the skill's
honest upstream caveat.

The existing isolation precedent is `scripts/run_tdd_experiment.py`. Its
`make_cell_home()` / `cell_env()` / `dispatch()` trio (~lines 155–234) mints a
fresh per-cell `HOME` + `CLAUDE_CONFIG_DIR`. It runs `claude -p …
--output-format json` with **no `--resume`**, a distinct `cwd`, and a hard
`timeout`. That isolates config/memory/telemetry carryover. Note, however, that
`cell_env()` does `env = dict(os.environ)`. It inherits the surrounding Remote
session env and does **not** scrub it. Run nested inside a Remote session, it
would still exhibit the shared `session_id` and Remote tool surface. That is
exactly why the leak is upstream and why the harness must run from a local
checkout.

---

## 3. Option B (fallback) — run the skill from its files (no install)

If a restrictive network policy blocks `marketplace add` / `install`, you do not
need the plugin loaded at all. Every skill, agent, and knowledge file is plain
text in the repo. To "run" a slash command, read its source and follow the
procedure:

| You'd normally type | Do this instead |
| --- | --- |
| `/plan` | Read `plugins/dev-team/skills/plan/SKILL.md` and follow its steps. |
| `/code-review` | Read `plugins/dev-team/skills/code-review/SKILL.md`. |
| `/build` | Read `plugins/dev-team/skills/build/SKILL.md`. |
| a review agent | Read `plugins/dev-team/agents/<name>.md`. |
| the catalog of what's available | Read `plugins/dev-team/knowledge/agent-registry.md` (or the `## Skills Registry` table in `plugins/dev-team/CLAUDE.md`). |

Concretely, ask the agent in your web session:

> "Read `plugins/dev-team/skills/plan/SKILL.md` and run that workflow on `<task>`."

Notes:

- **User-invocable skills** (the slash commands) have `user-invocable: true` in
  their `SKILL.md` frontmatter. Those are the skills meant to be driven this
  way. Other `SKILL.md` files are agent-loaded references that the procedure
  pulls in as needed.
- A skill may reference helper scripts as `${CLAUDE_PLUGIN_ROOT}/scripts/…`. When
  you run the skill from files, that variable is not set. Substitute the
  in-repo path (`plugins/dev-team/scripts/…`) instead.
- Helper scripts need their toolchain (`jq`, `python3`, …). The Setup
  script installs these regardless of which option you use.

This path is robust precisely because it has no dependency on plugin loading.
It is "read the recipe and cook."

---

## 4. The `SessionStart` hook — a documented fallback, not the primary path

This repo also ships a **cloud-only** install hook
(`.claude/install-dev-team.sh`, registered in `.claude/settings.json`). It is a
**no-op unless `DEV_TEAM_CLOUD_INSTALL=1`** is set. It installs the plugin when
the `claude` CLI is present. Otherwise, it falls back to Option-A guidance.

**It cannot load the plugin into the current session.** Because the hook runs
*after* boot, its install only takes effect on the **next** session (see §1).
The repo retains the hook for environments where you cannot edit the Setup
script. For same-session availability, use the Setup script (Option A).

To adapt the hook for your own plugin, copy `.claude/install-dev-team.sh` and
`.claude/settings.json`. Rename the env-var gate and the
`marketplace add`/`install` targets. Keep the no-CLI fallback message.

---

## 5. Caveats specific to the web environment

The general web-environment caveats live in
[`docs/cloud-setup.md`](cloud-setup.md#caveats). They cover boot enumeration,
the Setup-script exit-0 budget, snapshot rebuilds, the ephemeral VM, and
network-policy failures. This guide does not repeat them. Two points bear
directly on the fallback path in this doc:

- **Network policy → Option B.** A restrictive outbound policy can block
  `marketplace add` / `install` / `pip`. That is exactly when you drop to Option
  B (run skills from their files), which has no dependency on plugin loading.
- **No secrets store yet.** Treat environment variables as visible to anyone who
  can edit the environment. Do not put secrets there.

---

## 6. Quick reference

- Install the plugin (this session): paste `.claude/cloud-setup.sh` into the
  **Setup script** field; see [`docs/cloud-setup.md`](cloud-setup.md).
- Verify: `claude -p "List the names of every skill available to you, one per line." --max-turns 1 | grep -c '^dev-team:'` → ≈86.
- Slash command → file (fallback): `/<name>` ⇒ `plugins/<plugin>/skills/<name>/SKILL.md`.
- Find what's available: `plugins/<plugin>/CLAUDE.md` (registry tables) or
  `plugins/<plugin>/knowledge/agent-registry.md`.
- Next-session fallback only: set `DEV_TEAM_CLOUD_INSTALL=1` to enable the
  `SessionStart` hook.
- Authoritative summary: the `cloud-setup` skill (`.claude/skills/cloud-setup/SKILL.md`) or [`docs/cloud-setup.md`](cloud-setup.md).
