# Architecture

## System Overview

```text
User Request → Scrum Master → Agent Selection → Task Execution → Result
                    ↑                                    ↓
                    └──────── Learning Loop ──────────────┘
```

The Scrum Master receives every request, classifies it by type and complexity, selects agents, loads them in phases, and coordinates delivery. After each task, the learning loop captures metrics and evaluates whether configuration updates are needed.

## Context Management

The Scrum Master manages context utilization using two operational skills.

### Loading Protocol

[Context Loading Protocol](../.claude/skills/context-loading-protocol.md) controls what gets loaded and when:

1. **Classify** the task (simple, standard, multi-agent, complex)
2. **Select** the minimum set of agents and skills required
3. **Load in phases**: primary agent first, supporting agents as their phase begins
4. **Unload** previous-phase agents via summarization before loading next-phase agents

### Summarization

[Context Summarization](../.claude/skills/context-summarization.md) controls when to compress:

| Utilization | Action |
| --- | --- |
| < 40% | Normal operation |
| 40-50% | Prepare for summarization |
| 50-60% | Summarize older conversation turns |
| 60-75% | Aggressive summarization |
| 75%+ | Write summary to `memory/`, start new conversation |

Utilization is measured via the `usage` field in API responses. Summaries follow a structured template and are stored in `memory/` for cross-session continuity.

### Token Budgets

| Component | ~Tokens |
| --- | --- |
| CLAUDE.md (always loaded) | 870 |
| Single agent | 290-560 |
| Single skill | 420-1,020 |
| All agents (no skills) | 2,790 |
| Full load (all agents + all skills) | 10,800 |

A typical task loads 1 agent + 1-2 skills: roughly 1,000-2,000 tokens of configuration overhead.

## Quality Assurance

Validation happens at four progressive layers:

| Layer | Who | When |
| --- | --- | --- |
| Self-validation | Active agent | Before delivering any output |
| Peer validation | QA agent | After primary output, before delivery |
| Human spot-check | User | After delivery (accept/reject/amend) |
| Post-hoc monitoring | Scrum Master | During learning loop |

Every agent applies the [Accuracy Validation](../.claude/skills/accuracy-validation.md) self-check before output. This includes factual accuracy verification, instruction fidelity, internal consistency, and confidence scoring.

Quality gates by task type:

| Task Type | Required Gates |
| --- | --- |
| Code implementation | Self-validation + QA review |
| Architecture design | Self-validation + human approval |
| Documentation | Self-validation + terminology check |
| Bug fix | Self-validation + regression test |
| Data analysis | Self-validation + statistical validation |

## Human Oversight

Agents operate autonomously within boundaries. The [Human Oversight Protocol](../.claude/skills/human-oversight-protocol.md) defines three levels of human involvement:

| Level | When | Example |
| --- | --- | --- |
| **Autonomous** | Routine work within scope | Writing a unit test |
| **Notify** | Significant but within scope | Choosing between two valid patterns |
| **Approve** | High-impact or outside scope | Database schema change, production deploy |

Intervention commands (`override`, `pause`, `stop`) give humans immediate control when needed.

## Governance

[Governance & Compliance](../.claude/skills/governance-compliance.md) defines audit and ethics requirements:

- All task completions logged to `metrics/` (JSONL format)
- All configuration changes logged to `metrics/config-changelog.jsonl`
- Conversation summaries stored in `memory/` for cross-session continuity
- Sensitive data (credentials, PII) never stored in metrics or memory files
- All agent decisions must be explainable on request

## Feedback Loop

[Feedback & Learning](../.claude/skills/feedback-learning.md) enables continuous improvement:

1. User provides feedback via keywords (`amend`, `learn`, `remember`, `forget`)
2. Changes are previewed, applied, and logged with full audit trail
3. The Scrum Master monitors for recurring patterns (3+ occurrences)
4. System-initiated changes are proposed to the user with rationale

## Multi-LLM Routing

Tasks can be routed to different LLMs based on complexity and cost:

| Criteria | Claude | Gemini |
| --- | --- | --- |
| Task complexity | Complex tasks | Simple, high-volume |
| Cost sensitivity | Premium | Cost-optimized |
| Context requirements | Large context | Standard context |
| Precision requirements | Critical components | Standard components |

## Performance Targets

| Metric | Target |
| --- | --- |
| Efficiency gains | 10-15% over manual workflows |
| Structured data accuracy | > 95% |
| Hallucination rate | < 5% |
| Conversation-long accuracy | > 95% |
| First-pass acceptance | > 80% |
