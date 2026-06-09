# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

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

Two repo-level guides distill the marketplace conventions:
- [`docs/marketplace-builder-plugin-playbook.md`](docs/marketplace-builder-plugin-playbook.md) — how to build a plugin that scaffolds/audits/maintains marketplace monorepos (shipping hygiene, portability, testing, release/catalog sync).
- [`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md) — how to use a plugin's skills from a Claude Code web session.

## Developing the Plugin

Edit files directly in `plugins/dev-team/`. All plugin components (agents, skills, hooks) live there.

### Prerequisites

The local gates (`scripts/ci-local.sh`, run by the `pre-push` hook) need these tools on every dev machine:

- CLI: `shellcheck`, `bats`, `jq`, `python3` (macOS: `brew install shellcheck bats-core jq python3`)
- Python modules: install the declared dev dependencies once with `python3 -m pip install -r requirements-dev.txt` (PyYAML is required — several bats suites shell out to Python scripts that import it; semgrep for the security-assessment suites; httpx for the red-team harness smoke test).

**One-shot setup:** `bash scripts/dev-setup.sh` validates this toolchain and installs anything missing (Homebrew on macOS, apt-get on Debian/Ubuntu, then the `requirements-dev.txt` deps). It is idempotent — safe to re-run.

`ci-local.sh` checks these up front and exits with an actionable message (pointing at `dev-setup.sh`) if any are missing.

### Shell-script portability

Every shell script — both the dev/CI scripts and the ones shipped inside the plugins — is `bash` and must run on **macOS, Linux, and Windows**. Conventions:

- **macOS** ships bash 3.2, so stay 3.2-safe: no `mapfile`/`readarray`, `declare -A`, `${var,,}`, or `wait -n`; expand possibly-empty arrays with the empty-safe idiom `${arr[@]+"${arr[@]}"}` (bare `"${arr[@]}"` under `set -u` aborts on 3.2).
- **BSD vs GNU coreutils**: avoid GNU-only flags (`readlink -f`, `sed -i` semantics, `date +%N`, `stat -c`, `find -printf`, `timeout`) or guard them with a fallback (e.g. `recon-inventory.sh`'s `readlink -f || python3`, `_lib.sh`'s `date +%s%3N || python3`, `mutation-adapters/lib.sh`'s `timeout`→`gtimeout`→unbounded).
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

## Cloud sessions (claude.ai/code)

Plugins are a **local CLI / IDE** feature. A Claude Code web session runs in a
fresh managed VM that clones this repo; setup scripts and env vars are set in the
cloud **UI** (not a repo file) — see
[Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web).

**Cloud-only auto-install hook.** `.claude/settings.json` registers a
`SessionStart` hook (`.claude/install-dev-team.sh`) that installs the dev-team
plugin — but **only when `DEV_TEAM_CLOUD_INSTALL=1`**. Set that variable in your
cloud environment's *Environment variables* field; leave it unset locally, so the
hook is a no-op on your machine (where the plugin is already installed). Caveats:
the hook can only install if the cloud VM ships the `claude` CLI; if it doesn't,
it falls back to guidance (below). A plugin installed at `SessionStart` takes
effect on the **next** session, not the current one.

**If the plugin can't load (no CLI), use its files directly.** The skills and
agents are plain files in this repo; run any workflow manually:

- a skill → `plugins/dev-team/skills/<name>/SKILL.md` (e.g. `/plan` →
  read `plugins/dev-team/skills/plan/SKILL.md` and follow its steps);
- a review agent → `plugins/dev-team/agents/<name>.md`;
- the catalog → `plugins/dev-team/knowledge/agent-registry.md`.

**Test tooling in cloud.** To run this repo's gates in a cloud session, paste the
body of [`.claude/cloud-setup.sh`](.claude/cloud-setup.sh) into the environment's
*Setup script* field (installs `jq`, `shellcheck`, `bats`, the Python dev deps,
and `gh`). There is no dedicated secrets store yet — treat env vars as visible to
anyone who can edit the environment.

For the full walkthrough of running a plugin's skills from a web session (both the
zero-install file route and the gated auto-install hook), see
[`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md).

See `plugins/dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
