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

The core workflow is four commands: `/specs` → `/plan` → `/build` → `/pr`

1. **Specify** — `/specs` to produce Intent Description, User-Facing Behavior (Gherkin scenarios), Architecture Specification, and Acceptance Criteria. The consistency gate must pass before moving on.
2. **Plan** — `/plan` to create a step-by-step TDD implementation plan. It checks for spec artifacts automatically. Human approves before building.
3. **Build** — `/build` to execute the approved plan. Each step follows RED-GREEN-REFACTOR with inline review checkpoints and verification evidence.
4. **Ship** — `/pr` to run quality gates and create a pull request.

For additional depth at any stage, invoke agents directly:
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
| `/orchestrator` | Task routing and coordination | Complex tasks, multi-agent work, unclear routing |
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
| `/specs` | Structured specification | New features — produces 4 artifacts before implementation |
| `/threat-modeling` | STRIDE-based security analysis | New endpoints, auth changes, trust boundary changes |
| `/api-design` | Contract-first API design | New APIs, service boundaries, inter-service contracts |
| `/hexagonal-architecture` | Port/adapter architecture | Structuring services and modules |
| `/domain-driven-design` | DDD patterns | Modeling domains, bounded contexts, aggregates |
| `/quality-gate-pipeline` | Unified quality gate (self-validation, verification, review-correction) | Before delivery, at completion, during rework |
| `/governance-compliance` | Audit and compliance | Quality gates, audit trails, ethics |
| `/agent-skill-authoring` | Creating agents and skills | Extending the team with new capabilities |
| `/feedback-learning` | Modify system behavior | Teaching the system new preferences |
| `/human-oversight-protocol` | Approval gates | High-impact decisions requiring human sign-off |
| `/context-loading-protocol` | Context management | Optimizing what gets loaded into context |
| `/context-summarization` | Context compression | Managing long conversations |
| `/performance-metrics` | Task metrics | Logging and reviewing performance data |
| `/beads` | Task tracking | Query unblocked work, create issues, link dependencies |

## Rules to Know

1. **ATDD is mandatory.** All behavior changes require scenarios in feature files (Gherkin) before implementation. No scenario, no code.
2. **Human-in-the-loop.** Agents work autonomously but you make the decisions. They propose, you approve.
3. **Consistency gate is a hard stop.** For new features, all four specification artifacts must be consistent before implementation begins.
4. **Feedback keywords.** You can modify system behavior anytime using `amend`, `learn`, `remember`, or `forget`. Say `stop` or `pause` to halt agent work.

## Prerequisites

### Beads (recommended)

Beads is a git-backed issue tracker for AI agents. It gives agents persistent, structured task memory across sessions — they query `bd ready --json` at the start of each session instead of relying on reconstructed prose context.

Install once, system-wide:

```bash
npm install -g @beads/bd   # or: brew install beads
```

Initialize in your project:

```bash
bd init
git add .beads && git commit -m "Initialize Beads task tracker"
```

That's it. Agents will automatically use Beads for task tracking following the `/beads` skill. If `bd` is not installed, agents fall back to `memory/` progress files only.

## Project Structure

```
agents/                # Team agents (12) + review agents (19)
skills/                # Reusable knowledge modules (24 skills)
commands/              # Slash commands (50 user-invocable)
hooks/                 # PreToolUse guards + PostToolUse advisory hooks
knowledge/             # Progressive disclosure reference files
prompts/               # Subagent prompt templates
CLAUDE.md              # Orchestration pipeline configuration (auto-loaded)
```

## Extending the Team

To add a new agent or skill, use:

```
/agent-skill-authoring Create a new agent for [role] or a new skill for [capability]
```

This invokes the authoring guide which defines the required sections, registration steps, and anti-patterns to avoid.
