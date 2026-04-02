# Agentic Dev Team

A Claude Code plugin that adds a full persona-driven AI development team to any project. The Orchestrator routes tasks to specialized agents, inline review checkpoints catch quality issues during implementation, and skills provide reusable knowledge modules that any agent can draw on.

## Workflow

Four commands drive feature development from idea to pull request:

```
/specs  →  /plan  →  /build  →  /pr
```

| Step | Command | What it does |
| --- | --- | --- |
| **1. Specify** | `/specs` | Collaborate on four artifacts: Intent, BDD/Gherkin scenarios, Architecture notes, Acceptance Criteria. A consistency gate must pass before moving on. Skip for bug fixes, refactors, or trivial changes. |
| **2. Plan** | `/plan` | Create a step-by-step TDD implementation plan. Checks for spec artifacts first — if none exist, asks whether to continue or run `/specs`. Human approves before any code is written. |
| **3. Build** | `/build` | Execute the approved plan. Each step follows RED-GREEN-REFACTOR with inline review checkpoints (spec-compliance first, then quality agents). Produces verification evidence. |
| **4. Ship** | `/pr` | Run quality gates (tests, typecheck, lint, code review) and create a pull request. |

Each step produces artifacts the next step consumes. Human review gates sit between each transition.

```mermaid
flowchart LR
    S["/specs\n4 artifacts"] -->|consistency gate| P["/plan\nTDD steps"]
    P -->|human approval| B["/build\nRED-GREEN-REFACTOR"]
    B -->|code review| PR["/pr\nquality gates"]
```

For bug fixes or simple tasks, skip `/specs` and start at `/plan` or go straight to implementation. The orchestrator routes trivially when the full workflow isn't needed.

### Supporting commands

| Command | When to use |
| --- | --- |
| `/code-review` | Run all review agents against changed files (also runs as part of `/build`) |
| `/continue` | Resume an in-progress build or plan across sessions |
| `/browse` | Visual QA via Playwright |
| `/careful` / `/freeze` / `/guard` | Safety modes for production-critical sessions |

### Automated pre-commit review

Every `git commit` is automatically gated by `/code-review --changed`. A `PreToolUse` hook detects commit attempts and blocks them until a passing review exists for the exact set of staged files.

**Flow**: attempt commit → hook blocks → Claude runs `/code-review --changed` → if pass/warn, a `.review-passed` gate file is written → next commit attempt succeeds.

**Bypass**: `git commit --no-verify` skips the review gate.

## How It Works

**Team agents** define roles (persona, behavior, collaboration). **Review agents** check work quality in real time. **Skills** define knowledge (patterns, guidelines, procedures). **Slash commands** invoke agents and skills directly. The **Orchestrator** controls task routing, model selection, and the inline review feedback loop.

### Three-Phase Workflow (Orchestrator-Driven)

For complex tasks where the orchestrator manages the full lifecycle, every non-trivial task follows **Research → Plan → Implement** with human review gates between phases:

- **Research** produces a **design document** (`docs/specs/`) with problem statement, alternatives, and scope boundaries
- **Plan** is pre-checked by an automated **plan reviewer** before the human sees it
- **Implement** enforces strict **TDD** (RED-GREEN-REFACTOR with hard gates), uses **worktree isolation** for parallel units, and runs a **three-stage inline review**: spec-compliance first ("does code match spec?"), then quality agents ("is code good?"), then browser verification for UI changes. All agents must provide **verification evidence** (fresh test output) before claiming completion. After the human gate, a **branch workflow** handles PR creation and merge strategy.

