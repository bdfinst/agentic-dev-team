# Agentic Dev Team

A Claude Code plugin that adds a full persona-driven AI development team to any project. The Orchestrator routes tasks to specialized agents, inline review checkpoints catch quality issues during implementation, and skills provide reusable knowledge modules that any agent can draw on.

```mermaid
flowchart TD
    U([User Request]) --> O[Orchestrator]
    O --> R[Research Phase]
    R --> DD[Design Doc\ndocs/specs/]
    DD --> HG1([Human Gate])
    HG1 --> PL[Plan Phase]
    PL --> PR[Plan Reviewer\nprompts/plan-reviewer.md]
    PR --> HG2([Human Gate])
    HG2 --> IM[Implement Phase\nTDD: RED-GREEN-REFACTOR]
    IM --> SC[Stage 1: Spec Compliance\nspec-compliance-review]
    SC -->|fail| IM
    SC -->|pass| QR[Stage 2: Quality Review\nTargeted Review Agents]
    QR -->|fail| RF[Correction Context]
    RF --> IM
    QR -->|pass / warn| VBC[Verification Gate\nFresh test evidence required]
    VBC --> HG3([Human Gate])
    HG3 --> BW[Branch Workflow\nPR + Merge + Cleanup]
    BW --> LL[Learning Loop]
    LL --> O
```

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- `jq` — used by PostToolUse hooks for JSON parsing
  - macOS: `brew install jq`
  - Linux: `apt install jq` or `yum install jq`

**Recommended:**

