<!-- Extracted from CLAUDE.md — do not duplicate here -->

This file contains the orchestration workflow details extracted from CLAUDE.md to keep the main config file lean.

## Request Processing Flow

For trivial tasks (typo fix, simple query), the Orchestrator routes directly to a single agent. For non-trivial tasks, the Orchestrator follows the **Research → Plan → Implement** workflow:

### Three-Phase Workflow

1. **Research** — Understand the system: find relevant files, trace data flows, identify the problem surface area. Sub-agents explore the codebase and return concise findings to keep the parent context clean. For non-trivial features, produce a **design document** at `docs/specs/` with problem statement, approach, alternatives, and scope boundaries. Optionally run **Design Interrogation** to stress-test the design and surface unresolved decisions before planning. For module boundaries, use **Design It Twice** to generate parallel alternative interfaces via sub-agents. Output: research progress file + design doc written to `.claude/memory/`.
2. **Human Review Gate** — Human reviews research findings and design doc. Catching a misunderstanding here prevents hundreds of bad lines of code.
3. **Plan** — Decompose the feature into **vertical slices**, author each slice's **Gherkin scenarios** (the behavioral contract), then specify every change: files, snippets, TDD steps, verification. Before the human sees the plan, **plan review personas** run in parallel as critical outside reviewers — the set **scales to a plan tier** (`trivial`/`standard`/`complex`, derived from slice/file counts and decision axes): Acceptance Test Critic (criteria quality, scenario gaps; always runs), Design & Architecture Critic (coupling, structural risks), UX Critic (user journey, accessibility; only with a UI surface), Strategic Critic (scope, risk, opportunity cost), and Parallelization Critic (same-wave build independence; only when slice count > 1). Complex plans get all five. Any blocker findings are addressed before the human gate. The plan is the primary review artifact — 200 lines of plan is far more reviewable than 2,000 lines of code. After approval, optionally run `/issues-from-plan` to create GitHub issues for team distribution. Output: implementation plan progress file written to `.claude/memory/`.
4. **Human Review Gate** — Human reviews the plan. This replaces traditional line-by-line code review as the primary quality gate.
5. **Implement** — Execute the plan by dispatching the `software-engineer` agent (by `subagent_type`) for each step. All code is built in **small per-behavior batches** with **vertical slices** — **Code-First Small Batches** (IMPLEMENT → TEST → REFACTOR), the sole build cadence, refactoring on every green (`docs/experiments/RECOMMENDATIONS.md`). The build runs **wave by wave** (the plan's `## Parallelization` schedule): independent slices in a wave build concurrently in **worktree isolation** (`isolation: "worktree"`), then a barrier reconciles the wave and gates on the full suite before the next wave. Worktree isolation requires Claude Code's `worktree.baseRef` setting to be `"head"` — set it in `.claude/settings.json` or `~/.claude/settings.json` (plugin- and project-local-scope settings are not honored for this key per issue #553's Slice 0 spike; full evidence: `docs/spikes/worktree-baseref-head-spike.md`). Effective concurrency is `min(--jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)` — parallel fan-out is opt-in: when neither `--jobs` nor the env var **`DEV_TEAM_MAX_PARALLEL_BUILDS`** is set the default is sequential (effective 1), and you opt into fan-out with `--jobs N` or the env var, each capped by wave width (#1515). A fully-dependent plan degrades to today's one-slice-at-a-time behavior. A **three-stage inline review** runs at a granularity that scales with step complexity — per step for `complex` steps, batched once at the slice boundary for `standard`/`trivial` steps: a deterministic static self-heal pass (scoped static analysis with a capped fix loop, `skills/build/references/static-self-heal.md`) runs to pass-or-cap first, then (1) spec-compliance-review checks code matches spec, (2) quality review agents check code quality, (3) browser verification for UI changes. Each checkpoint's find/fix/no-op outcome is logged to `.claude/metrics/review-value.jsonl` so the overhead is measurable. Actionable issues (error/warning severity with high/medium confidence) are **auto-fixed and re-reviewed** in a loop (up to 5 iterations) — only issues requiring human judgment are escalated. Run `/code-review` before committing (which auto-scopes to uncommitted changes and runs its own fix loop). Then invoke `dev-team:tech-writer` to verify all affected documentation is current. All agents must provide **verification evidence** (fresh test output) before claiming completion. Output: working code + test results + code review pass + docs verified.
6. **Human Review Gate** — Human reviews the final output. Lightweight if the plan was correct.
7. **Branch Workflow** — Create PR, choose merge strategy, clean up branch (see Branch Workflow skill).
8. **Learning loop** — Update configs if needed, log metrics, refine routing.

### Skills by Phase

| Phase | Skills Used | Purpose |
|-------|-----------|---------|
| **Research** | Design Doc, Domain Analysis, Domain-Driven Design, Threat Modeling, Design Interrogation, Design It Twice, Competitive Analysis | Understand the system, explore alternatives, stress-test designs |
| **Plan** | Specs, API Design, Hexagonal Architecture, Legacy Code | Define what to build, specify interfaces and test strategy |
| **Plan → Team** | `/issues-from-plan` | Break plan into GitHub issues for team distribution |
| **Implement** | Test-Driven Development (advisory, on request), Systematic Debugging, Mutation Testing, Browser Testing, Performance Benchmark, CI Debugging | Build in small per-behavior batches (Code-First Small Batches), debug issues (reproduce defects with a failing test first), validate quality, measure performance |
| **Bug Triage** | `/triage` (Systematic Debugging + file-based triage record in `.dev-team-reports/triage/`) | Investigate bugs and write actionable triage records |
| **Review** | Quality Gate Pipeline, Farley Score | Validate output before delivery |
| **Cross-phase** | Context Loading Protocol, Context Summarization, Feedback & Learning, Human Oversight Protocol, Performance Metrics, Governance & Compliance, Branch Workflow | Orchestration, context management, learning |

### Phase Transitions

Each phase runs in a fresh context window. The output of each phase is a structured progress file in `.claude/memory/` that onboards the next phase. See the Orchestrator agent for the full protocol.

## Multi-Agent Collaboration Protocol

### Sub-Agents as Context Isolation

The primary value of sub-agents is **context isolation**, not persona specialization. When a parent agent dispatches a sub-agent to explore, search, or analyze, the sub-agent absorbs the context burden of reading files and tracing code flows. Only a concise, structured finding returns to the parent — keeping the parent's context clean and focused on the actual task.

**Design sub-agent calls for minimal context return**:

- Send the sub-agent a specific question ("Where is user authentication handled? Return file paths and line numbers.")
- The sub-agent reads 20 files; the parent receives 10 lines of structured findings
- The parent can get right to work without the context burden of exploration

Persona specialization (Software Engineer, Architect, etc.) provides behavioral guardrails and domain expertise, but context isolation is what makes multi-agent workflows scale.

### Multi-Agent Coordination

When a task requires multiple agents:

1. Orchestrator identifies multi-agent task and assigns the three-phase workflow
2. Load primary agent + sub-agents for the current phase only
3. Sub-agents explore and return concise findings (context isolation)
4. Primary agent coordinates (defines interfaces, manages dependencies, resolves conflicts)
5. Phase output is written to `.claude/memory/` as a progress file
6. Human reviews before next phase begins
7. Integration and validation (QA validates, Architect reviews if architectural changes)
8. Unified result delivery

Referenced from: `plugins/dev-team/CLAUDE.md`
