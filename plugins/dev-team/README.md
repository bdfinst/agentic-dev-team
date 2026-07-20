# dev-team

A Claude Code plugin that adds a full persona-driven AI development team to any project. The Orchestrator routes tasks to specialized agents, inline review checkpoints catch quality issues during implementation, and skills provide reusable knowledge modules that any agent can draw on.

For the workflow overview, team philosophy, and three-phase (Research → Plan → Implement) process, see the [repository README](../../README.md).

## Install

Three commands total: register the marketplace, install the plugin, then run `/setup` in your project. That's the whole flow.

**Prerequisite:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code), installed and authenticated. Nothing else needs to be installed by hand — `/setup` installs the tools your stack needs.

### Install

Register the marketplace, then install the plugin. The marketplace is named **`bfinster`** (the `name` field in `marketplace.json`); the plugin is **`dev-team`**. `claude plugin marketplace add` accepts a GitHub `owner/repo`, any git URL, or a local path; `claude plugin install` takes `<plugin>@<marketplace>`.

**From GitHub (recommended):**

```bash
claude plugin marketplace add bdfinst/agentic-dev-team
claude plugin install dev-team@bfinster
```

The `owner/repo` shorthand and the full `https://github.com/bdfinst/agentic-dev-team` URL are equivalent.

### Set up your project

Open Claude Code in your project and run one command:

```
/setup
```

`/setup` detects your stack, shows you a plan, and — once you confirm it — installs everything the team needs and writes project config. You do not pre-install anything:

- **Tool dependencies** — `jq` and `python3` (used by the hooks and gates), and for a recognized stack, the stack's linters, formatters, type checkers, test runner, and per-language mutation testing (Stryker for JS/TS, pitest for Java/Kotlin, Stryker.NET for C#).
- **Capability tools, each installed only when its signal fires** — `gh` when the repo has a GitHub remote (used by `/pr` and `/issues-from-plan`), `semgrep` for static analysis, Playwright + Chromium for `/browse`, the docker scanners (`hadolint`/`trivy`/`grype`) when a Dockerfile is present, and ADR tooling when the repo already keeps ADRs.
- **Optional code-intelligence indexes** — CodeGraph, Repowise, and Graphify, offered as keyless opt-ins for faster code navigation.
- **Project config** — a project-level `CLAUDE.md`, the auto-format PostToolUse hook, language-specific agent templates, a generated `/pr` command, and `.gitignore` entries for the workflow's runtime artifacts.

Recognized stacks are **JS/TS, Python, C#, and Java**. On a stack that isn't recognized, `/setup` installs the language-neutral pieces and tells you plainly what it could not set up — it never guesses at a toolchain.

For an unattended run (CI, scripted onboarding), pass `--yes` to accept the detected plan without the confirmation prompt: `/setup --yes`. Add `--dry-run` to report what it would install and configure without writing anything.

After `/setup`, you're ready to work: run `/specs` to start a feature, or just describe a task and let the Orchestrator route it. To confirm the team is live, see [Verify](#verify).

<details>
<summary><b>Manual / offline install of individual tools</b></summary>

`/setup` installs all of these for you. This section is a reference for air-gapped machines, an unsupported stack, or installing a single tool by hand.

**Hard dependencies** (any stack): `jq` (`brew install jq` / `apt install jq`) and `python3`.