```mermaid
flowchart TD
    U([User Request]) --> O[Orchestrator]

    subgraph "Phase 1 — Research"
        O --> SP["/specs\nIntent · BDD · Architecture · Criteria"]
        SP --> DD["Design Doc\ndocs/specs/"]
    end

    DD --> HG1([Human Gate — approve spec + design])

    subgraph "Phase 2 — Plan"
        HG1 --> PL["/plan\nTDD steps · complexity tiers · acceptance criteria"]
        PL --> PR["Plan Reviewer\nprompts/plan-reviewer.md"]
    end

    PR --> HG2([Human Gate — approve plan])

    subgraph "Phase 3 — Implement (/build)"
        HG2 --> CV["Verify criteria testability\n(sprint contract gate)"]
        CV --> NEXT{"Next step?"}
        NEXT -->|more steps| IM["TDD Loop\nRED → GREEN → REFACTOR"]

        subgraph "Per-Step Inline Review"
            IM --> CX{"Complexity?"}
            CX -->|trivial| NEXT
            CX -->|standard / complex| SC["Stage 1: Spec Compliance\n/review-agent spec-compliance"]
            SC -->|fail| IM
            SC -->|pass| QR["Stage 2: Quality Agents\n/review-agent per change type"]
            QR -->|"fail (max 2×)"| IM
            QR -->|pass| BV{"UI change?"}
            BV -->|yes| BR["Stage 3: Browser Verify\n/browse smoke test"]
            BV -->|no| NEXT
            BR --> NEXT
        end

        NEXT -->|all done| CR["/review --changed\nFull agent suite · all modified files"]
    end

    CR --> HG3([Human Gate — approve implementation])
    HG3 --> PRR["/pr\nQuality gate · create pull request"]
    PRR --> LL["Learning Loop\nMetrics · /harness-audit"]
    LL --> O
```

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- `jq` — used by PostToolUse hooks for JSON parsing
  - macOS: `brew install jq`
  - Linux: `apt install jq` or `yum install jq`

**Optional:**

- `semgrep` — required only for `/semgrep-analyze`

  ```bash
  pip install semgrep
  # or: brew install semgrep
  ```

- `playwright` — required only for `/browse` (browser-based QA)

  ```bash
  npx playwright install chromium
  ```

### Plugin install (recommended)

Add the marketplace source, then install the plugin. The marketplace resolves the plugin location automatically from `marketplace.json`.

**From GitHub:**

```bash
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-dev-team
```

