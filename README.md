# Agentic Dev Team

Two Claude Code plugins for engineering workflows. Install one or both.

- **`agentic-dev-team`** gives Claude Code a full persona-driven development team: an Orchestrator that routes tasks, specialist agents (engineer, QA, architect, reviewers…), skills that encode reusable knowledge, and the four-command feature workflow `/specs → /plan → /build → /pr`.
- **`agentic-security-assessment`** is the security companion. It adds a deterministic-first `/security-assessment` pipeline (SAST + LLM judgment + FP-reduction + exec report), a `/cross-repo-analysis` command for multi-repo attack chains, and an adversarial ML red-team harness (`/redteam-model`) for self-owned model endpoints.

The two plugins share a primitives contract (`codebase-recon`, `ACCEPTED-RISKS.md`, unified finding envelope) that lives in `agentic-dev-team`. Install that plugin first; add the security companion when you need it.

## Plugins

| Plugin | What it does | Key commands | Install |
| --- | --- | --- | --- |
| **agentic-dev-team** | Persona-driven development team, reviewer swarm, TDD-gated build loop | `/specs`, `/plan`, `/build`, `/pr`, `/code-review`, `/triage` | [plugins/agentic-dev-team/README.md](plugins/agentic-dev-team/README.md) |
| **agentic-security-assessment** | Tool-first security assessment + red-team pipeline | `/security-assessment`, `/cross-repo-analysis`, `/redteam-model`, `/export-pdf` | [plugins/agentic-security-assessment/README.md](plugins/agentic-security-assessment/README.md) |

**First time here?** Start with `agentic-dev-team`. Add `agentic-security-assessment` only when you run full `/security-assessment` pipelines against target repos.

## Getting Started

Install one or both plugins via the Claude Code plugin marketplace, or from a local clone for development. The marketplace at this repo's root publishes both plugins; install whichever you need.

### Prerequisites

