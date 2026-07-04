# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## Working Rules

- **Always work on a branch.** Never commit directly to `main`. Every change — including documentation-only changes, gitignore tweaks, and one-line fixes — lands via a feature branch and a pull request. If a commit accidentally lands on `main` locally, reset `main` to `origin/main` and move the commit to a branch before pushing. Release commits authored by release-please are the only exception; they arrive as their own PR.
- **Rebase-only merges.** `main` is protected by a ruleset that requires **signed commits** and forbids force-pushes. GitHub's squash/merge-commit strategies synthesize new commits with no signature and are blocked by the ruleset; **rebase merge is the only strategy that lands PRs**. Configure your local git to sign commits (`git config --global commit.gpgsign true` plus a key) so every commit you push is `G`-verified — see `git log --pretty="%h %G? %s"` to check.
- **Documentation-only PRs auto-merge.** When the diff touches only `*.md` files (plus `.gitignore`, `LICENSE`, or other non-shipping metadata) and changes no code, agent, skill, or hook, arm auto-merge at PR-open time: `gh pr merge <num> --auto --rebase`. Required checks still run; the PR lands the moment they pass. Any PR that touches code, agents, skills, hooks, eval fixtures, or marketplace manifests requires explicit human merge.
- **Prefer Python over bash, repo-wide, unless bash is strictly required.** This applies everywhere in the repo, not just shipped plugin code — new tests under `tests/`, new `scripts/*`, new CI helpers. Write `.py` (stdlib-only for anything under `plugins/dev-team/`) by default. Bash is acceptable only when the thing under test genuinely is a shell script, or for the unavoidable pre-Python bootstrap shim (`install.sh`'s two-line trampoline). New `.bats` files are a review finding, not a style choice — see [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md), [ADR 0015](docs/adr/0015-bash-removal-complete.md), and epic #668 (retiring the ~130 legacy `tests/**/*.bats` content-guard fixtures in favor of pytest). If you find yourself adding a `.bats` file, port the assertions to `test_*.py` instead — see `### Script authoring — Python only` below for the mechanical pattern.

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

- CLI: `shellcheck`, `jq`, `python3` (macOS: `brew install shellcheck jq python3`). `shellcheck` still lints repo-root shell (`scripts/audit-rules-vs-prompts.sh`, etc.) and the `plugins/security-assessment/` plugin; the `plugins/dev-team/` plugin itself is now Python.
- Python modules: install the declared dev dependencies once with `python3 -m pip install -r requirements-dev.txt` (PyYAML for a few content-guard tests that shell out to Python; pytest for every content-guard suite and the plugin's own unit tests; semgrep for the security-assessment suites; httpx for the red-team harness smoke test).

**One-shot setup:** `bash scripts/dev-setup.sh` validates this toolchain and installs anything missing (Homebrew on macOS, apt-get on Debian/Ubuntu, then the `requirements-dev.txt` deps). Safe to re-run.

`ci-local.sh` checks these up front and exits with an actionable message (pointing at `dev-setup.sh`) if any are missing.

### Known limitation — local Husky hooks don't run in unprovisioned worktrees

`core.hooksPath` is set to `.husky/_` (generated by `npm install`'s `prepare: "husky"` script — see `git ls-files .husky/`, which never includes `_`). That path is stored in the shared bare repo's config and resolved *relative to each worktree's own top level*, not shared across worktrees via `extensions.worktreeConfig`. A worktree where `npm install` was never run has neither `.husky/_` nor `node_modules`, so `git commit` silently runs **no hook at all** — no error, no warning — instead of the tracked `.husky/pre-commit` (knowledge-index rebuild + `lint-staged`).

This affects ephemeral worktrees created by the Claude Code harness itself (the `EnterWorktree` tool backing `/build`'s per-slice `isolation: "worktree"` fan-out) and by `scripts/run-full-eval-parallel.sh`'s per-batch `git worktree add`. Neither provisions `.husky/_`/`node_modules` after creation, and the harness-owned path is outside this repo's control to fix.

**Disposition: documented known limitation, not fixed** (investigated under issue #717; the relative-`hooksPath` question itself was already deferred by [issue #546's spec](docs/specs/pre-push-hook-hermetic-fixtures.md#ambiguity-log) as "leave as-is"). CI is the enforcement backstop for the consequential half of what the hook does: `tests/repo/test_knowledge_index_current.py` runs in CI (`chk_hook_units`, `.github/workflows/plugin-tests.yml`) and fails the PR if the knowledge index drifts from source — so a commit that skipped the local rebuild still can't merge with a stale index. The other half, `lint-staged`'s `eslint --fix`, has no equivalent CI gate today (`chk_eslint` in `scripts/ci-local.sh` is never invoked by any workflow) — a pre-existing gap orthogonal to worktree provisioning, since it would be skipped in CI-only PR runs regardless of local hook state.

If you're committing inside a worktree and want local hook enforcement, run `npm install` in that worktree first (populates `.husky/_` and `node_modules`); otherwise rely on `scripts/ci-local.sh` / CI to catch what the skipped hook would have.

### Script authoring — Python only

**Every shipped script under `plugins/dev-team/` is Python 3.8+ using stdlib only.** See [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md) (the decision) and [ADR 0015](docs/adr/0015-bash-removal-complete.md) (the completion — bash removal via epic #572). Concretely:

- **All shipped hooks + scripts are `.py` files.** No `.sh` remains in `plugins/dev-team/` except the `install.sh` trampoline (two-line shell → Python bootstrap so we can detect the shell environment before Python is guaranteed on PATH).
- **Stdlib only.** No `pip install`, no `requirements.txt` for shipped code. `subprocess`, `signal`, `pathlib`, `argparse`, `json`, `hashlib`, `re` cover the vast majority of shell-script territory portably.
- **Cross-OS by default.** Python runs natively on macOS, Linux, and Windows — no more Git Bash requirement for plugin hooks. When probing OS-specific paths (DOTNET_ROOT, tool install locations), use runtime probes (`subprocess`, `pathlib`) rather than hard-coding macOS or Linux paths.
- **Tests are pytest.** New tests land as `test_*.py` under the plugin's `tests/` tree.

Repo-root `scripts/*.sh` (`ci-local.sh`, `dev-setup.sh`, `cost-regression-check.sh`, the various `assemble-docs.sh`/`eval-changed.sh`/`run-full-eval.sh` helpers) are OUT of this rule's scope — they orchestrate developer tooling around the plugin, not the plugin itself, and are not shipped downstream. Convert them opportunistically when you touch them.

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
- **Hook**: Add a `.py` file to `plugins/dev-team/hooks/` and register it in `plugins/dev-team/settings.json`

After changes, run `/agent-audit` to verify structural compliance.

[`plugins/dev-team/docs/developer-notes.md`](plugins/dev-team/docs/developer-notes.md) is the maintainer-facing entry point: an index of the plugin-development docs plus the playbook for adding a new static-analysis language.

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
plugin also installs this repo's gates (`jq`, `shellcheck`, the Python
dev deps, and `gh`) — one paste into the *Setup script* field covers both. There
is no dedicated secrets store yet — treat env vars as visible to anyone who can
edit the environment.

For the full walkthrough of running a plugin's skills from a web session (the
Setup-script install plus the file-based fallback), see
[`docs/cloud-setup.md`](docs/cloud-setup.md) and
[`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md).

See `plugins/dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
