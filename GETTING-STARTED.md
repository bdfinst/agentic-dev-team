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
/agent-assisted-specification Specify the user registration feature
```

### Let the Scrum Master route

For complex or ambiguous requests, invoke the Scrum Master and let it decide which agents to load:

```
/scrum-master Build a new authentication system with OAuth2 support
```

The Scrum Master classifies the task, selects the right agents, and coordinates multi-agent collaboration when needed.

## Common Workflows

### New Feature (full lifecycle)

This is the most common workflow. It follows ATDD — behaviors are defined as scenarios in feature files before any implementation begins.

1. **Specify** — `/agent-assisted-specification` to produce Intent Description, User-Facing Behavior (Gherkin scenarios), Architecture Specification, and Acceptance Criteria
2. **Design** — `/architect` to define the technical approach, review the architecture specification
3. **Secure** — `/threat-modeling` if the feature crosses trust boundaries or handles sensitive data
4. **Implement** — `/software-engineer` to build it, guided by the feature file scenarios
5. **Test** — `/qa-engineer` to validate acceptance tests pass and coverage is adequate
6. **Document** — `/tech-writer` if user-facing documentation is needed

The consistency gate in step 1 must pass before proceeding to implementation. This is a hard stop.

### Bug Fix

```
/software-engineer Fix the race condition in the order processing pipeline
```

Bug fixes typically need only the Software Engineer. The QA Engineer loads afterward if regression tests are needed.

### Architecture Review

```
/architect Review the current service topology for scalability concerns
```

The Architect may pull in the Security Engineer or DevOps/SRE Engineer for cross-cutting concerns.

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
/devops-sre-engineer Design the CI/CD pipeline for the new microservice
```

## Available Agents

| Command | Role | When to Use |
|---------|------|-------------|
| `/scrum-master` | Task routing and coordination | Complex tasks, multi-agent work, unclear routing |
| `/software-engineer` | Code implementation | Writing code, bug fixes, refactoring |
| `/architect` | System design | Architecture decisions, API design, scalability |
| `/qa-engineer` | Testing and quality | Test strategy, acceptance tests, quality gates |
| `/product-manager` | Requirements | Feature scoping, prioritization, user stories |
| `/security-engineer` | Security analysis | Threat modeling, vulnerability assessment, secure design |
| `/devops-sre-engineer` | Operations | Pipelines, deployment, monitoring, reliability |
| `/data-scientist` | Data and ML | ML models, data analysis, data pipelines |
| `/ui-ux-designer` | Interface design | UX patterns, accessibility, design specs |
| `/tech-writer` | Documentation | Technical docs, style consistency, user guides |

## Available Skills

| Command | Skill | When to Use |
|---------|-------|-------------|
| `/agent-assisted-specification` | Structured specification | New features — produces 4 artifacts before implementation |
| `/threat-modeling` | STRIDE-based security analysis | New endpoints, auth changes, trust boundary changes |
| `/api-design` | Contract-first API design | New APIs, service boundaries, inter-service contracts |
| `/hexagonal-architecture` | Port/adapter architecture | Structuring services and modules |
| `/domain-driven-design` | DDD patterns | Modeling domains, bounded contexts, aggregates |
| `/accuracy-validation` | Output self-validation | Verifying claims before delivery |
| `/task-review-correction` | Review-correct-verify loop | Reviewing completed work, rework cycles |
| `/governance-compliance` | Audit and compliance | Quality gates, audit trails, ethics |
| `/agent-skill-authoring` | Creating agents and skills | Extending the team with new capabilities |
| `/feedback-learning` | Modify system behavior | Teaching the system new preferences |
| `/human-oversight-protocol` | Approval gates | High-impact decisions requiring human sign-off |
| `/context-loading-protocol` | Context management | Optimizing what gets loaded into context |
| `/context-summarization` | Context compression | Managing long conversations |
| `/performance-metrics` | Task metrics | Logging and reviewing performance data |

## Rules to Know

1. **ATDD is mandatory.** All behavior changes require scenarios in feature files (Gherkin) before implementation. No scenario, no code.
2. **Human-in-the-loop.** Agents work autonomously but you make the decisions. They propose, you approve.
3. **Consistency gate is a hard stop.** For new features, all four specification artifacts must be consistent before implementation begins.
4. **Feedback keywords.** You can modify system behavior anytime using `amend`, `learn`, `remember`, or `forget`. Say `stop` or `pause` to halt agent work.

## Project Structure

```
.claude/
  CLAUDE.md              # System configuration (auto-loaded)
  agents/                # Agent persona files (10 agents)
  skills/                # Reusable knowledge modules (14 skills)
  commands/              # Slash command wrappers
  memory/                # Conversation summaries (written by agents)
  metrics/               # Performance logs (JSONL)
```

## Extending the Team

To add a new agent or skill, use:

```
/agent-skill-authoring Create a new agent for [role] or a new skill for [capability]
```

This invokes the authoring guide which defines the required sections, registration steps, and anti-patterns to avoid.