Both plugins require [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated, plus `jq` for JSON parsing in hooks.

```bash
# macOS
brew install jq

# Linux
apt install jq    # or: yum install jq
```

`agentic-dev-team` additionally uses `gh` (GitHub CLI) for `/pr` and `/triage`. `agentic-security-assessment` requires Python ≥ 3.10 and a tier-1 static-analysis toolchain (`semgrep`, `gitleaks`, `trivy`, `hadolint`, `actionlint`). Per-plugin READMEs cover the full matrix:

- [`plugins/agentic-dev-team/README.md`](plugins/agentic-dev-team/README.md) — full prerequisites and optional-tool table
- [`plugins/agentic-security-assessment/README.md`](plugins/agentic-security-assessment/README.md) — tier-1 tool requirements

### Marketplace sources

`claude plugin marketplace add` accepts a generic git URL (or a local path), then `claude plugin install <name>@<marketplace-name>` pulls the plugin. Pick the form that matches where the marketplace lives:

| Source | Command |
| --- | --- |
| GitHub | `claude plugin marketplace add https://github.com/<owner>/<repo>` |
| Azure DevOps (HTTPS, uses your git credential helper) | `claude plugin marketplace add https://dev.azure.com/<org>/<project>/_git/<repo>` |
| Azure DevOps (PAT in URL — when no credential helper is configured) | `claude plugin marketplace add "https://<user>:<pat>@dev.azure.com/<org>/<project>/_git/<repo>"` |
| Local clone (any host) | `git clone <url> /path/to/clone && claude plugin marketplace add /path/to/clone` |

Notes:

- The Azure DevOps PAT needs **Code (Read)** scope. Don't paste the URL into chat or commit it.
- Behind a corporate proxy or if `git clone` over HTTPS fails non-interactively, prefer the local-clone form — it avoids Claude Code's clone path entirely.
- For other hosts (GitLab, Bitbucket, self-hosted Gitea), the same generic-URL pattern applies; auth follows your local git configuration.
- Full reference: [Claude Code plugin marketplaces docs](https://docs.anthropic.com/en/docs/claude-code/plugin-marketplaces).

### Install `agentic-dev-team`

Start here. Most users install only this plugin.

```bash
# From this marketplace (recommended)
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-dev-team@bfinster

# From a local clone (for plugin development)
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-dev-team
```

For Azure DevOps or another git host, swap the `marketplace add` URL per the [Marketplace sources](#marketplace-sources) table above; the install line stays the same.

Then verify the prerequisites:

```bash
./plugins/agentic-dev-team/install.sh
```

The verifier checks that `claude`, `jq`, and `gh` are available and authenticated.

### Install `agentic-security-assessment` (optional)

Add this plugin only if you want the `/security-assessment` pipeline. It depends on `agentic-dev-team`'s primitives contract, so install that one first.

```bash
# Plugin install (after agentic-dev-team is in place)
claude plugin install agentic-security-assessment@bfinster
# Or from a local clone:
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-security-assessment
```

Then install the tier-1 static-analysis tools:

```bash
# macOS — one command
./plugins/agentic-security-assessment/install-macos.sh           # tier-1 only
./plugins/agentic-security-assessment/install-macos.sh --all     # tier-1 + optional + PDF deps
./plugins/agentic-security-assessment/install-macos.sh --dry-run # preview without running

# Windows — PowerShell (requires Scoop)
.\plugins\agentic-security-assessment\install-windows.ps1
```

Verify the install:

```bash
./plugins/agentic-security-assessment/install.sh
```

This checks that the `agentic-dev-team` primitives contract is at `^1.0.0`, Python ≥ 3.10 is on PATH, and the tier-1 tools are reachable.

### First commands

In any Claude Code session inside an installed project:

```text
/specs   Specify a new feature (Intent + BDD + Architecture + Acceptance Criteria)
/plan    Turn an approved spec into a TDD step-plan
/build   Execute the approved plan with RED-GREEN-REFACTOR
/pr      Run quality gates and open a pull request
```

For a hands-on tutorial that walks through invoking individual agents and skills, see [GETTING-STARTED.md](GETTING-STARTED.md).

## Dev team workflow

Four commands drive feature development from idea to pull request:

```
/specs  →  /plan  →  /build  →  /pr
```

| Step | Command | What it does |
| --- | --- | --- |
| **1. Specify** | `/specs` | Produce Intent, BDD/Gherkin scenarios, Architecture notes, Acceptance Criteria. A consistency gate must pass before moving on. Skip for bug fixes, refactors, or trivial changes. |
| **2. Plan** | `/plan` | Create a TDD step-plan. Four plan-review personas (Acceptance Test, Design, UX, Strategic critics) challenge the plan before the human sees it. Human approves before any code is written. |
| **3. Build** | `/build` | Execute the approved plan. Each step follows RED-GREEN-REFACTOR with inline review checkpoints (spec-compliance first, then quality agents). Produces verification evidence. |
| **4. Ship** | `/pr` | Run quality gates (tests, typecheck, lint, code review) and open a pull request. |

Each step produces artifacts the next step consumes. Human review gates sit between transitions.

![Workflow: specs → plan → build → pr](plugins/agentic-dev-team/docs/diagrams/workflow-linear.svg)

For bug fixes or simple tasks, skip `/specs` and start at `/plan` — or go straight to implementation. The Orchestrator routes trivially when the full workflow isn't needed.

### Supporting commands

| Command | When to use |
| --- | --- |
| `/code-review` | Run review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations) |
| `/continue` | Resume an in-progress build or plan across sessions |
| `/browse` | Visual QA via Playwright |
| `/benchmark` | Runtime performance metrics (Core Web Vitals, resource sizes) against baselines |
| `/careful` / `/freeze` / `/guard` | Safety modes for production-critical sessions |
| `/triage` | Investigate a bug and file a GitHub issue with a TDD fix plan |

### Automated pre-commit review

Every `git commit` is automatically gated by `/code-review`. A `PreToolUse` hook detects commit attempts and blocks them until a passing review exists for the exact set of staged files.

**Flow**: attempt commit → hook blocks → Claude runs `/code-review` (auto-scopes to uncommitted changes) → if pass/warn, a `.review-passed` gate file is written → next commit attempt succeeds.

**Bypass**: `git commit --no-verify` skips the review gate.

### Orchestrator-driven three-phase workflow

For complex tasks, the Orchestrator manages the full lifecycle as **Research → Plan → Implement** with human gates between phases:

- **Research** produces a design document (`docs/specs/`) with problem statement, alternatives, and scope boundaries.
- **Plan** is critically reviewed by four plan-review personas running in parallel before the human sees it.
- **Implement** enforces strict TDD (RED-GREEN-REFACTOR hard gates), uses worktree isolation for parallel units, and runs a three-stage inline review — spec-compliance first ("does code match spec?"), then quality agents ("is code good?"), then browser verification for UI changes. Actionable issues auto-fix and re-review in a loop (up to 5 iterations); only issues requiring human judgment escalate. All agents provide verification evidence (fresh test output) before claiming completion.

![Three-Phase Workflow: Research → Plan → Implement](plugins/agentic-dev-team/docs/diagrams/workflow-three-phase.svg)

## Security assessment pipeline

`/security-assessment <path>` runs a six-phase pipeline against one or more target repos. Deterministic tools do the detection; LLM agents handle the judgment stages.

| Phase | Runs | Output |
| --- | --- | --- |
| **0. Recon** | `codebase-recon` agent | `memory/recon-<slug>.{json,md}` |
| **1. Tool-first detection** | semgrep, gitleaks, trivy, hadolint, actionlint, custom rulesets | unified findings stream |
| **1b. Judgment** | `security-review`, `business-logic-domain-review` agents | appended findings |
| **1c. Suppression** | `ACCEPTED-RISKS.md` gate (deterministic) | filtered stream + audit log |
| **2. FP-reduction** | 5-stage rubric (reachability, environment, controls, dedup, severity) | disposition register |
| **2b. Severity floors** | deterministic domain-class calibration | floor-adjusted scores |
| **3. Narrative + compliance** | `tool-finding-narrative-annotator`, compliance-mapping skill | 4-domain narrative + compliance JSON |
| **4. Cross-repo** | service-comm parser, shared-cred hash match (multi-target only) | mermaid diagram + SARIF |
| **5. Exec report** | `exec-report-generator` agent | publication-ready 7-section markdown |

**Zero-install flow**: `scripts/run-assessment-local.sh` runs the same pipeline from the repo checkout without installing the plugin. Auto-detects the `claude` CLI; degrades to deterministic-only when absent. See [docs/user-guide-security-assessment.md](plugins/agentic-security-assessment/docs/user-guide-security-assessment.md) for the full runbook.

**Adversarial ML red-team**: `/redteam-model` probes a self-owned model endpoint (localhost / RFC1918 by default; public targets require a signed `authorization.md`). Eight probes covering recon, evasion, extraction, and report synthesis.

## What's included

| | agentic-dev-team | agentic-security-assessment |
| --- | --- | --- |
| Team agents | 12 (orchestrator, engineer, QA, architect, PM, …) | — |
| Review agents | 19 (security, domain, test, naming, …) | — |
| Security / red-team agents | — | 10 (fp-reduction, narrative annotator, red-team analyzers, exec-report-generator, …) |
| Skills | 31 | 3 (false-positive-reduction, compliance-mapping, security-assessment-pipeline) |
| Slash commands | 56 | 4 |
| Subagent prompt templates | 8 | — |
| Language templates | 9 | — |

Full catalogs:

- [Agents](plugins/agentic-dev-team/docs/agent_info.md) — team + review agent rosters, persona template, how to add/remove/customize
- [Skills & Commands](plugins/agentic-dev-team/docs/skills.md) — skills catalog (by category), slash-commands catalog, how to add new ones

## Repository structure

```text
.claude-plugin/marketplace.json         # Marketplace catalog (points at both plugins)

plugins/agentic-dev-team/                # Dev-team plugin source
├── README.md                            # Install + prerequisites
├── .claude-plugin/plugin.json           # Plugin manifest + version
├── agents/                              # Team agents (12) + review agents (19)
├── commands/                            # Slash commands
├── skills/                              # Reusable knowledge modules (31 skills)
├── hooks/                               # PreToolUse guards + PostToolUse advisory hooks
├── knowledge/                           # Progressive disclosure reference files
├── templates/                           # Language-specific agent templates
├── docs/                                # Plugin docs (architecture, agents, skills, eval system)
├── settings.json                        # Hook registrations
├── install.sh                           # Prerequisite check
└── CLAUDE.md                            # Orchestration pipeline config (auto-loaded)

plugins/agentic-security-assessment/         # Security companion plugin
├── README.md                            # Install + prerequisites
├── install-macos.sh                     # One-command tool installer (macOS)
├── install.sh                           # Prerequisite verifier
├── agents/ commands/ skills/ harness/   # Assessment + red-team pipeline
├── docs/                                # Plugin docs (user guide, comparative testing)
└── CLAUDE.md                            # Pipeline config (auto-loaded)

docs/                                    # Cross-plugin dev documentation (roadmaps, spikes, repo-level specs)
plans/                                   # Implementation plans (not shipped)
evals/                                   # Agent eval fixtures + comparative harness
scripts/                                 # Zero-install assessment runner + helpers
```

---

## Local development

### Testing locally

Install either plugin from the local path into a test project:

```bash
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-dev-team
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-security-assessment
```

### Testing agents and hooks (dev-team plugin)

```
/agent-eval                                                # full eval suite
/agent-eval plugins/agentic-dev-team/agents/naming-review.md   # one agent
/agent-audit                                               # structural compliance
```

### Comparative-testing harness (security plugin)

Regression-test the `/security-assessment` pipeline against a seeded fixture + reference baseline:

```bash
python3 evals/comparative/score.py \
  --reference evals/comparative/reference-baseline/2026-04-21 \
  --ours memory
```

See [docs/comparative-testing.md](plugins/agentic-security-assessment/docs/comparative-testing.md) for the scoring methodology.

### Hook paths

Hooks are registered in each plugin's `settings.json` and ship with that plugin. Local development runs them from `plugins/<plugin-name>/hooks/`.

### Adding an agent or skill

```
/agent-add <description or URL to a coding standard>
```

This scaffolds the agent file, adds it to the registry in the owning plugin's `CLAUDE.md`, and creates eval fixtures. Run `/agent-audit` and `/agent-eval` to verify compliance.

### Documentation

| Guide | Description |
| --- | --- |
| [Tutorial: Invoking Agents](GETTING-STARTED.md) | Hands-on tutorial: invoke agents, skills, and common workflows (the [Getting Started](#getting-started) section above covers install) |
| [Architecture](plugins/agentic-dev-team/docs/agent-architecture.md) | Context management, quality assurance, governance, multi-LLM routing |
| [Agents](plugins/agentic-dev-team/docs/agent_info.md) | Agent roster, persona template, adding/removing/customizing |
| [Skills & Commands](plugins/agentic-dev-team/docs/skills.md) | Skills catalog, slash-commands catalog |
| [Eval System](plugins/agentic-dev-team/docs/eval-system.md) | How review-agent accuracy is measured and graded |
| [Security Assessment User Guide](plugins/agentic-security-assessment/docs/user-guide-security-assessment.md) | Path-A (plugin) vs. Path-B (zero-install) runbook, tool install matrix |
| [Comparative Testing](plugins/agentic-security-assessment/docs/comparative-testing.md) | Fixture repo, ground truth, scoring methodology |
