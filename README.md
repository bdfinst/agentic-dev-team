# Agentic Scrum Team

A persona-driven AI development team orchestrated through Claude Code's `.claude/` configuration system. Each scrum role is an autonomous agent with defined behavior, skills, and collaboration protocols.

## Quick Start

1. Copy `.claude/` into your project
2. Run `claude`
3. Describe what you need

```text
> Build a REST API for user authentication with JWT tokens
```

The Scrum Master analyzes the request, selects the right agents, and coordinates delivery. See [Setup](docs/setup.md) for full installation steps.

## How It Works

**Agents** define roles (persona, behavior, collaboration). **Skills** define capabilities (patterns, guidelines, procedures). Agents own orchestration logic (*when* and *why*); skills own execution knowledge (*how*). This keeps agents readable as workflow definitions while keeping capabilities DRY.

```text
User Request → Scrum Master → Agent Selection → Task Execution → Result
                    ↑                                    ↓
                    └──────── Learning Loop ──────────────┘
```

## Documentation

| Guide | Description |
| --- | --- |
| [Setup](docs/setup.md) | Prerequisites and installation |
| [Usage](docs/usage.md) | Submitting requests, feedback keywords, intervention commands |
| [Agents](docs/agent_info.md) | Agent roster, persona template, adding/removing agents |
| [Skills](docs/skills.md) | Skills catalog, skill template, adding new skills |
| [Architecture](docs/architecture.md) | Context management, quality assurance, governance, multi-LLM routing |

## Team

| Agent | Purpose |
| --- | --- |
| **Scrum Master** | Routes tasks, coordinates agents, manages context budget |
| **Software Engineer** | Code generation, implementation, refactoring |
| **Data Scientist** | ML models, data analysis, statistical validation |
| **QA/SQA Engineer** | Testing, quality gates, peer validation |
| **UI/UX Designer** | Interface design, accessibility compliance |
| **Architect** | System design, tech decisions, scalability |
| **Product Manager** | Requirements, prioritization, stakeholder alignment |
| **Technical Writer** | Documentation, terminology consistency |

## Key Capabilities

| Capability | How It Works |
| --- | --- |
| **Selective loading** | Only agents and skills needed for the current task are loaded into context |
| **Context management** | Summarization triggers at 50% utilization to prevent hallucination |
| **Feedback keywords** | `amend`, `learn`, `remember`, `forget` update configuration in real time |
| **Human oversight** | Approval gates for high-impact decisions; `override`, `pause`, `stop` for intervention |
| **Quality validation** | 4-layer validation: self-check, peer review, human spot-check, post-hoc monitoring |
| **Audit trail** | All decisions and changes logged to `metrics/` |
| **Multi-LLM routing** | Route to Claude (complex) or Gemini (simple, cost-sensitive) |

## File Structure

```text
.claude/
├── CLAUDE.md              # Orchestration pipeline + registries
├── agents/                # Agent personas (8 agents)
├── skills/                # Reusable capabilities (10 skills)
├── memory/                # Conversation summaries (runtime)
└── metrics/               # Performance logs (runtime)
```
