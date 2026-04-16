# Getting Started with the Agentic Scrum Team

This project gives you an AI development team — specialized agents with distinct roles, reusable skills they draw on, and slash commands to invoke them. You talk to the team in natural language. The system figures out who should do the work and what knowledge they need.

## Key Concepts

**Agents** are roles with personas, responsibilities, and behavioral guidelines. Each agent knows when to escalate, who to collaborate with, and how to make decisions. Think of them as team members with defined specialties.

**Skills** are reusable knowledge modules — patterns, checklists, and procedures that any agent can reference. Skills define *how* to do something; agents define *when* and *why*.

**Commands** are slash shortcuts (`/agent-name` or `/skill-name`) that invoke an agent or skill directly.

## How to Use It

### Invoke an agent directly

Use a slash command to adopt a specific agent's persona:

```
/architect Design a caching layer for the user service
/software-engineer Implement the caching adapter using hexagonal architecture
/qa-engineer Write acceptance tests for the caching behavior
```

The agent loads its persona, skills, and collaboration protocols, then applies them to your request.

### Invoke a skill directly

Use a slash command to apply a skill's procedures without a specific persona:

```
/threat-modeling Analyze the new payment API for security risks
/api-design Define the contract for the notification service
/specs Specify the user registration feature
```

### Let the Orchestrator route

For complex or ambiguous requests, invoke the Orchestrator and let it decide which agents to load:

```
/orchestrator Build a new authentication system with OAuth2 support
```

The Orchestrator classifies the task, selects the right agents, and coordinates multi-agent collaboration when needed.

## Common Workflows

### New Feature (full lifecycle)

Follow the core workflow (`/specs` → `/plan` → `/build` → `/pr`) described in the [README](README.md#workflow). At any stage, invoke agents directly for additional depth:
- `/architect` to define the technical approach or review architecture
- `/threat-modeling` if the feature crosses trust boundaries or handles sensitive data
- `/qa-engineer` to validate acceptance tests pass and coverage is adequate
- `/tech-writer` if user-facing documentation is needed

### Bug Fix

```
/software-engineer Fix the race condition in the order processing pipeline
```

Bug fixes typically need only the Software Engineer. The QA Engineer loads afterward if regression tests are needed.

### Architecture Review

```
/architect Review the current service topology for scalability concerns
```

The Architect may pull in the Security Engineer or Ops Engineer for cross-cutting concerns.

### API Design

```
/api-design Define the contract for the inventory management API
/architect Review the API contract for consistency with the domain model
```

### Security Review

```
/security-engineer Review the authentication flow for the mobile client
/threat-modeling Analyze the new file upload endpoint
```

### Pipeline and Deployment

```
/ops-engineer Design the CI/CD pipeline for the new microservice
```

## Available Agents and Skills

For the full roster of team agents, review agents, skills, and slash commands, see:

- [Agents](docs/agent_info.md) — who does the work (team agents and review agents)
- [Skills & Commands](docs/skills.md) — reusable knowledge modules and slash command catalog

## Rules to Know

1. **ATDD is mandatory.** All behavior changes require scenarios in feature files (Gherkin) before implementation. No scenario, no code.
2. **Human-in-the-loop.** Agents work autonomously but you make the decisions. They propose, you approve.
3. **Consistency gate is a hard stop.** For new features, all four specification artifacts must be consistent before implementation begins.
4. **Feedback keywords.** You can modify system behavior anytime using `amend`, `learn`, `remember`, or `forget`. Say `stop` or `pause` to halt agent work.

## Extending the Team

To add a new agent or skill, use:

```
/agent-skill-authoring Create a new agent for [role] or a new skill for [capability]
```

This invokes the authoring guide which defines the required sections, registration steps, and anti-patterns to avoid.
