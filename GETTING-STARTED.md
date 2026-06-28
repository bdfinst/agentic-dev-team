# Getting Started with the Agentic Dev Team

This project gives you an AI development team — specialized agents with distinct roles, reusable skills they draw on, and slash commands for skills and workflows. You talk to the team in natural language. The system figures out who should do the work and what knowledge they need.

## Installation

### Install `dev-team`

Start here — most users install only this plugin. Required tools (`jq`, `gh`) are listed in the [Plugins](README.md#plugins) table.

```bash
claude plugin marketplace add bdfinst/agentic-dev-team
claude plugin install dev-team@bfinster
```

The `owner/repo` shorthand and the full `https://github.com/bdfinst/agentic-dev-team` URL are equivalent. For self-hosted or other git hosts, install scopes (`user`/`project`/`local`), and the upgrade/re-point commands, see the [plugin install guide](plugins/dev-team/README.md#install).

Then, in your project, install tool dependencies and generate config:

```text
/init-dev-team
/setup
```

- **`/init-dev-team`** installs the plugin's tool dependencies — `jq`, `python3`, and language-specific mutation tooling (Stryker, pitest, Stryker.NET) — plus an optional CodeGraph index for code intelligence.
- **`/setup`** detects your stack and generates project-level config and hooks, including the automated pre-commit review gate.

After `/setup`, run `/specs` to start a feature, or ask a question and let the Orchestrator route it.

### Install `security-assessment` (optional)

Add this plugin only if you want the `/security-assessment` pipeline. Install `dev-team` first.

```bash
claude plugin install security-assessment@bfinster
```

For a self-hosted git host, see the [plugin install guide](plugins/dev-team/README.md#install); for a local clone, see [Local development](CONTRIBUTING.md#local-development) in CONTRIBUTING.

Then install the tier-1 static-analysis tools the pipeline depends on:

```bash
# macOS
./plugins/security-assessment/install-macos.sh           # tier-1 only
./plugins/security-assessment/install-macos.sh --all     # tier-1 + optional + PDF deps
./plugins/security-assessment/install-macos.sh --dry-run # preview without running

# Windows (requires Scoop)
.\plugins\security-assessment\install-windows.ps1
```

Verify: `./plugins/security-assessment/install.sh`

### Install `marketplace-dev` (optional)

Add this plugin if you're building or maintaining Claude Code plugins and marketplaces. It is independent of `dev-team` — install it on its own if that's all you need.

```bash
claude plugin install marketplace-dev@bfinster
```

Then use `/scaffold-plugin <name>` to create a new plugin, `/scaffold-marketplace <owner>` for a new marketplace, or `/plugin-audit [dir]` to check an existing plugin for structural compliance. See the [marketplace-dev guide](plugins/marketplace-dev/CLAUDE.md) for the full command list.

### Update an installed plugin

Run `/upgrade` from any Claude Code session with `dev-team` installed. It:

1. Reads the current installed scope from `claude plugin list` and passes `--scope <scope>` to `claude plugin update`, so project- and local-scope installs upgrade correctly rather than silently failing against the `user` default.
2. Asks before enabling marketplace-level auto-update (the same `extraKnownMarketplaces.<marketplace>.autoUpdate` flag the `/plugin` UI toggles); decline to keep manual control.
3. Reports the previous and new version, and prompts you to restart Claude Code so the new code loads.

Manual fallback when `/upgrade` is unavailable:

```bash
claude plugin update --scope <scope> dev-team@bfinster
claude plugin update --scope <scope> security-assessment@bfinster
claude plugin update --scope <scope> marketplace-dev@bfinster
```

## Key Concepts

**Agents** are roles with personas, responsibilities, and behavioral guidelines. Each agent knows when to escalate, who to collaborate with, and how to make decisions. Think of them as team members with defined specialties.

**Skills** are reusable knowledge modules — patterns, checklists, and procedures that any agent can reference. Skills define *how* to do something; agents define *when* and *why*.

**Commands** are slash shortcuts for **skills and workflows** (e.g. `/plan`, `/build`, `/specs`). Run `/help` for the full list. Note: **team agents are not slash commands** — you reach them through natural language or the workflow commands (see below), not by typing `/architect`.

## How to Use It

### Just describe what you want (natural language)

Most of the time, talk to the team in plain language. Claude classifies the task, adopts the right agent persona, loads the skills it needs, and coordinates multi-agent work when the task is complex:

```text
Build a new authentication system with OAuth2 support
```

To steer a specific role, name it in the request:

```text
As the architect, design a caching layer for the user service
As the security engineer, review the authentication flow for the mobile client
```

Under the hood this dispatches the matching agent persona (the same one the Agent tool addresses as `subagent_type: dev-team:architect`). There is no `/architect` command — the persona is selected by intent, not by a slash.

### Use the workflow commands

The structured lifecycle has real slash commands. These are the primary entry points:

```text
/specs   Capture intent, architecture, and acceptance criteria (lifecycle entry point)
/plan    Break a task into an incremental, test-driven plan
/build   Execute an approved plan with TDD and inline review
/pr      Run the pre-PR quality gate and open a pull request
/code-review   Run the review agents over your changes
/triage  Investigate a bug and file an issue with a fix plan
```

Run `/help` to see every available command.

### Invoke a skill directly

Beyond the lifecycle commands above, any skill *is* user-invocable as a slash command — use one to apply its procedures to your request:

```text
/ubiquitous-language Review the domain model for naming inconsistencies
/design-doc          Draft the technical design for the analytics pipeline
/hexagonal-architecture Apply ports-and-adapters to the payment module
```

## Common Workflows

### New Feature (full lifecycle)

Follow the core workflow (`/specs` → `/plan` → `/build` → `/pr`) described in the [README](README.md#dev-team-workflow). At any stage, reach for additional depth — skills via their slash commands, agent roles via natural language:

- "As the architect, define the technical approach…" to set or review architecture
- `/threat-modeling` if the feature crosses trust boundaries or handles sensitive data
- "As the QA engineer, confirm the acceptance tests pass and coverage is adequate"
- "As the tech writer, draft the user-facing docs" if documentation is needed

### Bug Fix

```text
Fix the race condition in the order processing pipeline
```

Or run `/triage` to investigate and file an issue with a fix plan. Bug fixes typically need only the Software Engineer; the QA Engineer follows if regression tests are needed.

### Architecture Review

```text
As the architect, review the current service topology for scalability concerns
```

The Architect may pull in the Security Engineer or Platform Engineer for cross-cutting concerns.

### API Design

```text
/api-design Define the contract for the inventory management API
```

Then ask the architect to review the contract for consistency with the domain model.

### Security Review

```text
/threat-modeling Analyze the new file upload endpoint
```

Then ask the security engineer to review the authentication flow for the mobile client.

### Pipeline and Deployment

```text
As the platform engineer, design the CI/CD pipeline for the new microservice
```

## Diagnostic & Audit Workflows

The commands above support a change in flight. These workflows do the opposite: point them at an **existing codebase** with no feature in progress and they report what to improve. They are read-only and advisory — each produces a report or scored assessment, none of them edit your code. Use them to take stock of a project you've inherited, to set a quality baseline, or as a periodic health check.

| Workflow | What it reports | Run it when |
|----------|-----------------|-------------|
| `/test-health` | Whole-suite test-strategy audit — suite shape, coverage-to-quadrant mapping, flaky tests, maturity — ending in an ordered plan. Rolls up `/test-design` + `/mutation-testing`, so start here. | "How healthy is our test suite?" |
| `/test-design` | A **Farley Score** (1–10 across Farley's 8 properties) for every test, plus per-file smells and testability blockers. | You want a quality score and per-test fixes without the full audit. |
| `/mutation-testing` | Whether tests actually catch bugs — mutates critical modules and triages survivors. | Coverage looks high but assertions feel weak. |
| `/code-review --all` | The full review-agent suite over the **entire repository**, not just a diff (`--background` for a no-gates drift review). | Auditing a whole project, or after a long gap. |
| `/semantic-scan` | The same business logic reimplemented across layers, with canonical-location suggestions. | Hunting hidden duplication in a layered codebase. |
| `/threat-modeling` | STRIDE analysis of attack surfaces, trust boundaries, and mitigations. | Reviewing a service's security posture. |
| `/docker-image-audit` | Container/Dockerfile CVEs, bloat, and best-practice violations (hadolint, Trivy, Grype). | Hardening or slimming an image. |
| `/benchmark <url>` | Runtime performance of a running app (Core Web Vitals, resource sizes) vs. saved baselines. | Establishing or checking a performance baseline. |
| `/explore --charter '<goal>'` | Charter-driven exploratory testing of a **running** target, auto-triaging critical defects. | Finding bugs the test suite misses. |

Two harness-level diagnostics review *how the project is set up to work with the team* rather than the product code: `/harness-audit` flags stale or redundant review agents and orchestration, and `/cost-report` reports token spend and cost regressions for a run. Run `/help` for the complete catalog.

## Available Agents and Skills

For the full roster of team agents, review agents, skills, and slash commands, see:

- [Agents](plugins/dev-team/docs/agent_info.md) — who does the work (team agents and review agents)
- [Skills & Commands](plugins/dev-team/docs/skills.md) — reusable knowledge modules and slash command catalog

## Rules to Know

1. **ATDD is mandatory.** Every behavior change needs a Gherkin scenario before implementation — no scenario, no code. `/specs` captures intent, architecture, and acceptance criteria; `/plan` then slices the feature and authors the per-slice scenarios.
2. **Human-in-the-loop.** Agents work autonomously but you make the decisions. They propose, you approve.
3. **Consistency gate is a hard stop.** For new features, the spec's three artifacts (intent, architecture, acceptance criteria) must pass the consistency gate before planning begins.
4. **Feedback keywords.** You can modify system behavior anytime using `amend`, `learn`, `remember`, or `forget`. Say `stop` or `pause` to halt agent work.
