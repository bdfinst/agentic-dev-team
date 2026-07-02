# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## Working Rules

- **Always work on a branch.** Never commit directly to `main`. Every change — including documentation-only changes, gitignore tweaks, and one-line fixes — lands via a feature branch and a pull request. If a commit accidentally lands on `main` locally, reset `main` to `origin/main` and move the commit to a branch before pushing. Release commits authored by release-please are the only exception; they arrive as their own PR.
- **Rebase-only merges.** `main` is protected by a ruleset that requires **signed commits** and forbids force-pushes. GitHub's squash/merge-commit strategies synthesize new commits with no signature and are blocked by the ruleset; **rebase merge is the only strategy that lands PRs**. Configure your local git to sign commits (`git config --global commit.gpgsign true` plus a key) so every commit you push is `G`-verified — see `git log --pretty="%h %G? %s"` to check.
- **Documentation-only PRs auto-merge.** When the diff touches only `*.md` files (plus `.gitignore`, `LICENSE`, or other non-shipping metadata) and changes no code, agent, skill, or hook, arm auto-merge at PR-open time: `gh pr merge <num> --auto --rebase`. Required checks still run; the PR lands the moment they pass. Any PR that touches code, agents, skills, hooks, eval fixtures, or marketplace manifests requires explicit human merge.

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

### Script authoring — Python for cross-OS scripts

**Every new script in this repo is authored in Python 3.8+ using stdlib only.** See [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md) for the full decision, alternatives, and consequences. Concretely:

- **New shipped hooks, dev/CI helpers, and user-invocable tooling land as `.py` files.** No new `.sh` files enter `plugins/dev-team/` after ADR 0014.
- **Stdlib only.** No `pip install`, no `requirements.txt` for scripts. `subprocess`, `signal`, `pathlib`, `argparse`, `json`, `hashlib`, `re` cover the vast majority of shell-script territory portably.
- **Existing `.sh` scripts stay** until converted per the phased plan in issue #572 (bash → Python migration epic). When you make a substantive change to an existing bash script, prefer converting it to Python in the same PR over patching bash.
- **Tests follow the shipped script.** New pytest for new Python; existing bats stays until its target script converts.
- **Two-line install trampolines that must be shell** (e.g. `plugins/dev-team/install.sh`) are the sole exception — they exist to detect the shell environment before Python is guaranteed available.

Why Python: uniform behavior on macOS + Linux + Windows Git Bash + native Windows via one runtime. `python3` is already a hard dependency of every plugin hook — this consolidates on it rather than introducing anything new.

### Shell-script portability (legacy bash, until converted per #572)

These rules apply to **existing** `.sh` scripts until they convert to Python per the epic in #572. All existing bash must continue to run on **macOS, Linux, and Windows Git Bash**:

- **macOS** ships bash 3.2, so stay 3.2-safe: no `mapfile`/`readarray`, `declare -A`, `${var,,}`, or `wait -n`; expand possibly-empty arrays with the empty-safe idiom `${arr[@]+"${arr[@]}"}` (bare `"${arr[@]}"` under `set -u` aborts on 3.2).
- **macOS vs Linux command differences**: avoid Linux-only flags (`readlink -f`, `sed -i` semantics, `date +%N`, `stat -c`, `find -printf`, `timeout`) or guard them with a fallback (e.g. `recon-inventory.sh`'s `readlink -f || python3`, `_lib.sh`'s `date +%s%3N || python3`, `mutation-adapters/lib.sh`'s `timeout`→`gtimeout`→unbounded).
- **Windows = Git Bash.** Native `cmd.exe`/PowerShell are not targets for legacy bash; the plugin's hooks and helper scripts run under [Git Bash](https://git-scm.com/download/win) (the POSIX shell Claude Code uses for its Bash tool on Windows). Each plugin's `install.sh` detects Windows-without-Git-Bash and tells the user to install it; `scripts/dev-setup.sh` does the same for contributors. New Python scripts don't need this — they run under native Python on any OS.

### Hermetic bats fixtures

Every `.bats` file under `tests/` that runs state-mutating git commands (`init`, `commit`, `push`, `update-ref`, `checkout`, `branch`, `add`, `clone`, `merge`, `rebase`, `reset`, ...) **must** `load '../lib/hermetic'` and wire `hermetic_setup` + `hermetic_teardown` into its `setup()`/`teardown()` blocks. `tests/repo/hermetic_adoption_tests.bats` enforces this at CI time.

Rationale: git exports `GIT_DIR`/`GIT_INDEX_FILE`/`GIT_WORK_TREE`/`GIT_PREFIX`/`GIT_REFLOG_ACTION` into the pre-push hook's environment. Without scrubbing, fixture bats tests inherit those vars and their `git init`/`git commit`/`git push` operations target the parent worktree's gitdir instead of their tempdirs, silently rewriting `refs/heads/*` on the pushing repo. See [`.triage/pre-push-corrupts-local-branch-refs.md`](.triage/pre-push-corrupts-local-branch-refs.md) and issue #546.

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

**Every commit landed on `main` must be conventional.** This repo rebase-merges PRs (see [Working Rules](#working-rules) — squash and merge-commit are disabled because they synthesize unsigned commits that the branch ruleset rejects). Rebase-merge lands each PR commit on `main` verbatim, so **release-please reads every commit**, not just the PR title. Two consequences:

- Squash your work-in-progress locally (`git rebase -i`) before opening the PR so only conventional-prefixed commits land — noise commits like `fix typo` or `wip` will confuse the changelog. Prefix genuinely non-shipping commits inside a PR with `chore:` so release-please ignores them.
- If a release is silently missed (nothing conventional landed), recover with a follow-up commit carrying a `Release-As: X.Y.Z` footer.

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
