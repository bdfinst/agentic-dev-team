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

### Invoke a skill directly

Skills *are* user-invocable as slash commands — use one to apply its procedures to your request:

```text
/threat-modeling Analyze the new payment API for security risks
/api-design Define the contract for the notification service
/specs Specify the user registration feature
```

### Use the workflow commands

The structured lifecycle has real slash commands. These are the primary entry points:

```text
/plan    Break a task into an incremental, test-driven plan
/build   Execute an approved plan with TDD and inline review
/pr      Run the pre-PR quality gate and open a pull request
/code-review   Run the review agents over your changes
/triage  Investigate a bug and file an issue with a fix plan
```

Run `/help` to see every available command.

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

## Available Agents and Skills

For the full roster of team agents, review agents, skills, and slash commands, see:

- [Agents](plugins/dev-team/docs/agent_info.md) — who does the work (team agents and review agents)
- [Skills & Commands](plugins/dev-team/docs/skills.md) — reusable knowledge modules and slash command catalog

## Rules to Know

1. **ATDD is mandatory.** Every behavior change needs a Gherkin scenario before implementation — no scenario, no code. `/specs` captures intent, architecture, and acceptance criteria; `/plan` then slices the feature and authors the per-slice scenarios.
2. **Human-in-the-loop.** Agents work autonomously but you make the decisions. They propose, you approve.
3. **Consistency gate is a hard stop.** For new features, the spec's three artifacts (intent, architecture, acceptance criteria) must pass the consistency gate before planning begins.
4. **Feedback keywords.** You can modify system behavior anytime using `amend`, `learn`, `remember`, or `forget`. Say `stop` or `pause` to halt agent work.
