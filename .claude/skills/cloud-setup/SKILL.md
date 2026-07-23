---
name: cloud-setup
description: "Use when working in a Claude Code web/cloud session (claude.ai/code) for this repo, or when asked how to install this plugin, run its skills, or set up tooling in a fresh cloud VM — covers the Setup script, the SessionStart fallback hook, and the file-based fallback when network policy blocks plugin install."
---

# Cloud sessions (claude.ai/code)

Plugins are a **local CLI / IDE** feature. A Claude Code web session runs in a
fresh managed VM that clones this repo; setup scripts and env vars are set in the
cloud **UI** (not a repo file) — see
[Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web).

**Install the plugin via the Setup script (loads this session).** Claude
loads all skills, agents, and commands once when it starts, so the plugin must
be on disk *before* Claude launches. The environment **Setup script** (cloud UI) runs
pre-boot and its filesystem is snapshotted and reused — installing the plugin
there makes it load in the **same** session. The `claude` CLI **is** available in
cloud environments. Paste the body of [`.claude/cloud-setup.sh`](../../cloud-setup.sh)
into the *Setup script* field; it installs the toolchain and then the plugin
(`claude plugin marketplace add bdfinst/agentic-dev-team` +
`claude plugin install dev-team@bfinster`), always exiting 0. See
[`docs/cloud-setup.md`](../../../docs/cloud-setup.md) for the focused recipe, the exact
snippet, and the verification probe.

**`SessionStart` hook is a fallback only — it lands next session.**
`.claude/settings.json` registers a `SessionStart` hook
(`.claude/install-dev-team.sh`), gated to **`DEV_TEAM_CLOUD_INSTALL=1`** (set it
in *Environment variables*; leave it unset locally). Because the hook runs *after*
boot, the plugin it installs only takes effect on the **next** session — use the
Setup script for same-session loading.

**If a network policy blocks the install, use the plugin's files directly.** The
skills and agents are plain files in this repo; run any workflow manually:

- a skill → `plugins/dev-team/skills/<name>/SKILL.md` (e.g. `/plan` →
  read `plugins/dev-team/skills/plan/SKILL.md` and follow its steps);
- a review agent → `plugins/dev-team/agents/<name>.md`;
- the catalog → `plugins/dev-team/knowledge/agent-registry.md`.

**Test tooling in cloud.** The same `.claude/cloud-setup.sh` that installs the
plugin also installs this repo's gates (`jq`, `shellcheck`, the Python
dev deps, and `gh`) — one paste into the *Setup script* field covers both. There
is no dedicated secrets store yet — treat env vars as visible to anyone who can
edit the environment.

For the full walkthrough of running a plugin's skills from a web session (the
Setup-script install plus the file-based fallback), see
[`docs/cloud-setup.md`](../../../docs/cloud-setup.md) and
[`docs/using-plugin-skills-in-the-web-environment.md`](../../../docs/using-plugin-skills-in-the-web-environment.md).

See `plugins/dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
