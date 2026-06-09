# Getting Started with the Agentic Dev Team

This project gives you an AI development team — specialized agents with distinct roles, reusable skills they draw on, and slash commands for skills and workflows. You talk to the team in natural language. The system figures out who should do the work and what knowledge they need.

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
/threat-modeling Analyze the new payment API for security risks
/api-design Define the contract for the notification service
/specs Specify the user registration feature
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
| `/test-health` | Project-wide test-strategy audit: suite shape vs. architecture fit, coverage mapped to the testing quadrants, coverage + mutation health, flaky tests, automation maturity — ending in an ordered improvement plan. | "How healthy is our test suite?" — the broad starting point for test work. |
| `/test-design` | Deep test-design review of the existing suite: a **Farley Score** for all existing tests (quality 1–10 across Dave Farley's 8 properties) plus per-file smells and testability blockers. | You want a quantitative quality score and concrete per-test fixes. |
| `/mutation-testing` | Whether your existing tests actually catch bugs — runs a real mutation tool on critical modules and triages surviving mutants. | Coverage looks high but you suspect assertions are weak. |
| `/code-review --all` | The full review-agent suite (architecture, complexity, naming, security, duplication, docs, …) over the **entire repository**, not just a diff. Add `--background` for a no-gates structural drift review. | Auditing code quality across a whole project or after a long period without review. |
| `/semantic-scan` | Business logic reimplemented in multiple layers — the same domain calculation duplicated across domain services, adapters, and UI — with canonical-location suggestions. | Hunting for hidden duplication and drift in a layered codebase. |
| `/threat-modeling` | STRIDE security analysis of attack surfaces, trust boundaries, and mitigations. | Reviewing the security posture of an existing service or data flow. |
| `/docker-image-audit` | Container and Dockerfile security (CVEs), image bloat, and best-practice violations via hadolint, Trivy, and Grype. | Hardening or slimming an existing image. |
| `/benchmark <url>` | Runtime performance of a running app (Core Web Vitals, resource sizes), compared against saved baselines. | Establishing or checking a performance baseline. |
| `/explore --charter '<goal>'` | Charter-driven exploratory testing of a **running** target: structured heuristics + adversarial probing, auto-triaging critical defects into a report. | Finding bugs in a live app that the test suite doesn't cover. |

```text
/test-health                      Audit the whole test suite and get an improvement plan
/test-design                      Score every existing test (Farley Score) and surface smells
/code-review --all                Review the entire repository, not just pending changes
/semantic-scan                    Find duplicated business logic across layers
```

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
