# Using a plugin's skills in the Claude Code web environment

Claude Code **plugins are a local CLI / IDE feature**, but you *can* get a
plugin's skills, agents, and slash commands working inside a Claude Code **web**
session (claude.ai/code). The reliable way is to install the plugin from the
environment's **Setup script**, which runs *before* Claude boots — so the plugin
is on disk before Claude starts and gets picked up in the **same** session. This guide
explains why that works, and gives a file-based fallback for restrictive
environments. It uses this repo's `dev-team` plugin as the worked example.

> TL;DR: install the plugin in the **Setup script** (cloud UI) → it loads this
> session. The `claude` CLI *is* available in cloud environments. If a network
> policy blocks the install, fall back to running each skill from its file:
> `/<skill>` ≡ "read `plugins/<plugin>/skills/<skill>/SKILL.md` and follow it."
>
> See [`docs/cloud-setup.md`](cloud-setup.md) for the focused, copy-paste setup
> recipe and the verification probe.

---

## 1. Why a plugin must be installed *before* Claude boots

Claude loads all skills, agents, and slash commands **once, when it starts.**
Anything that lands on disk *after* that is invisible to the running session.
That single fact drives everything below:

- The environment **Setup script** (configured in the cloud UI) runs **before**
  Claude launches, and its filesystem is snapshotted and reused by later
  sessions. A plugin installed there is on disk before Claude starts, so it
  loads in the **same** session. This is the supported way to install software
  before the session starts (you cannot replace the underlying machine image).
- A **`SessionStart` hook** runs **after** Claude has already launched. A plugin
  it installs is on disk too late for *this* session's enumeration, so it only
  takes effect on the **next** session — the "next-session effect." Useful as a
  fallback, but it is **not** the way to load the plugin into the current
  session.
- The `claude` CLI **is** available in cloud environments, so
  `claude plugin marketplace add …` and `claude plugin install …` run fine from
  the Setup script.

So the recommended path is **Option A** (install via the Setup script). **Option
B** (run skills from their files) is the always-works fallback when a network
policy blocks the install.

---

## 2. Option A (recommended) — install via the Setup script

Paste this script into your
environment's **Setup script** field (claude.ai/code → Environment → Setup
script). It installs the repo's toolchain **and** the `dev-team` plugin before
Claude boots, so the plugin's ~86 skills (including `/ship`) are available in the
session that starts.

The body of [`.claude/cloud-setup.sh`](../.claude/cloud-setup.sh) is exactly that
script — it installs `jq`, `shellcheck`, the Python dev deps
(`requirements-dev.txt`), `gh`, and then the plugin
(`claude plugin marketplace add bdfinst/agentic-dev-team` +
`claude plugin install dev-team@bfinster`). Every step is best-effort and the
script ends with `exit 0` so it can never fail session startup.

For the minimal, self-contained snippet and the why/how, see
[`docs/cloud-setup.md`](cloud-setup.md). Verify it worked with the headless
probe:

```bash
claude -p "List the names of every skill available to you, one per line." \
  --max-turns 1 | grep -c '^dev-team:'
```

A non-zero count (≈86) means the plugin loaded this session.

### Headless / benchmarking caveat — don't nest `claude -p` inside a Remote session

