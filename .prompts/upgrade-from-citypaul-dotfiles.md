# Upgrade Suggestions from citypaul/.dotfiles

Source: https://github.com/citypaul/.dotfiles/tree/main/claude/.claude

Analysis of patterns and ideas worth adopting into the agentic-dev-team plugin. Each suggestion is categorized by effort and value.

**Design constraints:**
- All suggestions must be either language-agnostic or conditionally activated based on detected project language/stack. The `/setup` command (item #1) performs stack detection and gates language-specific features accordingly.
- **JS/TS projects:** Always enforce ES modules (`"type": "module"` in package.json, `import`/`export` only — no `require`/`module.exports`) and functional patterns (immutability, pure functions, composition, array methods over loops). When a JS project is detected without TypeScript, `/setup` must ask whether to add TypeScript. If yes, scaffold `tsconfig.json` with strict mode and activate the `ts-enforcer` template.

---

## High Value, Low Effort

### 1. Add a `/setup` command (project onboarding)

**What they have:** A `/setup` command that detects a project's tech stack and auto-generates project-level CLAUDE.md, hooks, commands, and a PR review agent in one shot.

**Why it matters:** New users installing the plugin have no project-level configuration. A `/setup` command would bootstrap everything — detect the tech stack (TypeScript, Python, Go, etc.), generate appropriate PostToolUse hooks (prettier, eslint, formatters), and create a project-tailored CLAUDE.md.

**Action:** Create `commands/setup.md` that:
- Detects package.json, pyproject.toml, go.mod, Cargo.toml, Gemfile, pom.xml, build.gradle, *.csproj, *.sln, angular.json, etc.
- Records detected stack in `.claude/project-stack.json` (used by other commands/agents to gate language-specific behavior)
- **JS-specific flow:**
  - If `package.json` exists but no `tsconfig.json`, ask the user: "This is a JavaScript project. Would you like to add TypeScript?" If yes, scaffold `tsconfig.json` (strict mode) and activate `ts-enforcer`
  - Enforce ES modules: verify `"type": "module"` in package.json, flag any `require()`/`module.exports` usage
  - Always activate the `functional-patterns` template for JS/TS projects
- Generates project-level `.claude/CLAUDE.md` with discovered conventions
- Generates PostToolUse hooks for the detected formatter/linter (see #4)
- Optionally scaffolds language-specific review agents only when that stack is detected
- Generates a project-specific `/pr` command
- Reports what was created

### 2. Add a `/continue` command (session resumption)

**What they have:** A `/continue` command that reads plan files and progress state to resume work after context resets or new sessions.

**Why it matters:** We already have phase transition files in `memory/`, but no explicit command for users to say "pick up where I left off." This would complement our Context Loading Protocol.

**Action:** Create `commands/continue.md` that:
- Reads `memory/` for in-progress phase files
- Reads `plans/` for active plans
- Summarizes current state and next steps
- Resumes execution from the last checkpoint

### 3. Add a `/plan` command (structured planning)

**What they have:** A `/plan` command that creates structured plan files with goal, acceptance criteria, incremental steps (RED/GREEN/REFACTOR per step), and a pre-PR quality gate.

**Why it matters:** Our orchestrator does planning in Phase 2, but there's no user-invocable command to create a standalone plan. This is especially useful for smaller tasks that don't need the full three-phase orchestration.

**Action:** Create `commands/plan.md` that:
- Creates a plan file in `plans/` (or `docs/specs/`)
- Uses the structure: Goal, Acceptance Criteria, Steps (with TDD phases), Pre-PR Quality Gate
- Integrates with the progress-guardian pattern (see below)

### 4. PostToolUse hook for auto-formatting

**What they have:** A PostToolUse hook that runs prettier + eslint on every Write/Edit of .ts/.tsx files.

**Why it matters:** We have a PreToolUse guard for sensitive paths, but no PostToolUse hook for formatting. This prevents style nits from cluttering reviews and keeps code consistent without manual intervention.

**Action:** Create `hooks/post-format.sh` — a language-aware formatting hook dispatched by `/setup` based on detected stack. The hook script should detect the file extension and route to the correct formatter:

| Stack detected | Extensions | Formatter command |
|----------------|-----------|-------------------|
| Node/TypeScript | `.ts`, `.tsx`, `.js`, `.jsx` | `npx prettier --write "$FILE" && npx eslint --fix "$FILE"` |
| Python | `.py` | `ruff format "$FILE" && ruff check --fix "$FILE"` (or `black` + `flake8`) |
| Go | `.go` | `gofmt -w "$FILE"` |
| Rust | `.rs` | `rustfmt "$FILE"` |
| Ruby | `.rb` | `bundle exec rubocop -A "$FILE"` |
| Java/Kotlin | `.java`, `.kt` | `google-java-format -i "$FILE"` / `ktlint -F "$FILE"` |
| C# | `.cs` | `dotnet format --include "$FILE"` |
| Angular/TypeScript | `.ts`, `.html` | `npx prettier --write "$FILE" && npx ng lint --fix --files "$FILE"` |

The `/setup` command generates the hook with only the branches relevant to the detected stack. Example settings.json output for a TypeScript project:
```json
{
  "PostToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "FILE=$(jq -r '.tool_input.file_path // empty'); case \"$FILE\" in *.ts|*.tsx|*.js|*.jsx) npx prettier --write \"$FILE\" 2>/dev/null && npx eslint --fix \"$FILE\" 2>/dev/null;; esac; exit 0"
    }]
  }]
}
```

---

## High Value, Medium Effort

### 5. Add a `progress-guardian` agent

**What they have:** An agent that enforces plan discipline — tracks which step you're on, requires commit approval before proceeding, gates plan changes through human approval, and runs an end-of-feature quality gate.

**Why it matters:** Our orchestrator manages phases but doesn't have a dedicated "are we still on track?" mechanism. A progress-guardian would prevent scope creep and ensure each increment leaves the codebase in a working state.

**Action:** Create `agents/progress-guardian.md` as a review agent that:
- Reads the active plan file
- Tracks completed vs remaining steps
- Requires commit approval (integrates with human oversight)
- Enforces the pre-PR quality gate before `/pr`

### 6. Add a `learn` agent (institutional knowledge capture)

**What they have:** An agent that captures gotchas, patterns, and decisions discovered during development and proposes additions to CLAUDE.md or relevant documentation.

**Why it matters:** We have the feedback-learning skill, but it's passive (triggered by keywords). A dedicated agent that proactively asks "what did we learn?" after completing features would build institutional knowledge faster. This directly feeds our `memory/` system.

**Action:** Create `agents/learn.md` that:
- Triggers after feature completion or complex bug fixes
- Asks: "What do I wish I'd known at the start?"
- Classifies learnings: gotcha, pattern, anti-pattern, decision, edge case
- Proposes memory entries or CLAUDE.md updates
- Integrates with the feedback-learning skill

### 7. Add a `refactor-scan` agent

**What they have:** An agent that assesses refactoring opportunities after tests pass (TDD's third step). Distinguishes semantic duplication (real DRY violations) from structural similarity (leave alone).

**Why it matters:** Our structure-review agent checks SRP/DRY/coupling, but doesn't specifically tie into the TDD cycle's refactor phase. A refactor-scan agent would run after GREEN and provide actionable, prioritized refactoring suggestions.

**Action:** Create `agents/refactor-scan.md` that:
- Runs after tests pass (invoked by orchestrator or manually)
- Classifies: Critical (fix now), High (this session), Nice (later), Skip (already clean)
- Applies the semantic vs structural duplication test
- Reports in structured format with a recommended action plan

### 8. Add a CI debugging skill

**What they have:** A systematic CI/CD failure diagnosis skill with hypothesis-first approach, environment delta analysis, and anti-patterns (no blind retries).

**Why it matters:** CI failures are a common pain point. We have a devops-sre-engineer agent but no specific skill for diagnosing CI failures methodically. This would prevent the common anti-pattern of "just re-run it."

**Action:** Create `skills/ci-debugging.md` covering:
- Hypothesis-first diagnosis
- Environment delta analysis — language-agnostic checklist:
  - Runtime version (Node, Python, Go, JDK, Ruby, etc.)
  - OS and architecture differences
  - Dependency resolution (lockfile drift, registry differences)
  - Environment variables and secrets
  - Parallelism and test isolation
  - Memory/CPU constraints
  - Network and filesystem differences
- Local reproduction steps
- Anti-patterns: blind retries, adding retries to "flaky" tests, speculative fix pushes
- Integration with devops-sre-engineer agent

### 9. Add a `test-design-reviewer` skill

**What they have:** A skill that evaluates test quality using Dave Farley's 8 properties (Understandable, Maintainable, Repeatable, Atomic, Necessary, Granular, Fast, First) with a weighted "Farley Score."

**Why it matters:** Our test-review agent checks coverage gaps and assertion quality, but doesn't have a quantitative scoring framework. The Farley Score would give teams a concrete metric to track test quality improvement over time.

**Action:** Create `skills/test-design-reviewer.md` or integrate into the existing test-review agent:
- 8-property scoring (1-10 each)
- Weighted formula for composite score
- Score interpretation ranges (Exemplary 9.0+ to Critical <3.0)
- Structured output with per-property analysis
- Attribution to Andrea Laforgia / Dave Farley

---

## Medium Value, Medium Effort

### 10. Add a `/pr` command with quality gates

**What they have:** A `/pr` command that runs a full quality gate before creating a PR: runs tests, typecheck, lint, mutation testing assessment, refactoring scan, then creates the PR with a structured summary.

**Why it matters:** We have the branch-workflow skill but no user-invocable `/pr` command. Users currently create PRs manually or rely on the orchestrator. A standalone `/pr` command would enforce quality gates consistently.

**Action:** Create `commands/pr.md` that:
- Runs pre-PR quality gate (tests, typecheck, lint)
- Optionally runs mutation testing
- Runs `/code-review --changed`
- Creates PR via `gh pr create` with structured summary

### 11. CLAUDE.md architecture pattern (lean root, skills on-demand)

**What they have:** A deliberately lean CLAUDE.md (~100 lines) that contains only core philosophy and quick reference, with all detailed patterns loaded on-demand via skills. They explicitly track version history (v1: monolithic 1,818 lines → v2: modular 3,000+ lines → v3: lean 100 lines).

**Why it matters:** Our CLAUDE.md is already reasonably lean (~800 tokens) with registries moved to knowledge files, but their explicit "architecture" section documenting this pattern is worth adopting. It makes the design intent clear to contributors.

**Action:** Add an architecture note to our CLAUDE.md header explaining the layered loading strategy:
- CLAUDE.md: core philosophy + quick reference (always loaded)
- Skills: detailed patterns (loaded on-demand)
- Knowledge: reference data (loaded on-demand by agents)
- Agents: behavioral specs (loaded per-phase)

### 12. Output guardrails section

**What they have:** Explicit rules in CLAUDE.md:
- "Write to files, not chat" — artifacts go to files, not just inline
- "Plan-only mode" — when asked for a plan, produce ONLY the plan (no implementation)
- "Incremental output" — produce a first draft within 3-4 tool calls, refine iteratively

**Why it matters:** These are simple but high-impact guardrails that prevent common failure modes. Our orchestrator handles these implicitly, but making them explicit in CLAUDE.md would benefit all agents.

**Action:** Add an "Output Guardrails" section to CLAUDE.md with these three rules.

### 13. ADR (Architecture Decision Record) agent

**What they have:** An agent that creates and manages ADRs with a clear decision framework for when to create one vs not. Includes format template, anti-patterns, and integration points.

**Why it matters:** Our architect agent handles architectural decisions, but we don't have a dedicated ADR workflow. For projects that use ADRs, this would standardize the format and prevent trivial decisions from getting ADR'd.

**Action:** Create `agents/adr.md` or add ADR management as a capability of the architect agent. Include the decision framework (DO create for: technology choices, architectural patterns, breaking changes; DON'T create for: bug fixes, style choices, obvious best practices).

### 14. `use-case-data-patterns` agent

**What they have:** An agent that traces a use case through all architecture layers, mapping data access patterns, caching strategies, external integrations, and identifying gaps.

**Why it matters:** This is a specialized exploration agent that would complement our domain-review and arch-review agents. Useful for understanding how data flows through a system before making changes.

**Action:** Create `agents/use-case-data-patterns.md` that:
- Parses a use case description
- Traces through architecture layers (API → service → repository → database)
- Maps data access patterns (queries, caching, external calls)
- Identifies gaps and missing patterns
- Reports with relevant code locations

---

## Lower Priority (Nice to Have)

### 15. `docs-guardian` agent

We already have `doc-review` which covers similar ground (documentation accuracy, staleness, API doc alignment). Their version is more opinionated about documentation quality principles (7 pillars, progressive disclosure, etc.). Consider enriching `doc-review` with their quality framework.

### 16. Browser automation preference

They prefer `agent-browser` for web automation with a documented core workflow (open → snapshot → interact → re-snapshot). Low effort to add as a note if/when browser automation becomes relevant.

### 17. Plugins worth evaluating

Their settings.json enables several plugins:
- `feature-dev@claude-code-plugins` — guided feature development
- `frontend-design@claude-code-plugins` — frontend design generation
- `hookify@claude-code-plugins` — hook management
- `learning-output-style@claude-code-plugins` — output style learning
- `security-guidance@claude-code-plugins` — security guidance

Evaluate these for compatibility with our agent pipeline.

---

## Summary: Recommended Implementation Order

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 1 | `/setup` command (#1) | Low | High — reduces onboarding friction |
| 2 | PostToolUse formatting hook (#4) | Low | High — eliminates style noise |
| 3 | Output guardrails in CLAUDE.md (#12) | Low | Medium — prevents common failures |
| 4 | `/continue` command (#2) | Low | High — enables session continuity |
| 5 | `/plan` command (#3) | Low | Medium — structured lightweight planning |
| 6 | `progress-guardian` agent (#5) | Medium | High — prevents scope creep |
| 7 | CI debugging skill (#8) | Medium | High — systematic failure diagnosis |
| 8 | `learn` agent (#6) | Medium | Medium — institutional knowledge |
| 9 | `refactor-scan` agent (#7) | Medium | Medium — TDD cycle completion |
| 10 | Test design reviewer skill (#9) | Medium | Medium — quantitative test quality |
| 11 | `/pr` command (#10) | Medium | Medium — quality-gated PRs |
| 12 | ADR agent (#13) | Medium | Medium — decision documentation |

## What NOT to Adopt as Always-On

- **TDD guardian as a separate agent:** We already have TDD integrated into the software-engineer agent and the test-driven-development skill. Adding another agent would create overlap.
- **PR reviewer agent:** We already have 16 review agents orchestrated by `/code-review`. Their single PR reviewer is less granular than our approach.
- **Always-think mode:** This is a user preference (`alwaysThinkingEnabled`), not a plugin concern.

## Language-Specific Items to Offer as Optional Agent Templates

These should NOT be bundled as always-on agents. Instead, ship them as templates in `templates/agents/` that `/setup` scaffolds into a project when the matching stack is detected, or that users can add manually via `/agent-add`.

| Template | Activates when | What it does |
|----------|---------------|--------------|
| `ts-enforcer` | `package.json` has `typescript` dep or `tsconfig.json` exists | No `any` types, schema-first at trust boundaries, `type` vs `interface` discipline, strict tsconfig audit |
| `esm-enforcer` | JS/TS project detected (**always-on**) | `"type": "module"` in package.json, `import`/`export` only, no `require()`/`module.exports`, no `__dirname`/`__filename` (use `import.meta`) |
| `functional-patterns` | JS/TS project detected (**always-on**) | Immutability enforcement, pure functions, composition over inheritance, array methods over loops, no nested mutation, early returns over nested conditionals |
| `react-testing` | `react` or `react-dom` in deps | Component testing with Testing Library, anti-patterns (unnecessary `act()`, shallow rendering), hook testing |
| `front-end-testing` | Any frontend framework detected (React, Vue, Svelte, Angular) | Behavior-driven UI testing, browser-mode preference (Vitest/Karma/Playwright), query priority (getByRole first), HTTP interceptors (MSW/HttpClientTestingModule) |
| `twelve-factor-audit` | Service/API project detected (has Dockerfile, server entry point, or cloud config) | Audit all 12 factors with language-appropriate examples |
| `python-quality` | `pyproject.toml` or `requirements.txt` exists | Type hints (mypy/pyright strict), no bare `except`, f-strings over format, dataclasses/Pydantic models |
| `go-quality` | `go.mod` exists | Error handling discipline, no naked returns, interface segregation, struct embedding patterns |
| `csharp-quality` | `.csproj` or `.sln` exists | Nullable reference types enabled, no `dynamic`, async/await discipline, record types for DTOs, dependency injection patterns |
| `angular-testing` | `@angular/core` in deps | TestBed setup, component harnesses, OnPush change detection testing, RxJS marble testing, no direct DOM queries |

The `/setup` command should present detected templates and let the user confirm before scaffolding.
