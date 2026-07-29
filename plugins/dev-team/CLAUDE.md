# Agentic Dev Team - Orchestration Pipeline

## System Overview

Persona-driven AI agent team. The Orchestrator dispatches tasks to specialized agents by classification, complexity, and expertise.

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
3. **Incremental output.** First draft within 3–4 tool calls, then refine.

## Core Principles

1. **Selective Agent Loading**: Load only necessary agents. Target < 10,000 tokens simple tasks.
2. **40% Context Ceiling**: Conservative target, not an accuracy cliff — see [Context Management](docs/context-management.md). Enforced by `hooks/context_ceiling_guard.py`.
3. **Persona-Driven Behavior**: Specs in `.claude/agents/`. Build concurrency `DEV_TEAM_MAX_PARALLEL_BUILDS`: unset → `1` (sequential); set `--jobs`/env to opt into fan-out, capped by wave width.
4. **Human-in-the-Loop**: Autonomous agents, human oversight.
5. **Dynamic Configuration**: Config changes → `.claude/metrics/config-changelog.jsonl`.
6. **ATDD + Code-First Small Batches** (sole build cadence — Rec 3, docs/experiments/RECOMMENDATIONS.md): no code without a `/plan` scenario.
7. **Python for cross-OS scripts**: shipped hooks/scripts are Python 3.8+ stdlib-only (ADR 0014, 0015).

## Team Organization

See @docs/team-structure.md for the org chart.

## Agent & Skill Registry

Full registry (token counts, effort bands): [`knowledge/agent-registry.md`](knowledge/agent-registry.md). Registry gate (`/agent-audit`) fails CI on drift.

Teams can create `REVIEW-CONTEXT.md` in the project root with domain knowledge code analysis cannot discover — `/code-review` passes it to each agent.

## Skills Registry

See [knowledge/skills-registry.md](knowledge/skills-registry.md) for the full command reference. All review skills run under orchestrator direction (`agents/orchestrator.md`).

## Request Processing Flow

See [knowledge/request-processing-flow.md](knowledge/request-processing-flow.md) for the three-phase workflow (Research → Plan → Implement), inline review protocol, and multi-agent collaboration.

## Model/Effort

Each agent declares `model:`/`effort:` directly in frontmatter — the native Claude Code sub-agent contract, resolved by the harness itself (ADR 0026). See `agents/orchestrator.md` → Model/Effort Resolution.

## Context Management

1. **[Context Loading Protocol](skills/context-loading-protocol/SKILL.md)** — decides *what* to load and *when*
2. **[Handoff](skills/handoff/SKILL.md)** — decides *when*/*how* to compress (continue) or fork side-work (fork)

Token budgets per agent: see [knowledge/agent-registry.md](knowledge/agent-registry.md).

Rules: load on demand; summarize phases to `.claude/memory/` before next phase; new conversations read from `.claude/memory/`.

## Feedback & Learning

**[Feedback & Learning](skills/feedback-learning/SKILL.md)** is a choreographic skill — keywords `amend`, `learn`, `remember`, `forget` fire directly via Claude Code's skill-matching, independent of orchestrator phase classification.

## Human Oversight

Required for high-impact decisions. Full protocol: **[Human Oversight Protocol](skills/human-oversight-protocol/SKILL.md)**. Commands: `amend`/`learn`/`remember`/`forget` (feedback-learning), `override`, `pause`, `stop`.

## Proxy Resilience

429s: **[Proxy Resilience](skills/proxy-resilience/SKILL.md)**. Refused conns: [proxy-connectivity.md](knowledge/proxy-connectivity.md).

## Quality & Accuracy

All agents apply the **[Quality Gate Pipeline](skills/quality-gate-pipeline/SKILL.md)**. Ethics and audit logging: **[Governance & Compliance](skills/governance-compliance/SKILL.md)**.

**Quality ownership.** Agents own the quality *state* — green means the whole suite, not just the diff. Red signals must be fixed or triaged, never stepped over.

Hooks: `pre_tool_guard.py` blocks sensitive path writes; `destructive_guard.py` warns on destructive commands; `context_ceiling_guard.py` enforces the context ceiling (see above).

## Performance Metrics

Logged to `.claude/metrics/` as JSONL. **[Performance Metrics](skills/performance-metrics/SKILL.md)**.

Every claim must name the instrument. **Instrumented:** token budgets (`scripts/measure-tokens.sh`), agent accuracy (`/agent-eval`), efficiency (`/orchestration-benchmark`). **Not yet:** hallucination rate, first-pass acceptance.
