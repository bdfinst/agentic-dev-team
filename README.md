# Agentic Dev Team

A Claude Code plugin that adds a full persona-driven AI development team to any project. The Orchestrator routes tasks to specialized agents, inline review checkpoints catch quality issues during implementation, and skills provide reusable knowledge modules that any agent can draw on.

## Workflow

Four commands drive feature development from idea to pull request:

```
/specs  →  /plan  →  /build  →  /pr
```

| Step | Command | What it does |
| --- | --- | --- |
| **1. Specify** | `/specs` | Collaborate on four artifacts: Intent, BDD/Gherkin scenarios, Architecture notes, Acceptance Criteria. A consistency gate must pass before moving on. Skip for bug fixes, refactors, or trivial changes. |
| **2. Plan** | `/plan` | Create a step-by-step TDD implementation plan. Four plan review personas (Acceptance Test, Design, UX, Strategic critics) challenge the plan before the human sees it. Human approves before any code is written. |
| **3. Build** | `/build` | Execute the approved plan. Each step follows RED-GREEN-REFACTOR with inline review checkpoints (spec-compliance first, then quality agents). Produces verification evidence. |
| **4. Ship** | `/pr` | Run quality gates (tests, typecheck, lint, code review) and create a pull request. |

Each step produces artifacts the next step consumes. Human review gates sit between each transition.

```mermaid
flowchart LR
    S["/specs\n4 artifacts"] -->|consistency gate| P["/plan\nTDD steps"]
    P -->|human approval| B["/build\nRED-GREEN-REFACTOR"]
    B -->|code review| PR["/pr\nquality gates"]
```

For bug fixes or simple tasks, skip `/specs` and start at `/plan` or go straight to implementation. The orchestrator routes trivially when the full workflow isn't needed.

### Supporting commands

| Command | When to use |
| --- | --- |
| `/code-review` | Run all review agents, auto-fix actionable issues, and re-run until clean (up to 5 iterations) |
| `/continue` | Resume an in-progress build or plan across sessions |
| `/browse` | Visual QA via Playwright |
| `/benchmark` | Runtime performance metrics (Core Web Vitals, resource sizes) against baselines |
| `/careful` / `/freeze` / `/guard` | Safety modes for production-critical sessions |

### Automated pre-commit review

Every `git commit` is automatically gated by `/code-review`. A `PreToolUse` hook detects commit attempts and blocks them until a passing review exists for the exact set of staged files.

**Flow**: attempt commit → hook blocks → Claude runs `/code-review` (auto-scopes to uncommitted changes) → if pass/warn, a `.review-passed` gate file is written → next commit attempt succeeds.

**Bypass**: `git commit --no-verify` skips the review gate.

## How It Works

**Team agents** define roles (persona, behavior, collaboration). **Review agents** check work quality in real time. **Skills** define knowledge (patterns, guidelines, procedures). **Slash commands** invoke agents and skills directly. The **Orchestrator** controls task routing, model selection, and the inline review feedback loop.

### Three-Phase Workflow (Orchestrator-Driven)

For complex tasks where the orchestrator manages the full lifecycle, every non-trivial task follows **Research → Plan → Implement** with human review gates between phases:

- **Research** produces a **design document** (`docs/specs/`) with problem statement, alternatives, and scope boundaries
- **Plan** is critically reviewed by **four plan review personas** (Acceptance Test, Design & Architecture, UX, and Strategic critics) running in parallel before the human sees it
- **Implement** enforces strict **TDD** (RED-GREEN-REFACTOR with hard gates), uses **worktree isolation** for parallel units, and runs a **three-stage inline review**: spec-compliance first ("does code match spec?"), then quality agents ("is code good?"), then browser verification for UI changes. Actionable issues (error/warning severity with high/medium confidence) are **auto-fixed and re-reviewed** in a loop (up to 5 iterations) — only issues requiring human judgment are escalated. All agents must provide **verification evidence** (fresh test output) before claiming completion. After the human gate, a **branch workflow** handles PR creation and merge strategy.