**From a local clone:**

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install agentic-dev-team
```

By default the marketplace is registered at user scope (available in all projects). To scope it to a single project:

```bash
claude plugin marketplace add --scope project https://github.com/bdfinst/agentic-dev-team
claude plugin install --scope project agentic-dev-team
```

### Upgrading from a previous install

If you previously installed the plugin before the directory restructure (pre-v2.1), remove and re-add the marketplace source:

```bash
claude plugin marketplace remove agentic-dev-team
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-dev-team
```

### Verify

After starting Claude Code, confirm the system is working:

```
> What agents are available on this team?
```

## Team Agents

| Agent | Purpose |
| --- | --- |
| [**Orchestrator**](plugins/agentic-dev-team/agents/orchestrator.md) | Routes tasks, selects models, coordinates inline review feedback loop |
| [**Software Engineer**](plugins/agentic-dev-team/agents/software-engineer.md) | Code generation, implementation, applies review corrections |
| [**Data Scientist**](plugins/agentic-dev-team/agents/data-scientist.md) | ML models, data analysis, statistical validation |
| [**QA/SQA Engineer**](plugins/agentic-dev-team/agents/qa-engineer.md) | Testing, quality gates, peer validation |
| [**UI/UX Designer**](plugins/agentic-dev-team/agents/ui-ux-designer.md) | Interface design, accessibility compliance |
| [**Architect**](plugins/agentic-dev-team/agents/architect.md) | System design, tech decisions, scalability |
| [**Product Manager**](plugins/agentic-dev-team/agents/product-manager.md) | Requirements, prioritization, stakeholder alignment |
| [**Technical Writer**](plugins/agentic-dev-team/agents/tech-writer.md) | Documentation, terminology consistency |
| [**Security Engineer**](plugins/agentic-dev-team/agents/security-engineer.md) | Security analysis, threat modeling |
| [**DevOps/SRE Engineer**](plugins/agentic-dev-team/agents/devops-sre-engineer.md) | Pipeline, deployment, reliability |

## Review Agents

19 specialized review agents run as sub-agents during Phase 3 checkpoints and full `/code-review` runs. The **three-stage review pattern** runs spec-compliance first (does code match spec?), then quality agents (is code good?), then browser verification for UI changes. Heavyweight agents (security, domain, architecture) load detection knowledge from `knowledge/` files at runtime for progressive disclosure.

| Agent | Focus | Model |
| --- | --- | --- |
| [`spec-compliance-review`](plugins/agentic-dev-team/agents/spec-compliance-review.md) | **First gate** — spec-to-code matching before quality review | sonnet |
| [`test-review`](plugins/agentic-dev-team/agents/test-review.md) | Coverage gaps, assertion quality, test hygiene (QA Engineer delegates here) | sonnet |
| [`security-review`](plugins/agentic-dev-team/agents/security-review.md) | Injection, auth/authz, data exposure | opus |
| [`domain-review`](plugins/agentic-dev-team/agents/domain-review.md) | Abstraction leaks, boundary violations | opus |
| [`arch-review`](plugins/agentic-dev-team/agents/arch-review.md) | ADR compliance, layer violations, dependency direction | opus |
| [`structure-review`](plugins/agentic-dev-team/agents/structure-review.md) | SRP, DRY, coupling, organization | sonnet |
| [`complexity-review`](plugins/agentic-dev-team/agents/complexity-review.md) | Function size, cyclomatic complexity, nesting | haiku |
| [`naming-review`](plugins/agentic-dev-team/agents/naming-review.md) | Intent-revealing names, magic values | haiku |
| [`js-fp-review`](plugins/agentic-dev-team/agents/js-fp-review.md) | Array mutations, impure patterns | sonnet |
| [`concurrency-review`](plugins/agentic-dev-team/agents/concurrency-review.md) | Race conditions, async pitfalls | sonnet |
| [`a11y-review`](plugins/agentic-dev-team/agents/a11y-review.md) | WCAG 2.1 AA, ARIA, keyboard nav | sonnet |
| [`performance-review`](plugins/agentic-dev-team/agents/performance-review.md) | Resource leaks, N+1 queries | haiku |
| [`token-efficiency-review`](plugins/agentic-dev-team/agents/token-efficiency-review.md) | File size, LLM anti-patterns | haiku |
| [`claude-setup-review`](plugins/agentic-dev-team/agents/claude-setup-review.md) | CLAUDE.md completeness and accuracy | haiku |
| [`doc-review`](plugins/agentic-dev-team/agents/doc-review.md) | README accuracy, API doc alignment, comment drift | sonnet |
| [`svelte-review`](plugins/agentic-dev-team/agents/svelte-review.md) | Svelte reactivity, closure state leaks | sonnet |
| [`progress-guardian`](plugins/agentic-dev-team/agents/progress-guardian.md) | Plan adherence, commit discipline, scope creep | sonnet |
| [`refactoring-review`](plugins/agentic-dev-team/agents/refactor-scan.md) | Post-GREEN refactoring opportunities | sonnet |
| [`data-flow-tracer`](plugins/agentic-dev-team/agents/use-case-data-patterns.md) | Data flow tracing through architecture layers (analysis-only) | sonnet |

## Slash Commands

| Command | What It Does |
| --- | --- |
| [`/code-review`](plugins/agentic-dev-team/commands/code-review.md) | Run all review agents with pre-flight gates, scope validation, and MCP probing |
| [`/review`](plugins/agentic-dev-team/commands/review.md) | Alias for `/code-review` |
| [`/review-agent <name>`](plugins/agentic-dev-team/commands/review-agent.md) | Run a single review agent |
| [`/agent-audit`](plugins/agentic-dev-team/commands/agent-audit.md) | Audit agents and commands for structural compliance |
| [`/agent-eval`](plugins/agentic-dev-team/commands/agent-eval.md) | Run eval fixtures and grade review agent accuracy |
| [`/agent-add`](plugins/agentic-dev-team/commands/agent-add.md) | Scaffold a new review agent |
| [`/agent-remove`](plugins/agentic-dev-team/commands/agent-remove.md) | Remove an agent and all registry entries |
| [`/add-plugin`](plugins/agentic-dev-team/commands/add-plugin.md) | Install a plugin and register it in settings.json |
| [`/apply-fixes`](plugins/agentic-dev-team/commands/apply-fixes.md) | Apply correction prompts from `/code-review` |
| [`/review-summary`](plugins/agentic-dev-team/commands/review-summary.md) | Generate compact session summary |
| [`/semgrep-analyze`](plugins/agentic-dev-team/commands/semgrep-analyze.md) | Run Semgrep SAST |
| [`/domain-analysis`](plugins/agentic-dev-team/commands/domain-analysis.md) | Assess DDD health: bounded contexts, context map, friction report |
| [`/mutation-testing`](plugins/agentic-dev-team/commands/mutation-testing.md) | Run mutation testing tool and triage surviving mutants |
| [`/browse`](plugins/agentic-dev-team/commands/browse.md) | Browser-based QA: navigate, screenshot, click, fill forms via Playwright |
| [`/careful`](plugins/agentic-dev-team/commands/careful.md) | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE) |
| [`/freeze <glob>`](plugins/agentic-dev-team/commands/freeze.md) | Scope-lock editing to a glob pattern |
| [`/unfreeze`](plugins/agentic-dev-team/commands/unfreeze.md) | Lift the scope lock set by `/freeze` |
| [`/guard <glob>`](plugins/agentic-dev-team/commands/guard.md) | Combined `/careful` + `/freeze` for production-critical sessions |
| [`/upgrade`](plugins/agentic-dev-team/commands/upgrade.md) | Check for and apply plugin updates from within a session |
| [`/help`](plugins/agentic-dev-team/commands/help.md) | List all available slash commands with descriptions |
| [`/plan`](plugins/agentic-dev-team/commands/plan.md) | Create a structured implementation plan with TDD steps |
| [`/build`](plugins/agentic-dev-team/commands/build.md) | Execute an approved plan with TDD, inline reviews, and verification evidence |
| [`/pr`](plugins/agentic-dev-team/commands/pr.md) | Run quality gates and create a pull request |
| [`/setup`](plugins/agentic-dev-team/commands/setup.md) | Detect tech stack, generate project-level config and hooks |
| [`/continue`](plugins/agentic-dev-team/commands/continue.md) | Resume work from a prior session using phase progress files |
| [`/specs`](plugins/agentic-dev-team/commands/specs.md) | Collaborative specification workflow |
| [`/triage`](plugins/agentic-dev-team/commands/triage.md) | Investigate a bug and file a GitHub issue with TDD fix plan |
| [`/issues-from-plan`](plugins/agentic-dev-team/commands/issues-from-plan.md) | Break a plan into independently-grabbable GitHub issues |
| [`/harness-audit`](plugins/agentic-dev-team/commands/harness-audit.md) | Analyze harness effectiveness and flag stale components |
| [`/competitive-analysis`](plugins/agentic-dev-team/commands/competitive-analysis.md) | Compare plugin against others to find gaps |

## Skills

Reusable knowledge modules that any agent can draw on. Skills define patterns, procedures, and guidelines — not personas.

| Skill | Purpose |
| --- | --- |
| [Context Loading Protocol](plugins/agentic-dev-team/skills/context-loading-protocol.md) | Decide what to load and when; stay below 40% context ceiling |
| [Context Summarization](plugins/agentic-dev-team/skills/context-summarization.md) | Compress conversation history to structured summaries in `memory/` |
| [Feedback & Learning](plugins/agentic-dev-team/skills/feedback-learning.md) | Process `amend`/`learn`/`remember`/`forget` trigger keywords |
| [Human Oversight Protocol](plugins/agentic-dev-team/skills/human-oversight-protocol.md) | Approval gates, intervention commands, transparency requirements |
| [Performance Metrics](plugins/agentic-dev-team/skills/performance-metrics.md) | Log task completion data to `metrics/` in JSONL format |
| [Quality Gate Pipeline](plugins/agentic-dev-team/skills/quality-gate-pipeline.md) | Self-validation, verification evidence, review-correction loops |
| [Governance & Compliance](plugins/agentic-dev-team/skills/governance-compliance.md) | Audit logging, quality gates, ethics procedures |
| [Agent & Skill Authoring](plugins/agentic-dev-team/skills/agent-skill-authoring.md) | Create and maintain agent and skill files |
| [Specs](plugins/agentic-dev-team/skills/specs.md) | Collaborative spec workflow: Intent, BDD, Architecture, Acceptance Criteria |
| [API Design](plugins/agentic-dev-team/skills/api-design.md) | Contract-first API design for stable, evolvable interfaces |
| [Hexagonal Architecture](plugins/agentic-dev-team/skills/hexagonal-architecture.md) | Ports and adapters to separate business logic from infrastructure |
| [Domain-Driven Design](plugins/agentic-dev-team/skills/domain-driven-design.md) | Bounded contexts, aggregates, context mapping |
| [Domain Analysis](plugins/agentic-dev-team/skills/domain-analysis.md) | Assess existing system DDD health |
| [Threat Modeling](plugins/agentic-dev-team/skills/threat-modeling.md) | Structured STRIDE security analysis |
| [Legacy Code](plugins/agentic-dev-team/skills/legacy-code.md) | Characterization tests and dependency-breaking before behavioral changes |
| [Test-Driven Development](plugins/agentic-dev-team/skills/test-driven-development.md) | RED-GREEN-REFACTOR with hard gates |
| [Mutation Testing](plugins/agentic-dev-team/skills/mutation-testing.md) | Run Stryker/pitest/mutmut and triage surviving mutants |
| [Systematic Debugging](plugins/agentic-dev-team/skills/systematic-debugging.md) | Structured root cause analysis |
| [Browser Testing](plugins/agentic-dev-team/skills/browser-testing.md) | Playwright-based visual QA |
| [Test Design Reviewer](plugins/agentic-dev-team/skills/test-design-reviewer.md) | Evaluate test quality and design |
| [CI Debugging](plugins/agentic-dev-team/skills/ci-debugging.md) | Diagnose CI pipeline failures |
| [Design Doc](plugins/agentic-dev-team/skills/design-doc.md) | Problem statement, approach, alternatives, scope boundaries |
| [Design Interrogation](plugins/agentic-dev-team/skills/design-interrogation.md) | Stress-test designs and surface unresolved decisions |
| [Design It Twice](plugins/agentic-dev-team/skills/design-it-twice.md) | Generate parallel alternative interfaces via sub-agents |
| [Branch Workflow](plugins/agentic-dev-team/skills/branch-workflow.md) | PR creation, merge strategy, branch cleanup |
| [Competitive Analysis](plugins/agentic-dev-team/skills/competitive-analysis.md) | Compare against external tools to find gaps and weaknesses |
| [JS Project Init](plugins/agentic-dev-team/skills/js-project-init/SKILL.md) | Scaffold a new JS project with ESM, vitest, eslint, prettier |

## Repository Structure

```text
.claude-plugin/marketplace.json     # Marketplace catalog
plugins/agentic-dev-team/           # Plugin source (ships to users)
├── .claude-plugin/plugin.json      # Plugin manifest + version
├── agents/                         # Team agents (12) + review agents (19)
├── commands/                       # Slash commands
├── skills/                         # Reusable knowledge modules (26 skills)
├── hooks/                          # PreToolUse guards + PostToolUse advisory hooks
├── knowledge/                      # Progressive disclosure reference files
├── templates/                      # Language-specific agent templates
├── settings.json                   # Hook registrations
├── install.sh                      # Prerequisite check
└── CLAUDE.md                       # Orchestration pipeline config (auto-loaded)

