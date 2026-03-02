# Usage

## Submit a Request

Describe what you need in natural language:

```text
> Build a REST API for user authentication with JWT tokens
```

The Scrum Master classifies the task, selects agents (Software Engineer + Architect + QA), loads them in phases, and coordinates delivery.

## Multi-Agent Collaboration

Complex requests automatically engage multiple agents:

```text
> Design and implement a dashboard with real-time data visualization
```

Agents are loaded in phases (design, then implementation, then testing) to keep context utilization low. The Scrum Master manages transitions between phases.

## Give Feedback

Four keywords modify system behavior at any time:

| Keyword | Intent | Example |
| --- | --- | --- |
| `amend` | Modify existing behavior | `amend: software engineer should prefer functional patterns` |
| `learn` | Teach something new | `learn: our APIs use kebab-case URLs` |
| `remember` | Persist a preference | `remember: always run tests before completing tasks` |
| `forget` | Remove a preference | `forget: the kebab-case URL convention` |

Changes apply immediately, are logged to an audit trail, and can be rolled back. See [Feedback & Learning](../.claude/skills/feedback-learning.md) for the full procedure.

## Intervene

When you need more control over agent behavior:

| Command | Effect |
| --- | --- |
| `override: X -> Y` | Replace an agent's decision with yours |
| `pause` | Halt work for review, then resume |
| `stop` | Emergency halt of all agent activity |

See [Human Oversight Protocol](../.claude/skills/human-oversight-protocol.md) for the full intervention model.
