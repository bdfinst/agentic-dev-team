# Three-Phase Workflow

The orchestrator's phase reference, loaded on demand. `agents/orchestrator.md`
§ Three-Phase Workflow carries the always-on part — the phase list, each phase's
goal and human gate, and the invariants that hold across all three. Everything
below is the detail a session needs *once it is actually running a phase*: the
persona rosters to dispatch, the conditional dispatch rules, the review
checkpoints, and the wave mechanics. Read the section for the phase you are in
via its anchor, not the whole file.

Notes on what `scripts/orchestrator.py` — the `Enforcement: script` deterministic
implementation — actually does, and where it diverges from the policy below, live
in `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md`. They are needed when running or working on that script, not
when following the policy interactively.

Every non-trivial task follows three explicit phases. Each phase runs in minimal context, and a human review gate separates each phase. The output of each phase is a structured progress file written to `.claude/memory/` that onboards the next phase.

## Phase 1: Research

- **Goal**: Understand how the system works, identify all relevant files, locate the problem or feature surface area
- **Agents**: `codebase-recon` (gated on RECON artifact freshness — see Codebase Recon dispatch below), `architect`, `data-flow-tracer` (always dispatched — see the Research persona roster in `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-1-research`), `security-engineer` (conditional — see Security Engineer dispatch), plus the Orchestrator itself and further sub-agents for exploration as needed (context isolation — sub-agents search, read, and return concise findings so the parent context stays clean)
- **Output**: A research progress file with file paths, line numbers, data flows, and key findings
- **Design doc**: For non-trivial features (see Design Doc skill for criteria), produce a design document at `docs/specs/{feature-name}.md` with problem statement, proposed approach, alternatives, key decisions, and scope boundaries. The human approves the design doc as part of the research gate.
- **Human gate**: Human reviews the research findings and design doc before planning begins. Catching a misunderstanding here prevents hundreds of bad lines of code downstream.
- **Context**: Compact after this phase — write progress file, start fresh context for Phase 2

Script behavior and known gaps: `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-1-research`.

### Codebase Recon dispatch