- [Beads](https://github.com/beads-dev/beads) (`bd`) — git-backed issue tracker designed for AI agents. If `bd` is not installed, agents fall back to `memory/` progress files.

  AI agents start each session with a fresh context window — they don't remember what happened last time. Beads solves this "fresh context" problem by giving agents a structured, queryable task graph they can read at session start instead of reconstructing state from prose summaries.

  How agents use it across the three-phase workflow:

  - **Session start** — Agents run `bd ready --json` to find their next unblocked task
  - **Research** — Discovered problems are filed as Beads issues so they survive context compaction
  - **Plan** — The implementation plan is decomposed into Beads issues with dependency links (`bd dep add`)
  - **Implement** — Agents work one issue per session, mark it `done`, then end the session. The next session picks up the next unblocked item
  - **Crash recovery** — If a session dies mid-task, the issue stays `in-progress` with a checkpoint in the body, so the next session can resume

  Beads and `memory/` progress files are complementary: Beads is the source of truth for *what work remains* (structured task graph), while `memory/` captures *why decisions were made* (prose context).

  ```bash
  npm install -g @beads/bd
  # or: brew install beads
  ```

  Initialize in your project:

  ```bash
  bd init
  git add .beads && git commit -m "Initialize Beads task tracker"
  ```

**Optional:**

- `semgrep` — required only for `/semgrep-analyze`

  ```bash
  pip install semgrep
  # or: brew install semgrep
  ```

### Plugin install (recommended)

Installation is two steps: add the marketplace source, then install the plugin.

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

After installing, run the prerequisite check:

```bash
./install.sh
```

Then add the Beads session-start hook to your global `~/.claude/CLAUDE.md`:

```markdown
## Session Start
At the beginning of every session, run `bd prime` to load Beads context before any other work.
```

### Verify

After starting Claude Code, confirm the system is working:

```
> What agents are available on this team?
```

## How It Works

**Team agents** define roles (persona, behavior, collaboration). **Review agents** check work quality in real time. **Skills** define knowledge (patterns, guidelines, procedures). **Slash commands** invoke agents and skills directly. The **Orchestrator** controls task routing, model selection, and the inline review feedback loop.

### Three-Phase Workflow

Every non-trivial task follows **Research → Plan → Implement** with human review gates between phases:

- **Research** produces a **design document** (`docs/specs/`) with problem statement, alternatives, and scope boundaries
- **Plan** is pre-checked by an automated **plan reviewer** before the human sees it
- **Implement** enforces strict **TDD** (RED-GREEN-REFACTOR with hard gates), uses **worktree isolation** for parallel units, and runs a **two-stage inline review**: spec-compliance first ("does code match spec?"), then quality agents ("is code good?"). All agents must provide **verification evidence** (fresh test output) before claiming completion. After the human gate, a **branch workflow** handles PR creation and merge strategy.

## Team Agents

| Agent | Purpose |
| --- | --- |
| **Orchestrator** | Routes tasks, selects models, coordinates inline review feedback loop |
| **Software Engineer** | Code generation, implementation, applies review corrections |
| **Data Scientist** | ML models, data analysis, statistical validation |
| **QA/SQA Engineer** | Testing, quality gates, peer validation |
| **UI/UX Designer** | Interface design, accessibility compliance |
| **Architect** | System design, tech decisions, scalability |
| **Product Manager** | Requirements, prioritization, stakeholder alignment |
| **Technical Writer** | Documentation, terminology consistency |
| **Security Engineer** | Security analysis, threat modeling |
| **DevOps/SRE Engineer** | Pipeline, deployment, reliability |

## Review Agents

19 specialized review agents run as sub-agents during Phase 3 checkpoints and full `/code-review` runs. The **two-stage review pattern** runs spec-compliance first (does code match spec?), then quality agents (is code good?). Heavyweight agents (security, domain, architecture) load detection knowledge from `knowledge/` files at runtime for progressive disclosure.

| Agent | Focus | Model |
| --- | --- | --- |
| `spec-compliance-review` | **First gate** — spec-to-code matching before quality review | sonnet |
| `test-review` | Coverage gaps, assertion quality, test hygiene (QA Engineer delegates here) | sonnet |
| `security-review` | Injection, auth/authz, data exposure | opus |
| `domain-review` | Abstraction leaks, boundary violations | opus |
| `arch-review` | ADR compliance, layer violations, dependency direction | opus |
| `structure-review` | SRP, DRY, coupling, organization | sonnet |
| `complexity-review` | Function size, cyclomatic complexity, nesting | haiku |
| `naming-review` | Intent-revealing names, magic values | haiku |
| `js-fp-review` | Array mutations, impure patterns | sonnet |
| `concurrency-review` | Race conditions, async pitfalls | sonnet |
| `a11y-review` | WCAG 2.1 AA, ARIA, keyboard nav | sonnet |
| `performance-review` | Resource leaks, N+1 queries | haiku |
| `token-efficiency-review` | File size, LLM anti-patterns | haiku |
| `claude-setup-review` | CLAUDE.md completeness and accuracy | haiku |
| `doc-review` | README accuracy, API doc alignment, comment drift | sonnet |
| `svelte-review` | Svelte reactivity, closure state leaks | sonnet |
| `progress-guardian` | Plan adherence, commit discipline, scope creep | sonnet |
| `refactoring-review` | Post-GREEN refactoring opportunities | sonnet |
| `data-flow-tracer` | Data flow tracing through architecture layers (analysis-only) | sonnet |

## Slash Commands

| Command | What It Does |
| --- | --- |
| `/code-review` | Run all review agents with pre-flight gates, scope validation, and MCP probing |
| `/review` | Alias for `/code-review` |
| `/review-agent <name>` | Run a single review agent |
| `/agent-audit` | Audit agents and commands for structural compliance |
| `/agent-eval` | Run eval fixtures and grade review agent accuracy |
| `/agent-add` | Scaffold a new review agent |
| `/agent-remove` | Remove an agent and all registry entries |
| `/add-plugin` | Install a plugin and register it in settings.json |
| `/apply-fixes` | Apply correction prompts from `/code-review` |
| `/review-summary` | Generate compact session summary |
| `/semgrep-analyze` | Run Semgrep SAST |
| `/domain-analysis` | Assess DDD health: bounded contexts, context map, friction report |

## Plugin Structure

```text
agents/                # Team agents (12) + review agents (19)
skills/                # Reusable knowledge modules (23 skills)
knowledge/             # Progressive disclosure reference files for heavyweight agents
prompts/               # Subagent prompt templates (4) for reproducible dispatch
commands/              # Slash commands (12 user-invocable + agent/skill invokers)
hooks/                 # PreToolUse guard + PostToolUse advisory hooks
evals/                 # Review agent accuracy fixtures
docs/                  # Architecture and reference documentation
docs/specs/            # Design documents produced during Research phase
CLAUDE.md              # Orchestration pipeline configuration (auto-loaded)
REVIEW-CONTEXT.md      # (optional, user-created) Institutional context for reviews
install.sh             # Prerequisite check
```

---

## Local Development

### Setup

Clone the repo, then run `dev-setup.sh` to symlink root-level plugin files into `.claude/` so Claude Code can load them while you develop:

```bash
git clone <repo-url> agentic-dev-team
cd agentic-dev-team
./dev-setup.sh
```

This creates symlinks:

```
.claude/agents   -> ../agents
.claude/skills   -> ../skills
.claude/commands -> ../commands
.claude/hooks    -> ../hooks
```

To remove the symlinks:

```bash
./dev-setup.sh --clean
```

### Testing changes

**Unit testing agents and skills** — run the eval suite against a single agent or the full set:

```
/agent-eval
/agent-eval agents/naming-review.md
```

**Testing a hook change** — hooks fire automatically on every file write/edit while Claude is running in this repo. Trigger one manually to confirm behavior:

```bash
echo '{"tool_input":{"file_path":"test.js"}}' | bash hooks/js-fp-review.sh
```

**Testing in a real project** — the most reliable test is installing the plugin into a scratch project:

```bash
mkdir /tmp/plugin-test && cd /tmp/plugin-test
git init && claude
# inside claude:
# claude plugin marketplace add --scope project /path/to/agentic-dev-team
# claude plugin install --scope project agentic-dev-team
```

**Running the eval audit** — verify all agents and commands meet structural compliance:

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
| [Getting Started](GETTING-STARTED.md) | How to invoke agents, skills, and common workflows |
| [Agents](docs/agent_info.md) | Agent roster, persona template, adding/removing agents |
| [Skills & Commands](docs/skills.md) | Skills catalog, slash commands catalog |
| [Architecture](docs/architecture.md) | Context management, quality assurance, multi-LLM routing |
| [Eval System](docs/eval-system.md) | How review agent accuracy is measured and graded |
| [C-DAD Roadmap](docs/cadad-roadmap.md) | Gaps against the Contract-Driven AI Development white paper |