```mermaid
flowchart TD
    U([User Request]) --> O[Orchestrator]

    subgraph "Phase 1 — Research"
        O --> SP["/specs\nIntent · BDD · Architecture · Criteria"]
        SP --> DD["Design Doc\ndocs/specs/"]
    end

    DD --> HG1([Human Gate — approve spec + design])

    subgraph "Phase 2 — Plan"
        HG1 --> PL["/plan\nTDD steps · complexity tiers · acceptance criteria"]
        PL --> PRV["Plan Review Personas\n4 critics in parallel"]
        PRV --> ATC["Acceptance Test Critic\ncriteria · scenarios · error paths"]
        PRV --> DAC["Design & Architecture Critic\ncoupling · abstractions · patterns"]
        PRV --> UXC["UX Critic\njourney · a11y · cognitive load"]
        PRV --> STC["Strategic Critic\nscope · risk · opportunity cost"]
        ATC --> AGG["Aggregate Findings\nfix blockers · collect warnings"]
        DAC --> AGG
        UXC --> AGG
        STC --> AGG
    end

    AGG --> HG2([Human Gate — approve plan + review summary])

    subgraph "Phase 3 — Implement (/build)"
        HG2 --> CV["Verify criteria testability\n(sprint contract gate)"]
        CV --> NEXT{"Next step?"}
        NEXT -->|more steps| IM["TDD Loop\nRED → GREEN → REFACTOR"]

        subgraph "Per-Step Inline Review"
            IM --> CX{"Complexity?"}
            CX -->|trivial| NEXT
            CX -->|standard / complex| SC["Stage 1: Spec Compliance\n/review-agent spec-compliance"]
            SC -->|fail| IM
            SC -->|pass| QR["Stage 2: Quality Agents\n/review-agent per change type"]
            QR -->|"fail → auto-fix (max 5×)"| IM
            QR -->|pass| BV{"UI change?"}
            BV -->|yes| BR["Stage 3: Browser Verify\n/browse smoke test"]
            BV -->|no| NEXT
            BR --> NEXT
        end

        NEXT -->|all done| CR["/code-review\nauto-scope · fix loop · up to 5×"]
    end

    CR --> HG3([Human Gate — approve implementation])
    HG3 --> PRR["/pr\nQuality gate · create pull request"]
    PRR --> LL["Learning Loop\nMetrics · /harness-audit"]
    LL --> O
```

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

All three also run as Docker containers if you prefer not to install locally — see the [docker-image-audit skill docs](plugins/agentic-dev-team/skills/docker-image-audit/SKILL.md) for details.

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

## What's Included

The plugin ships with **12 team agents**, **19 review agents**, **31 skills**, **8 subagent prompt templates**, and **56 slash commands**. For the full catalogs:

- [Agents](docs/agent_info.md) — team agent roster, review agent roster, persona template, how to add/remove/customize
- [Skills & Commands](docs/skills.md) — skills catalog (by category), slash commands catalog, how to add new ones

## Repository Structure

```text
.claude-plugin/marketplace.json     # Marketplace catalog
plugins/agentic-dev-team/           # Plugin source (ships to users)
├── .claude-plugin/plugin.json      # Plugin manifest + version
├── agents/                         # Team agents (12) + review agents (19)
├── commands/                       # Slash commands
├── skills/                         # Reusable knowledge modules (31 skills)
├── hooks/                          # PreToolUse guards + PostToolUse advisory hooks
├── knowledge/                      # Progressive disclosure reference files
├── templates/                      # Language-specific agent templates
├── settings.json                   # Hook registrations
├── install.sh                      # Prerequisite check
└── CLAUDE.md                       # Orchestration pipeline config (auto-loaded)

docs/                               # Dev documentation (not shipped)
plans/                              # Implementation plans (not shipped)
evals/                              # Agent eval fixtures (not shipped)
reports/                            # Review reports (not shipped)
```

---

## Local Development

### Testing locally

Install the plugin from the local path into a test project:

```bash
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-dev-team
```

### Testing agents and hooks

**Eval suite** — run against a single agent or the full set:

```
/agent-eval
/agent-eval plugins/agentic-dev-team/agents/naming-review.md
```

**Structural compliance** — verify all agents and commands:

```
/agent-audit
```

### Hook paths

Hooks are registered in `plugins/agentic-dev-team/settings.json` and ship with the plugin. When developing locally, hooks run from `plugins/agentic-dev-team/hooks/`.

### Adding an agent or skill

```
/agent-add <description or URL to a coding standard>
```

This scaffolds the agent file, adds it to the registry in `CLAUDE.md`, and creates eval fixtures. Run `/agent-audit` and `/agent-eval` to verify compliance.

### Documentation

| Guide | Description |
| --- | --- |
| [Getting Started](GETTING-STARTED.md) | Hands-on tutorial: invoke agents, skills, and common workflows |
| [Architecture](docs/architecture.md) | Context management, quality assurance, governance, multi-LLM routing |
| [Agents](docs/agent_info.md) | Agent roster, persona template, adding/removing/customizing agents |
| [Skills & Commands](docs/skills.md) | Skills catalog, slash commands catalog |
| [Eval System](docs/eval-system.md) | How review agent accuracy is measured and graded |
