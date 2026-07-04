# Agentic Dev Team - Orchestration Pipeline

## System Overview

Fully automated development team using persona-driven AI agents. The Orchestrator dispatches tasks to specialized agents by classification, complexity, and expertise.

## North Star

Every change must reduce friction: **fewer missteps, less rework, lower token cost.** Measure friction — don't assume it. A change that cannot name the friction it removes does not ship.

## Architecture

- **CLAUDE.md**: Core philosophy + quick reference (always loaded)
- **Skills**: Detailed procedures (loaded on-demand)
- **Knowledge**: Registries, rubrics, patterns (loaded on-demand by agents)
- **Agents**: Behavioral specifications (loaded per-phase, never all at once)
- **Templates**: Language-specific agent templates (scaffolded by `/setup`)

## Output Guardrails

1. **Write to files, not chat.** Artifacts go to files — not chat deliverables.
2. **Plan-only mode.** When asked for a plan, produce ONLY the plan.
3. **Incremental output.** First draft within 3-4 tool calls, then refine.

## Core Principles

1. **Selective Agent Loading**: Load only necessary agents. Target < 10,000 tokens simple tasks.
2. **40% Context Ceiling**: A conservative target, not an accuracy cliff — see [Context Management](docs/context-management.md) for the guide and evidence. Enforced by `hooks/context_ceiling_guard.py`.
3. **Persona-Driven Behavior**: Specs in `.claude/agents/`. Build concurrency: `DEV_TEAM_MAX_PARALLEL_BUILDS` (default 3).
4. **Human-in-the-Loop**: Autonomous agents, human oversight.
5. **Dynamic Configuration**: Config changes → `metrics/config-changelog.jsonl`.
6. **ATDD + Code-First Small Batches** (TDD opt-in — docs/experiments/RECOMMENDATIONS.md): no code without a `/plan` scenario.
7. **Python for cross-OS scripts**: shipped hooks/scripts are Python 3.8+ stdlib-only (ADR 0014, 0015).

## Team Organization

See @docs/team-structure.md for the full team org chart.

## Agent & Skill Registry

Full registry (token counts, effort bands): [`knowledge/agent-registry.md`](knowledge/agent-registry.md). Registry gate (`/agent-audit`) fails CI on drift.

Teams can create `REVIEW-CONTEXT.md` in the project root with domain knowledge code analysis cannot discover — `/code-review` passes it to each agent.

## Skills Registry

See [knowledge/skills-registry.md](knowledge/skills-registry.md) for the full command reference. All review skills run under orchestrator direction via the Resolution Procedure (`agents/orchestrator.md`).

## Request Processing Flow

See [knowledge/request-processing-flow.md](knowledge/request-processing-flow.md) for the three-phase workflow (Research → Plan → Implement), inline review protocol, phase transitions, and multi-agent collaboration.

## Model Routing

Each agent declares an effort band (`effort: low|medium|high`). Resolution enforced by `hooks/agent_model_resolve.py` via `knowledge/model-routing.json` (or `.claude/model-ladder.json`). See `agents/orchestrator.md` → Resolution Procedure and `/model-routing-check`.

## Context Management

1. **[Context Loading Protocol](skills/context-loading-protocol/SKILL.md)** — decides *what* to load and *when*
2. **[Context Summarization](skills/context-summarization/SKILL.md)** — decides *when* to compress and *how*

Token budgets per agent: see [knowledge/agent-registry.md](knowledge/agent-registry.md).

Operating rules: load on demand; summarize phases to `memory/` before next-phase load; new conversations read from `memory/`.

## Feedback & Learning

Trigger keywords: `amend`, `learn`, `remember`, `forget`. Full procedure: **[Feedback & Learning](skills/feedback-learning/SKILL.md)**.

## Human Oversight

Required for high-impact decisions. Full protocol: **[Human Oversight Protocol](skills/human-oversight-protocol/SKILL.md)**. Intervention commands: feedback keywords above, plus `override`, `pause`, `stop`.

## Proxy Resilience

429s: **[Proxy Resilience](skills/proxy-resilience/SKILL.md)**. Refused conns: [proxy-connectivity.md](knowledge/proxy-connectivity.md).

## Quality & Accuracy

All agents apply the **[Quality Gate Pipeline](skills/quality-gate-pipeline/SKILL.md)**. Ethics and audit logging: **[Governance & Compliance](skills/governance-compliance/SKILL.md)**.

**Quality ownership.** Agents own the quality *state* — green means the whole suite, not just the diff. A red signal must be fixed or triaged, never stepped over.

Hooks: `pre_tool_guard.py` blocks sensitive path writes; `destructive_guard.py` warns on destructive commands; `context_ceiling_guard.py` enforces the context ceiling (see above).

## Performance Metrics

Logged to `metrics/` in JSONL format. See **[Performance Metrics](skills/performance-metrics/SKILL.md)**.

Every quantitative claim must name the instrument that measures it. **Instrumented:** token budgets (`scripts/measure-tokens.sh`), per-agent accuracy (`/agent-eval`). **Not yet:** efficiency gains, hallucination rate, first-pass acceptance (#102, #106).