docs/                               # Dev documentation (not shipped)
plans/                              # Implementation plans (not shipped)
evals/                              # Agent eval fixtures (not shipped)
reports/                            # Review reports (not shipped)
```

---

## Local Development

### Testing locally

Install the plugin from the local path into a test project:

```bash
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-dev-team
```

### Testing agents and hooks

**Eval suite** — run against a single agent or the full set:

```
/agent-eval
/agent-eval plugins/agentic-dev-team/agents/naming-review.md
```

**Structural compliance** — verify all agents and commands:

```
/agent-audit
```

### Hook paths

When running Claude Code in this repo, hooks are loaded from `hooks/` at the project root via `.claude/settings.json`. The hook path references in `settings.json` match the plugin structure (`hooks/X.sh`, not `.claude/hooks/X.sh`).

### Adding an agent or skill

```
/agent-add <description or URL to a coding standard>
```

This scaffolds the agent file, adds it to the registry in `CLAUDE.md`, and creates eval fixtures. Run `/agent-audit` and `/agent-eval` after to verify compliance.

### Documentation

| Guide | Description |
| --- | --- |
| [Getting Started](GETTING-STARTED.md) | Hands-on tutorial: invoke agents, skills, and common workflows |
| [Architecture](docs/architecture.md) | Context management, quality assurance, governance, multi-LLM routing |
| [Agents](docs/agent_info.md) | Agent roster, persona template, adding/removing/customizing agents |
| [Skills & Commands](docs/skills.md) | Skills catalog, slash commands catalog |
| [Eval System](docs/eval-system.md) | How review agent accuracy is measured and graded |