**GitHub CLI** — `gh`, used by `/pr` and `/issues-from-plan`. `brew install gh` (macOS) or [GitHub CLI install docs](https://github.com/cli/cli#installation), then `gh auth login`.

**By feature:**

| Tool(s) | Required for | Install |
| --- | --- | --- |
| `semgrep` | `/semgrep-analyze`, static analysis pre-pass in `/code-review` | `pip install semgrep`, `brew install semgrep`, or `pipx install semgrep` |
| `playwright` | `/browse` (browser-based QA) | `npx playwright install chromium` (requires Node.js) |
| `hadolint`, `trivy`, `grype` | `/docker-image-audit` | `brew install hadolint trivy grype`; Linux install scripts and Docker-container usage in the [docker-image-audit skill docs](skills/docker-image-audit/SKILL.md) |
| `az` (with `az boards` extension) | `/test-modernize` when the parent issue lives on Azure DevOps | `brew install azure-cli` or [Azure CLI install docs](https://learn.microsoft.com/cli/azure/install-azure-cli); then `az extension add --name azure-devops` and `az login` |
| `glab` | `/test-modernize` when the parent issue lives on GitLab | `brew install glab` or [GitLab CLI install docs](https://gitlab.com/gitlab-org/cli#installation); then `glab auth login` |
| `acli` | `/test-modernize` when the parent issue lives on Jira (Atlassian Cloud) | See [Atlassian CLI install docs](https://developer.atlassian.com/cloud/acli/); REST + `JIRA_TOKEN` is the fallback |

`/test-modernize` falls back to local plan files under `./plans/test-modernize/` whenever the tracker CLI for the given parent URL is missing — the workflow continues uninterrupted, only the destination of the issues changes.

**Auto-formatting (the `post-format` hook, detected per language):** the hook auto-formats files on every edit, detecting available formatters and degrading silently if none are installed.

| Tool | Language | Install |
| --- | --- | --- |
| `prettier` | JS/TS/CSS/HTML/JSON | `npm install -D prettier` (project-local) |
| `eslint` | JS/TS | `npm install -D eslint` (project-local) |
| `ruff` | Python | `pip install ruff` or `brew install ruff` |
| `black` | Python (fallback if ruff absent) | `pip install black` |
| `gofmt` | Go | Included with Go toolchain |
| `rustfmt` | Rust | `rustup component add rustfmt` |
| `rubocop` | Ruby | `gem install rubocop` (or add to Gemfile) |
| `google-java-format` | Java | `brew install google-java-format` or [GitHub releases](https://github.com/google/google-java-format/releases) |
| `ktlint` | Kotlin | `brew install ktlint` or [GitHub releases](https://github.com/pinterest/ktlint/releases) |
| `dotnet format` | C# | Included with .NET SDK 6+ |

**Quality gates in `/pr` (detected per stack):** `/pr` auto-detects test runners, type checkers, and linters from project manifests — if the tool is installed and the project has the relevant config file, it runs automatically.

| Tool | Detected via | Install |
| --- | --- | --- |
| `tsc` | `tsconfig.json` | `npm install -D typescript` (project-local) |
| `mypy` | `mypy.ini` or `pyproject.toml` [mypy] | `pip install mypy` |
| `ruff` | `which ruff` | `pip install ruff` (project venv / dev requirements) |
| `golangci-lint` | `which golangci-lint` | `brew install golangci-lint` or [install docs](https://golangci-lint.run/welcome/install/) |

</details>

### Self-hosted / other git hosts

For a self-hosted or other git host (GitLab, Bitbucket, Gitea, Azure DevOps, on-prem), end the URL with `.git` so Claude Code clones the repository instead of treating the URL as a direct link to a `marketplace.json`, and append `#<branch-or-tag>` to pin a ref. The repository must contain `.claude-plugin/marketplace.json` at its root.

```bash
# HTTPS (private repos use your git credential helper)
claude plugin marketplace add https://gitlab.example.com/team/agentic-dev-team.git

# SSH
claude plugin marketplace add git@gitlab.example.com:team/agentic-dev-team.git

# pin a release tag
claude plugin marketplace add https://gitlab.example.com/team/agentic-dev-team.git#dev-team-v6.6.0

# then, for any of the above:
claude plugin install dev-team@bfinster
```

For a private host that needs a token, embed a **read-scoped** token in the URL — `https://<user>:<token>@host/team/agentic-dev-team.git` — but never commit it or paste it in chat (Azure DevOps PATs need **Code (Read)** scope). Behind a corporate proxy, clone first and add the local path: `git clone <url> /path/to/clone && claude plugin marketplace add /path/to/clone`.

**Scope and monorepo options** — these flags apply to `marketplace add` and `install`:

| Flag | Effect |
| --- | --- |
| `--scope user` | You, across all projects (**default**) |
| `--scope project` | All collaborators in this repo (writes `.claude/settings.json`) |
| `--scope local` | You, this repo only (writes `.claude/settings.local.json`) |
| `--sparse .claude-plugin plugins` | Limit the marketplace checkout to these directories — for monorepos; `marketplace add` only |

Full reference: [Claude Code plugin marketplaces docs](https://docs.anthropic.com/en/docs/claude-code/plugin-marketplaces).

### Upgrading

Run `/upgrade` from any session, or update manually:

```bash
claude plugin update --scope <scope> dev-team@bfinster
```

To re-point the marketplace (e.g., after moving git hosts), remove it by its **marketplace name** (`bfinster`) and re-add the source:

```bash
claude plugin marketplace remove bfinster
claude plugin marketplace add bdfinst/agentic-dev-team
```

### Verify

After `/setup` completes, confirm the system is working:

```
> What agents are available on this team?
```

## What's included

- **11 team agents** — Orchestrator, Software Engineer, QA Engineer, Architect, Product Manager, etc.
- **28 review agents** — security-review, domain-review, test-review, naming-review, …
- **93 skills** — knowledge modules and procedures the team draws on, 89 of them user-invocable as slash commands (`/plan`, `/build`, `/pr`, `/code-review`, `/browse`, `/triage`, …)

Full catalogs: [Agents](docs/agent_info.md) · [Skills](docs/skills.md) · [Workflows](docs/workflows.md)
