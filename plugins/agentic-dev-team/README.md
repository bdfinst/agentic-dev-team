# agentic-dev-team

A Claude Code plugin that adds a full persona-driven AI development team to any project. The Orchestrator routes tasks to specialized agents, inline review checkpoints catch quality issues during implementation, and skills provide reusable knowledge modules that any agent can draw on.

For the workflow overview, team philosophy, and three-phase (Research → Plan → Implement) process, see the [repository README](../../README.md).

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- `jq` — used by hooks for JSON parsing
  - macOS: `brew install jq`
  - Linux: `apt install jq` or `yum install jq`
- `gh` — [GitHub CLI](https://cli.github.com/), used by `/pr` and `/triage` for creating PRs and issues
  - macOS: `brew install gh`
  - Linux: see [GitHub CLI install docs](https://github.com/cli/cli#installation)
  - Then authenticate: `gh auth login`

**Optional — by feature:**

| Tool(s) | Required for | Install |
| --- | --- | --- |
| `semgrep` | `/semgrep-analyze`, static analysis pre-pass in `/code-review` | See below |
| `playwright` | `/browse` (browser-based QA) | See below |
| `hadolint`, `trivy`, `grype` | `/docker-image-audit` | See below |

**Optional — auto-formatting (detected per language):**

The `post-format` hook auto-formats files on every edit. It detects available formatters and degrades silently if none are installed. Install the ones relevant to your stack:

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

**Optional — quality gates in `/pr` (detected per stack):**

`/pr` auto-detects test runners, type checkers, and linters based on project manifests. No configuration needed — if the tool is installed and the project has the relevant config file, it runs automatically.

| Tool | Detected via | Install |
| --- | --- | --- |
| `tsc` | `tsconfig.json` | `npm install -D typescript` (project-local) |
| `mypy` | `mypy.ini` or `pyproject.toml` [mypy] | `pip install mypy` |
| `pylint` | `which pylint` | `pip install pylint` |
| `golangci-lint` | `which golangci-lint` | `brew install golangci-lint` or [install docs](https://golangci-lint.run/welcome/install/) |

---

#### Installing semgrep

```bash
pip install semgrep
# or: brew install semgrep
# or: pipx install semgrep
```

#### Installing Playwright

```bash
npx playwright install chromium
```

Requires Node.js. Used by `/browse` for browser-based visual QA.

#### Installing hadolint, trivy, grype

```bash
# macOS (Homebrew)
brew install hadolint trivy grype

# Linux
# hadolint
curl -sL -o /usr/local/bin/hadolint \
  "https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64"
chmod +x /usr/local/bin/hadolint

# trivy
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
```

All three also run as Docker containers if you prefer not to install locally — see the [docker-image-audit skill docs](skills/docker-image-audit/SKILL.md) for details.

### Plugin install (recommended)

Add the marketplace source, then install the plugin. The marketplace resolves the plugin location automatically from `marketplace.json`.

**From GitHub:**

```bash
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-dev-team@bfinster
```

**From a local clone:**

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install agentic-dev-team@bfinster
```

By default the marketplace is registered at user scope (available in all projects). To scope it to a single project:

```bash
claude plugin marketplace add --scope project https://github.com/bdfinst/agentic-dev-team
claude plugin install --scope project agentic-dev-team@bfinster
```

### Upgrading from a previous install

If you previously installed the plugin before the directory restructure (pre-v2.1), remove and re-add the marketplace source:

```bash
claude plugin marketplace remove agentic-dev-team
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-dev-team@bfinster
```

### Verify

After starting Claude Code, confirm the system is working:

```
> What agents are available on this team?
```

## What's included

- **12 team agents** — Orchestrator, Software Engineer, QA Engineer, Architect, Product Manager, etc.
- **19 review agents** — security-review, domain-review, test-review, naming-review, …
- **31 skills** — TDD, design-doc, competitive-analysis, domain-analysis, …
- **56 slash commands** — `/plan`, `/build`, `/pr`, `/code-review`, `/browse`, `/triage`, …

Full catalogs: [Agents](../../docs/agent_info.md) · [Skills & Commands](../../docs/skills.md)