The probe above is a *one-shot* headless call, which is fine. But a **headless
benchmark harness** — one that shells out to `claude -p "/code-review … --json"`
to score runs (e.g. the #821 benchmark harness) — must be run from a **plain
local CLI checkout, not nested inside a live Claude Code Remote session.**

A nested `claude -p` launched inside a running Remote session is **not
process-isolated the way you'd expect**: it inherits the parent's identity and
tool surface from the surrounding Remote runtime. The two tell-tale symptoms:

- **Shared `session_id`** — the nested run reports the *same* `session_id` as the
  parent instead of minting a fresh one, so runs are not independent.
- **Remote-injected tool surface** — the nested run sees Remote-runtime tools
  (`CronCreate`, `PushNotification`, `ScheduleWakeup`, etc.) that a local CLI
  session would never expose, changing the tool set under test.

This inheritance is an **upstream Claude Code / Remote-runtime behavior — it is
not fixable in this plugin repo** (no plugin setting, hook, or config removes the
inherited identity or tools). It is being reported upstream to Claude Code; until
then, run benchmark harnesses locally.

**Reusable workaround — the `/headless-run` skill.** When you must run a one-shot
headless invocation (a harness case) with maximum isolation, use
[`plugins/dev-team/skills/headless-run/SKILL.md`](../plugins/dev-team/skills/headless-run/SKILL.md).
Its helper (`skills/headless-run/scripts/isolated_dispatch.py`) mints a fresh
`--session-id <uuid>`, a clean temp `HOME` + `CLAUDE_CONFIG_DIR`, and a **scrubbed
env** (dropping inherited `CLAUDE_*` session/Remote vars), runs
`--output-format json` with a timeout and no `--resume`. It directly fixes the
reused-`session_id` symptom; it cannot remove the Remote-injected MCP tools
(those are not env-carried), so the fully-supported path is still a local
checkout — see the skill's honest upstream caveat.

The existing isolation precedent is `scripts/run_tdd_experiment.py`: its
`make_cell_home()` / `cell_env()` / `dispatch()` trio (~lines 155–234) mints a
fresh per-cell `HOME` + `CLAUDE_CONFIG_DIR`, runs `claude -p …
--output-format json` with **no `--resume`**, a distinct `cwd`, and a hard
`timeout`. That isolates config/memory/telemetry carryover — but note
`cell_env()` does `env = dict(os.environ)`, so it inherits (does **not** scrub)
the surrounding Remote session env; run nested inside a Remote session it would
still exhibit the shared `session_id` and Remote tool surface. That is exactly
why the leak is upstream and why the harness must run from a local checkout.

---

## 3. Option B (fallback) — run the skill from its files (no install)

If a restrictive network policy blocks `marketplace add` / `install`, you don't
need the plugin loaded at all: every skill, agent, and knowledge file is plain
text in the repo. To "run" a slash command, read its source and follow the
procedure:

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
- Helper scripts need their toolchain (`jq`, `python3`, …); the Setup
  script installs these regardless of which option you use.

This path is robust precisely because it has no dependency on plugin loading —
it's "read the recipe and cook."

---

## 4. The `SessionStart` hook — a documented fallback, not the primary path

This repo also ships a **cloud-only** install hook
(`.claude/install-dev-team.sh`, registered in `.claude/settings.json`). It is a
**no-op unless `DEV_TEAM_CLOUD_INSTALL=1`** is set, installs the plugin when the
`claude` CLI is present, and falls back to Option-A guidance otherwise.

**It cannot load the plugin into the current session.** Because the hook runs
*after* boot, its install only takes effect on the **next** session (see §1). It
is retained for environments where editing the Setup script isn't possible — but
for same-session availability, use the Setup script (Option A).

Adapting this for your own plugin: copy `.claude/install-dev-team.sh` and
`.claude/settings.json`, rename the env-var gate and the
`marketplace add`/`install` targets, and keep the no-CLI fallback message.

---

## 5. Caveats specific to the web environment

- **Boot enumeration.** Skills/agents/commands are enumerated once at boot.
  Install the plugin *before* boot (Setup script) to use it this session; a
  post-boot install (`SessionStart` hook) only lands next session.
- **Setup-script budget & exit code.** The Setup script has a few-minute budget
  and **must exit 0** — a non-zero exit fails session startup. Guard every
  optional step with `|| true` and end with `exit 0`.
- **Snapshot rebuild.** The Setup-script filesystem is snapshotted and reused;
  editing the Setup script (or other environment config) triggers a rebuild on
  the next session.
- **Ephemeral VM.** Commit and push anything you want to keep before the session
  ends; the container is reclaimed afterward.
- **Network policy.** Outbound access is governed by the environment's network
  policy chosen in the cloud UI; an install or `pip` step can fail under a
  restrictive policy — fall back to Option B.
- **No secrets store yet.** Treat environment variables as visible to anyone who
  can edit the environment; don't put secrets there.

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
- Authoritative summary: `CLAUDE.md` → *Cloud sessions (claude.ai/code)*.
