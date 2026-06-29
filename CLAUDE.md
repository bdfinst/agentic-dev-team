# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## Working Rules

- **Always work on a branch.** Never commit directly to `main`. Every change — including documentation-only changes, gitignore tweaks, and one-line fixes — lands via a feature branch and a pull request. If a commit accidentally lands on `main` locally, reset `main` to `origin/main` and move the commit to a branch before pushing. Release commits authored by release-please are the only exception; they arrive as their own PR.
- **Documentation-only PRs auto-merge.** When the diff touches only `*.md` files (plus `.gitignore`, `LICENSE`, or other non-shipping metadata) and changes no code, agent, skill, or hook, arm auto-merge at PR-open time: `gh pr merge <num> --auto --squash`. Required checks still run; the PR lands the moment they pass. Any PR that touches code, agents, skills, hooks, eval fixtures, or marketplace manifests requires explicit human merge.

## Repository Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog (points to plugins/)
plugins/dev-team/          # The plugin source
├── .claude-plugin/plugin.json     # Plugin manifest + version
├── agents/                        # Team agents + review agents
├── skills/                        # Agent-loaded + user-invocable (slash command) skills
├── hooks/                         # PreToolUse and PostToolUse scripts
├── knowledge/                     # Progressive disclosure reference files
├── templates/                     # Language-specific agent templates
├── docs/                          # Plugin-specific docs (architecture, agents, skills, eval system)
├── settings.json                  # Hook registrations (ships with plugin)
├── install.sh                     # Prerequisite checker
└── CLAUDE.md                      # Plugin instructions (ships with plugin)

docs/                              # Cross-plugin dev documentation (roadmaps, spikes, repo-level specs)
plans/                             # Implementation plans (not shipped)
evals/                             # Agent eval fixtures (not shipped)
reports/                           # Review reports (not shipped)
```

Two guides explain how the marketplace works:

- [`docs/marketplace-builder-plugin-playbook.md`](docs/marketplace-builder-plugin-playbook.md) — how to build a plugin that scaffolds/audits/maintains marketplace monorepos (shipping hygiene, portability, testing, release/catalog sync).
- [`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md) — how to use a plugin's skills from a Claude Code web session.

## Developing the Plugin

Edit files directly in `plugins/dev-team/`. All plugin components (agents, skills, hooks) live there.

### Prerequisites

The local gates (`scripts/ci-local.sh`, run by the `pre-push` hook) need these tools on every dev machine:

- CLI: `shellcheck`, `bats`, `jq`, `python3` (macOS: `brew install shellcheck bats-core jq python3`)
- Python modules: install the declared dev dependencies once with `python3 -m pip install -r requirements-dev.txt` (PyYAML is required — several bats suites shell out to Python scripts that import it; semgrep for the security-assessment suites; httpx for the red-team harness smoke test).

**One-shot setup:** `bash scripts/dev-setup.sh` validates this toolchain and installs anything missing (Homebrew on macOS, apt-get on Debian/Ubuntu, then the `requirements-dev.txt` deps). Safe to re-run.

`ci-local.sh` checks these up front and exits with an actionable message (pointing at `dev-setup.sh`) if any are missing.

### Shell-script portability

Every shell script — both the dev/CI scripts and the ones shipped inside the plugins — is `bash` and must run on **macOS, Linux, and Windows**. Conventions:

- **macOS** ships bash 3.2, so stay 3.2-safe: no `mapfile`/`readarray`, `declare -A`, `${var,,}`, or `wait -n`; expand possibly-empty arrays with the empty-safe idiom `${arr[@]+"${arr[@]}"}` (bare `"${arr[@]}"` under `set -u` aborts on 3.2).
- **macOS vs Linux command differences**: avoid Linux-only flags (`readlink -f`, `sed -i` semantics, `date +%N`, `stat -c`, `find -printf`, `timeout`) or guard them with a fallback (e.g. `recon-inventory.sh`'s `readlink -f || python3`, `_lib.sh`'s `date +%s%3N || python3`, `mutation-adapters/lib.sh`'s `timeout`→`gtimeout`→unbounded).
- **Windows = Git Bash.** Native `cmd.exe`/PowerShell are not targets; the plugin's hooks and helper scripts run under [Git Bash](https://git-scm.com/download/win) (the POSIX shell Claude Code uses for its Bash tool on Windows). Each plugin's `install.sh` detects Windows-without-Git-Bash and tells the user to install it; `scripts/dev-setup.sh` does the same for contributors.

### Testing locally

Register the local checkout as a marketplace, then install from it into a test project:

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install --scope project dev-team@bfinster
# Or from the published marketplace (GitHub):
# claude plugin marketplace add bdfinst/agentic-dev-team
# claude plugin install dev-team@bfinster
```

### Adding agents, skills, or hooks

- **Agent**: Add a `.md` file to `plugins/dev-team/agents/`
- **Agent-loaded skill**: Add a `SKILL.md` under `plugins/dev-team/skills/<name>/`
- **User-invocable skill** (slash command): Add a `SKILL.md` under `plugins/dev-team/skills/<name>/` with `user-invocable: true` in frontmatter
- **Hook**: Add a `.sh` script to `plugins/dev-team/hooks/` and register it in `plugins/dev-team/settings.json`

After changes, run `/agent-audit` to verify structural compliance.

### Releasing

Releases are managed by release-please. Push conventional commits to main:

- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE` → major version bump

A release PR is opened automatically. Merging it creates a GitHub Release with a version tag.

**Squash-merge titles must be conventional.** This repo squash-merges PRs, so the **PR title is the only thing release-please reads** for the version bump — not the commit messages in the body. A PR titled `Add X` (no `feat:`/`fix:` prefix) is invisible to release-please and silently skips the version bump, even when its squashed body contains conventional commits. Title every PR conventionally. To recover a release that was missed this way, land a follow-up commit carrying a `Release-As: X.Y.Z` footer.

## Cloud sessions (claude.ai/code)

Plugins are a **local CLI / IDE** feature. A Claude Code web session runs in a
fresh managed VM that clones this repo; setup scripts and env vars are set in the
cloud **UI** (not a repo file) — see
[Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web).

**Install the plugin via the Setup script (loads this session).** Claude
loads all skills, agents, and commands once when it starts, so the plugin must
be on disk *before* Claude launches. The environment **Setup script** (cloud UI) runs
pre-boot and its filesystem is snapshotted and reused — installing the plugin
there makes it load in the **same** session. The `claude` CLI **is** available in
cloud environments. Paste the body of [`.claude/cloud-setup.sh`](.claude/cloud-setup.sh)
into the *Setup script* field; it installs the toolchain and then the plugin
(`claude plugin marketplace add bdfinst/agentic-dev-team` +
`claude plugin install dev-team@bfinster`), always exiting 0. See
[`docs/cloud-setup.md`](docs/cloud-setup.md) for the focused recipe, the exact
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
plugin also installs this repo's gates (`jq`, `shellcheck`, `bats`, the Python
dev deps, and `gh`) — one paste into the *Setup script* field covers both. There
is no dedicated secrets store yet — treat env vars as visible to anyone who can
edit the environment.

For the full walkthrough of running a plugin's skills from a web session (the
Setup-script install plus the file-based fallback), see
[`docs/cloud-setup.md`](docs/cloud-setup.md) and
[`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md).

See `plugins/dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