Dispatch `codebase-recon` as a sub-agent **before any other exploration**,
at the start of Research, when no `.claude/memory/recon-<slug>.json`
artifact exists, or the existing one is more than 24 hours old (`<slug>` is
the repo basename) — skip the dispatch (silently) when a fresh artifact is
present. It returns entry points, dependency graph, security surface, and
git history in a structured artifact (`.claude/memory/recon-<slug>.json` /
`.claude/memory/recon-<slug>.md`, checked for freshness against the `.json`
half since that's the machine-readable artifact other agents consume)
intended to onboard the Architect and Security Engineer without those
agents needing to re-read the codebase themselves.

Script behavior and known gaps: `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-1-research`.

### Security Engineer dispatch

Dispatch `security-engineer` during Research when any of these signals is
present: the task touches authentication, authorization, cryptography,
session management, or secrets handling; it introduces a new external
integration or API surface; or the user explicitly asks to "threat model
this", "design this securely", or "what's the attack surface here" (these
three match `agents/security-engineer.md`'s own dispatch description) — or a
recent `/code-review` run's `security-review` produced a `fail` verdict with
high-severity findings on this area (orchestrator-owned: only the
orchestrator sees `/code-review` history). Its `effort: high` cost is only
justified on security-relevant work, so this dispatch stays conditional
rather than unconditional.

Script behavior and known gaps: `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-1-research`.

## Phase 2: Plan

- **Goal**: Specify every change to be made — files, snippets, test strategy, verification steps
- **Agents**: `product-manager`, `architect`, `qa-engineer` (core trio that drafts the plan — always dispatched, see the Plan persona roster in `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-2-plan`), then the `plan-review-*` critics reviewing that draft (below)
- **Input**: Research progress file from Phase 1 + approved design doc (if produced in Phase 1)
- **Output**: An implementation plan with explicit file changes, test expectations, and acceptance criteria
- **Automated plan review**: Before the human gate, dispatch the plan review
  personas in parallel as sub-agents — `plan-review-acceptance`,
  `plan-review-design`, `plan-review-ux`, `plan-review-strategic`,
  `plan-review-parallelization`. Each is a registered agent
  (`agents/plan-review-<name>.md`); dispatch by `subagent_type` like any
  other agent — the harness reads its `model:`/`effort:` frontmatter
  natively, no dispatch-time override needed. The reviewer set scales to
  plan tier and complexity; see the plan skill's
  [Run plan review personas step](../skills/plan/SKILL.md#5-run-plan-review-personas)
  for the tier classification (that table is the single source of truth —
  do not re-duplicate the reviewer set here, it drifts).

  Each returns a `verdict` of `approve` or `needs-revision`. If **any**
  dispatched reviewer returns `needs-revision`, address the blocker issues
  before presenting to the human. Aggregate all findings (including
  warnings from approving reviewers) into the plan review summary.
- **Human gate**: Human reviews the plan and the aggregated review findings. This is the primary review artifact — 200 lines of plan is far more reviewable than 2,000 lines of code. If the plan is wrong, fix it here, not in code.
- **Design intent: no choice made during Implementation is meant to compensate for a weak plan.** A plan carrying an unresolved `needs-revision` verdict (a blocker, or 3+ warnings — 2+ for `plan-review-parallelization` — per `${CLAUDE_PLUGIN_ROOT}/knowledge/plan-review-rubric.md#verdict-rules`) is revised and re-reviewed before the human gate — see the plan skill's [Run plan review personas step](../skills/plan/SKILL.md#5-run-plan-review-personas) for that iteration cap and its escalation path — and never carried silently into Phase 3. Code-First Small Batches (Phase 3's sole cadence, per ADR 0017) is not a substitute for plan quality, it is what a *good* plan gets executed with. When a plan looks weak going into the human gate, the fix is another Phase 2 iteration, never a Phase 3 workaround. See `${CLAUDE_PLUGIN_ROOT}/knowledge/test-cadence-tradeoffs.md#the-decision-rule` for the evidence bar an alternative Phase 3 cadence has to clear before it changes this.
- **Context**: Compact after this phase — write progress file, start fresh context for Phase 3

Script behavior and known gaps: `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-2-plan`.

## Phase 3: Implement

- **Goal**: Execute the plan. Write code, run tests, verify at each step.
- **Agents**: Software Engineer (primary), QA Engineer (validation), others as needed
- **Input**: Plan progress file from Phase 2
- **Subagent dispatch**: Dispatch the `software-engineer` agent by `subagent_type` when dispatching implementation subagents, scoped to a single plan step — the harness reads its `model:`/`effort:` frontmatter natively, no dispatch-time override needed. For parallel implementation of independent units, prefer `isolation: "worktree"` on the Agent tool to give each subagent its own git worktree. Disjoint *final* file sets are not sufficient justification to skip it: two parallel subagents sharing one working directory can still observe each other's mid-edit, intermediate state — a shared production file transiting a broken half-edited form at the exact moment a sibling's own test run reads it — even when neither subagent's final diff ever touches the other's files (#1609). If worktree isolation is skipped for a given dispatch because its per-agent cost (~200-500ms + disk) isn't justified for that unit of work, treat any test failure one parallel subagent reports while siblings are still running as provisional: re-verify it once every parallel subagent in that batch has completed before treating it as a real regression, not a timing artifact. **Never instruct a dispatched parallel worker to dispatch its own review agent.** A subagent that calls the Agent tool itself does not receive that call's completion notification the way the top-level session does — notifications for a subagent's own dispatched children route to the top-level session instead, so a worker that dispatches a review and then stops to wait for it stalls indefinitely (#1881). This applies to any fan-out of independent units, not only the wave mechanism documented in § Wave-aware build dispatch: each parallel worker fixes/implements, tests, commits, and pushes only; review is dispatched once, from the top level, after every worker in the batch has finished — never once per worker. (This is why the Three-stage inline review below is described as something the orchestrator runs after each unit completes, not something a software-engineer subagent runs on itself.)
- **Cadence enforcement**: The Software Engineer follows the single per-behavior cadence for every unit — Code-First Small Batches (IMPLEMENT → TEST → REFACTOR), per `docs/experiments/RECOMMENDATIONS.md` Rec 3. The orchestrator verifies that each unit's output includes the cadence's verification evidence: green full-suite output. Defect fixes are the one exception — they follow `systematic-debugging`'s mandatory Phase 4 gate, which requires a failing test that reproduces the bug before any fix code is written.
- **Output**: Working code that passes all tests, acceptance criteria, and code review
- **Three-stage inline review**: After each discrete unit of work completes, run the deterministic static self-heal pass to pass-or-cap (`skills/build/references/static-self-heal.md`), then spec-compliance, then quality, then browser verification for UI changes:
  1. **Stage 1 — Spec compliance**: Dispatch the `spec-reviewer` agent by `subagent_type`. Does the code match the spec? If fail → fix before proceeding to Stage 2. (This is a distinct, narrower per-step check than the `spec-compliance-review` agent used as the first gate before the final `/code-review` — see § Inline review checkpoint below and `${CLAUDE_PLUGIN_ROOT}/knowledge/agent-registry.md#review-agents` for how the two differ.)
  2. **Stage 2 — Code quality**: Dispatch the `quality-reviewer` agent by `subagent_type` to run the standard **Inline Review Checkpoint** (see below). Is the code high quality?
  3. **Stage 3 — Browser verification (UI changes only)**: If the plan step involves UI components, run `/browse` in automated smoke test mode against the running dev server. Capture screenshots, verify rendering, and check basic interaction. If the dev server is not running, skip with a warning (do not fail). Timeout: 30 seconds. Failures enter the review loop (max 2 iterations). This stage is skipped for non-UI changes.
- **Final verify**: After all units complete and tests pass, run `/code-review` on all modified files:
  - `fail` → Software Engineer addresses critical issues, re-run review
  - `warn` → include findings in human gate summary
  - `pass` → proceed to doc review
- **Doc review**: Before the human gate, invoke `dev-team:tech-writer` to review all documentation affected by the changes:
  - Any behavioral or architectural change → check `docs/agent-architecture.md`, `README.md`
  - Any configuration or tooling change → check `docs/agent-architecture.md` (Governance section)
  - Any agent or skill change → check `CLAUDE.md`, `docs/agent_info.md`, `docs/team-structure.md`; regenerate `docs/skills.md` (generated — `hooks/lib/build_skills_index.py`)
  - Tech-writer updates outdated sections and confirms all docs reflect current behavior before proceeding
- **Human gate**: Human reviews the final output. If the plan was good, implementation review is lightweight.
- **Context**: If implementation is large, compact mid-phase — update the plan progress file with completed steps and continue in a fresh context

Script behavior and known gaps: `${CLAUDE_PLUGIN_ROOT}/knowledge/orchestrator-script-implementation.md#phase-3-implement`.

### Wave-aware build dispatch

During `/build`, the orchestrator executes the plan **wave by wave** (the plan's `## Parallelization` schedule from `scripts/plan_waves.py`):

1. **Resolve** the wave schedule (`build_wave.py`) and the effective concurrency (`build_jobs.py` → `min(--jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)`).
2. **Dispatch** each independent slice in the wave to its own git worktree (`isolation: "worktree"`) up to that concurrency — each runs its full per-behavior cycle (Code-First Small Batches) + inline review in isolation.
3. **Barrier + reconcile** (`build_wave_reconcile.py`): order-independently merge the wave's slice branches, gate on the full suite, and only then start the next wave. A failing slice or a reconcile conflict halts loudly (names the offender, preserves succeeded worktrees, prints the resume command) and starts no next-wave slice.

Effective concurrency 1 (fully-dependent plan, `--jobs 1`, or `DEV_TEAM_MAX_PARALLEL_BUILDS=1`) degrades to sequential single-worktree build with no fan-out or reconcile.

> Read a slice's status during a wave only from its structured result, never from a live transcript read into this orchestrating context — see `docs/agent-architecture.md` → Subagent status checks.

**`worktree.baseRef` prerequisite (issue #553).** Worktree fan-out only works when Claude Code's `worktree.baseRef` setting is `"head"` — otherwise each subagent worktree branches from `origin/<default>` and cannot see the caller's uncommitted-to-remote spec, plan, or prior-wave commits. Users must set this in **`.claude/settings.json`** (project scope) or **`~/.claude/settings.json`** (user scope); plugin-scope `plugins/<name>/settings.json` and project-local `.claude/settings.local.json` are **not** honored by 2.1.198's worktree isolation. `/build`'s Step 4 detect-and-warn surfaces the requirement loudly on every invocation until the user sets it (or opts out with `DEV_TEAM_WORKTREE_BASE_FRESH=1`). Full audit trail: `docs/spikes/worktree-baseref-head-spike.md`.

### Review depth by complexity

Each plan step includes a **Complexity** classification that controls review depth:

| Complexity | Inline review behavior | Granularity |
|------------|----------------------|-------------|
| `trivial` | Skip inline review entirely. The final `/code-review` covers all files. | — |
| `standard` | Run spec-compliance + quality agents relevant to the change type (see table below). | **Batched at the slice boundary** — one pass over the slice's accumulated `standard`/`trivial` changes once all its steps are green, not per step. |
| `complex` | Run spec-compliance + full quality suite including high-effort agents (security-review, domain-review, arch-review). | **Per step** — smaller blast radius per fix. |

If a step has no complexity annotation, default to `standard`.

Each checkpoint that runs records a find/fix/no-op outcome to `.claude/metrics/review-value.jsonl` (#348) so the review overhead is measurable and the tiering can be evidence-based.

### Inline review checkpoint

After each discrete unit of work classified as **standard** or **complex** (a function, a module, a feature slice — as defined in the Phase 2 plan):

**Step 1 — Select agents by what changed:**

| Changed | Agents to run |
|---|---|
| JS/TS functions | complexity-review, naming-review, js-fp-review |
| Test files | test-review |
| API surface / auth | security-review |
| Domain/business logic | domain-review |
| UI components | a11y-review, structure-review, component-architecture-review |
| Agent or command files | eval-compliance-check hook runs automatically; also run /agent-audit |
| Dockerfile or .dockerignore | docker-image-audit skill |
| Documentation files (.md) | doc-review |
| Architecture/dependency changes | arch-review |
| All changes | structure-review as a baseline |
| All changes (before quality review) | spec-compliance-review as first gate |

**Step 2 — Run selected agents in parallel** using the Agent tool by `subagent_type` — the harness reads each agent's `model:`/`effort:` frontmatter natively per `agents/orchestrator.md` § Model/Effort Resolution.

When the selection above would dispatch 5+ agents in one wave, note the coordination-cost signal and consider batching high-overlap lenses per `${CLAUDE_PLUGIN_ROOT}/knowledge/wave-consolidation-guidance.md#when-it-applies` — advisory only; dispatch still proceeds.

**Step 3 — Aggregate findings and apply Review Loop:**

- `pass` / `warn` → log findings in phase output, continue
- `fail` → enter the **Review Loop** below

### Review loop

When any checkpoint agent returns `fail`:

1. Classify issues by actionability (same criteria as `/code-review` step 5):
   - **Actionable**: severity `error` or `warning` with confidence `high` or `medium`
   - **Human-required**: confidence `none` — log and skip, do not attempt auto-fix
2. For actionable issues, apply the minimal fix directly:
   - Apply file-by-file, top-to-bottom by line number
   - Run tests after each batch of fixes — revert and mark as human-required if tests break
3. Re-run only the agents that reported actionable issues.
4. Repeat up to **5 iterations** total (matching `/code-review` loop behavior).
5. **Exit conditions**:
   - Zero actionable issues remain → continue to next plan step
   - Same issues persist after fix attempt → not converging, escalate
   - Iteration limit reached (5) → escalate to human with:
     - The original findings
     - All fix attempts
     - Remaining issues and recommended resolution path
6. `warn` after any iteration is acceptable; document in phase output and continue.

## Phase transitions

1. Complete the current phase's work
2. Write a structured progress file to `.claude/memory/` (see Context Summarization skill)
3. Human reviews and approves before proceeding
4. Start new context window for the next phase
5. Load only the progress file + agents needed for the new phase
