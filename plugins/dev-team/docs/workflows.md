# Workflows

This page documents every user-invocable command in the dev-team plugin by capability group.
Commands within each group are split into two tiers:

- **Multi-agent (orchestrators)** — dispatch more than one Agent tool call per invocation, directly
  or via delegation, and may include human gates.
- **Standalone (single-pass)** — single-agent or self-contained; return in one pass without
  inter-phase human gates.

The two multi-phase pipelines with inter-phase gates are [`/ship`](#ship) —
whose full phase table appears at the end of this page — and
[`/test-improve`](#test-improve), whose phase reference lives on its own page,
[test-improve.md](test-improve.md).

**On this page:**

- [Planning and Specification](#planning-and-specification)
- [Implementation](#implementation)
- [Code Review and Quality](#code-review-and-quality)
- [Testing](#testing)
- [Agent and Session Tooling](#agent-and-session-tooling)
- [Session Guards and Scope Control](#session-guards-and-scope-control)
- [Infrastructure and Docker](#infrastructure-and-docker)
- [Multi-Phase Pipeline Reference](#multi-phase-pipeline-reference) — [`/ship`](#ship), [`/test-improve`](#test-improve)
- [Cross-command lifecycle](#cross-command-lifecycle)

---

## Planning and Specification

### Multi-agent

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/specs` | `skills/specs/SKILL.md` | Produce Intent, Architecture Notes, and Acceptance Criteria; gates on human approval before `/plan` | `<task description>` (positional) |
| `/plan` | `skills/plan/SKILL.md` | Decompose a feature into vertical slices with Gherkin scenarios; dispatches plan-review personas (1–5 by tier) plus `progress-guardian` | `<task-description> [--output <path>] [--yes] [--spec-issue <url>]` |
| `/design-doc` | `skills/design-doc/SKILL.md` | Produce a written design document in `docs/specs/` with user approval before planning | `<design topic>` (positional) |
| `/issues-from-plan` | `skills/issues-from-plan/SKILL.md` | Break an approved plan into independently-grabbable GitHub issues | `[plan file path]` |

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/design-interrogation` | `skills/design-interrogation/SKILL.md` | Relentlessly interview the user about a plan or spec to surface hidden assumptions | `<plan or spec text>` (positional) |
| `/design-it-twice` | `skills/design-it-twice/SKILL.md` | Generate multiple radically different interface designs for a module | `<module or interface description>` |
| `/domain-analysis` | `skills/domain-analysis/SKILL.md` | Strategic DDD health assessment of an existing system | `[path]` |
| `/domain-driven-design` | `skills/domain-driven-design/SKILL.md` | Model software around the business domain; bounded contexts, aggregates, value objects | `[path]` |
| `/hexagonal-architecture` | `skills/hexagonal-architecture/SKILL.md` | Design with ports and adapters to separate business logic from infrastructure | `[path]` |
| `/api-design` | `skills/api-design/SKILL.md` | Contract-first API design for stable, evolvable interfaces | `<endpoint or interface description>` |
| `/ubiquitous-language` | `skills/ubiquitous-language/SKILL.md` | Build or refresh the project's ubiquitous language glossary | `[path-to-source-root]` |
| `/adr-tools` | `skills/adr-tools/SKILL.md` | Create and manage Architecture Decision Records using the npryce adr-tools CLI | `<new <title> \| list \| generate>` |
| `/mermaid-diagramming` | `skills/mermaid-diagramming/SKILL.md` | Create Mermaid diagrams using the project's blue-gray theme | `<diagram description>` |

---

## Implementation

### Multi-agent

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/build` | `skills/build/SKILL.md` | Execute an approved plan in small per-behavior batches (Code-First Small Batches) with inline review checkpoints and verification evidence | `[--plan <path>] [--yes]` |
| `/setup` | `skills/setup/SKILL.md` | Provision a repo end to end: install prerequisites, generate project config, activate agent templates | `[--yes] [--dry-run]` |
| `/project-init` | `skills/project-init/SKILL.md` | Detect the stack, inventory tools, install only what's missing; offers opt-in graph-tools | `[--yes]` |
| `/autoship` | `skills/autoship/SKILL.md` | Orchestrate a bounded round of automated issue processing: reclaim orphaned in-progress issues, discover `autoship:ready` issues, and invoke `/ship` for each until a cost or count cap is hit | `--max-issues N --max-cost-usd N [--dry-run] [--label LABEL]` |

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/triage` | `skills/triage/SKILL.md` | Investigate a bug and write a triage record to `.dev-team-reports/triage/<slug>.md` with a TDD fix plan | `<bug description or error message> [--pdf]` |
| `/apply-fixes` | `skills/apply-fixes/SKILL.md` | Apply correction prompts from `/code-review` output | `<corrections-dir> [--dry] [--skip-tests] [--skip-build] [--skip-lint]` |
| `/legacy-code` | `skills/legacy-code/SKILL.md` | Safely modify code that lacks tests — apply characterization tests first | `[path]` |
| `/branch-workflow` | `skills/branch-workflow/SKILL.md` | Clean branch completion: PR creation, merge strategy, and cleanup | `[--base <branch>] [--draft]` |
| `/systematic-debugging` | `skills/systematic-debugging/SKILL.md` | Four-phase protocol (reproduce, investigate, root-cause, fix) to prevent guess-and-fix thrashing | `<error or symptom description>` |
| `/ci-debugging` | `skills/ci-debugging/SKILL.md` | Systematic CI/CD failure diagnosis with hypothesis-first approach and environment delta analysis | `[--url <ci-run-url>] [--log <path>]` |
| `/continue` | `skills/continue/SKILL.md` | Resume work from a prior session using phase progress files | `[--phase <n>]` |

---

## Code Review and Quality

### Multi-agent

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/code-review` | `skills/code-review/SKILL.md` | Run review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations); short-circuits documentation-only changesets | `[--agent <name>] [--since <ref>] [--path <dir>] [--all] [--json] [--internal] [--force --reason "<text>"] [--static-analysis\|--no-static-analysis] [--init-risks] [--background] [--pdf]` |
| `/review` | `skills/review/SKILL.md` | Alias for `/code-review` — same arguments, same behavior | same as `/code-review` |
| `/pr` | `skills/pr/SKILL.md` | Run quality gates and create a pull request (auto-merge enabled by default) | `[--skip-review] [--draft] [--base <branch>]` |
| `/frontend-architecture` | `skills/frontend-architecture/SKILL.md` | Dispatch `component-architecture-review` over frontend component files to catch reuse, prop drilling, and API issues | `[--path <dir>] [--since <ref>] [--all] [--json]` |

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/review-agent` | `skills/review-agent/SKILL.md` | Run a single named review agent (used for inline checkpoints) | `<agent-name> [--since <ref>] [--path <dir>] [--internal]` |
| `/semgrep-analyze` | `skills/semgrep-analyze/SKILL.md` | Run Semgrep SAST and return structured findings | `[path] [--rules <ruleset>]` |
| `/semantic-scan` | `skills/semantic-scan/SKILL.md` | Build computation register and detect semantic duplicates across architectural layers | `[path] [--full] [--no-opus]` |
| `/semantic-duplication-scan` | `skills/semantic-duplication-scan/SKILL.md` | Detect business logic reimplemented in multiple architectural layers | `[path]` |
| `/governance-compliance` | `skills/governance-compliance/SKILL.md` | Audit logging, quality gates, and ethics procedures for the agent team | `[path]` |
| `/threat-modeling` | `skills/threat-modeling/SKILL.md` | Structured STRIDE security analysis for threats, attack surfaces, and mitigations | `[path]` |
| `/quality-gate-pipeline` | `skills/quality-gate-pipeline/SKILL.md` | Unified quality gate for agent output — self-validation, verification evidence, and review-correction loops | `[--strict]` |

---

## Testing

### Multi-agent

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/test-health` | `skills/test-health/SKILL.md` | Project-wide test-strategy audit; runs `/test-design` and `mutation-testing`, folds results in | `[--path <dir>] [--pdf]` |
| `/test-design` | `skills/test-design/SKILL.md` | Deep test-design review: dispatch `test-review` + `test-smell-review`, Farley Score, testability/refactor recommendations | `[--path <dir>] [--since <ref>] [--advise]` |
| `/explore` | `skills/explore/SKILL.md` | Charter-driven exploratory testing (Chaos Specialist mode) with adversarial expansion; auto-triages critical defects | `--charter '<goal>' [target] [--probe-budget <n>] [--invariants '<expr,...>'] [--no-adversarial] [--force]` |
| `/cd-test-architecture` | `skills/cd-test-architecture/SKILL.md` | Evaluate an app's tests and recommend a CD-pipeline-aligned test architecture — fast, deterministic tests that validate behavior in CI without configuring the rest of the system | `[--component <name>] [--ci <path>] [--external-tests <path>] [--stack <id>] [--pdf]` |
| `/quality-targets-converge` | `skills/quality-targets-converge/SKILL.md` | Convergence worker: iterate toward the four quality targets (coverage ≥ 90%, zero surviving mutants, determinism, fastest pre-merge wall-clock), dispatching the smallest action that closes the largest gap each round | `<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--max-iterations <n>] [--refactor-mode <no-refactor\|refactor-allowed>]` |

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/mutation-testing` | `skills/mutation-testing/SKILL.md` | Run a real mutation testing tool and triage survivors | `[--scope <files-or-globs>] [--emit-json <path>] [--workflow-managed-approval]` |
| `/coverage-baseline` | `skills/coverage-baseline/SKILL.md` | Capture line+branch coverage percentages as the pre-improvement baseline | `<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>]` |
| `/coverage-delta` | `skills/coverage-delta/SKILL.md` | Re-run coverage and post delta vs. baseline after each Story closes | `<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--story <id-or-path>] [--story-files <glob-or-comma-list>]` |
| `/farley-score` | `skills/farley-score/SKILL.md` | Evaluate test quality using Dave Farley's 8 properties with a weighted Farley Score | `[path]` |
| `/gherkin-derive` | `skills/gherkin-derive/SKILL.md` | Standalone Gherkin derivation from code — discovers the public surface, recommends BDD binding mode | `<repo-path> [--mode none\|xunit-with-annotations\|bdd-runner] [--repo-slug <slug>]` |
| `/gherkin-public` | `skills/gherkin-public/SKILL.md` | Author Gherkin scenarios for the entire public interface at the observable boundary | `<repo-path> [--repo-slug <slug>] [--parent <issue-url>] [--create-stories]` |
| `/feature-file-validation` | `skills/feature-file-validation/SKILL.md` | Validate Gherkin feature files for structural quality and determinism | `[path]` |
| `/test-audit-disable` | `skills/test-audit-disable/SKILL.md` | Detect tests that cannot fail and disable each with skip+tag; never deletes | `<repo-path> [--repo-slug <slug>] [--dry-run]` |
| `/test-driven-development` | `skills/test-driven-development/SKILL.md` | Advisory reference for Classic RED-GREEN-REFACTOR TDD with hard gates | `[path]` |
| `/exploratory-testing` | `skills/exploratory-testing/SKILL.md` | Charter-driven exploratory testing with structured heuristics and charter-quality evaluation | `--charter '<goal>' [target]` |
| `/browse` | `skills/browse/SKILL.md` | Browser-based QA: navigate, screenshot, click, fill forms via Playwright | `<url> [--screenshot <path>] [--click <selector>] [--fill <selector> <value>] [--wait <ms>] [--viewport <WxH>]` |
| `/benchmark` | `skills/benchmark/SKILL.md` | Capture runtime performance metrics (Core Web Vitals, resource sizes) and compare against baselines | `<url> [--baseline] [--budget] [--trend] [--mobile] [--3g] [--runs <n>]` |
| `/performance-metrics` | `skills/performance-metrics/SKILL.md` | Log task completion data to `.claude/metrics/` — tokens, cost, agents used, rework cycles | `[--task <name>]` |
| `/co-evolution-audit` | `skills/co-evolution-audit/SKILL.md` | Flag production files that churn while their paired test files stay stale (the "Red Queen" gap); ranks stale-coverage pairs from git history | `[--since <date\|N-days>] [--max-commits <N>] [--min-churn <N>] [--max-test-churn <N>]` |
| `/issues-from-assessment` | `skills/issues-from-assessment/SKILL.md` | Convert a `/cd-test-architecture` assessment into a parent + Phase-tagged child issues on the operator's tracker (ADO, GitHub, GitLab, Jira); falls back to local plan files when the CLI is missing | `<assessment-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--refactor-mode <no-refactor\|refactor-allowed>] [--dry-run]` |
| `/stryker-xunit-v2-shim` | `skills/stryker-xunit-v2-shim/SKILL.md` | Build a xunit.v2 Stryker shim so Stryker.NET produces a valid mutation score for a xunit.v3 test project; run it before mutation testing a .NET project on xunit.v3 | `(none)` |

---

## Agent and Session Tooling

### Multi-agent

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/agent-audit` | `skills/agent-audit/SKILL.md` | Audit agents/skills/hooks for structural compliance | `[file-path \| --all] [--fix]` |
| `/agent-eval` | `skills/agent-eval/SKILL.md` | Run eval fixtures, grade accuracy, detect regressions | `[--agent <name>] [--skill <name>] [--fixture <name>] [--trials <n>] [--in-session] [--integration] [--ablation <agent>] [--no-cache] [--verbose]` |
| `/harness-audit` | `skills/harness-audit/SKILL.md` | Analyze harness effectiveness and flag stale components | `[--output <path>]` |
| `/session-review` | `skills/session-review/SKILL.md` | Mine real session transcripts and dispatch `session-analysis` to suggest improvements | `[--cwd <path>] [--transcript <file>] [--out <report>]` |
| `/competitive-analysis` | `skills/competitive-analysis/SKILL.md` | Compare this plugin against external plugins, tools, or feature sets | `<comparison target>` |
| `/context-loading-protocol` | `skills/context-loading-protocol/SKILL.md` | Decide which agents and skills to load for a given task | `[task description]` |
| `/feedback-learning` | `skills/feedback-learning/SKILL.md` | Capture amend/learn/remember/forget keywords and update agent or skill behavior | `<feedback statement>` |
| `/handoff` | `skills/handoff/SKILL.md` | Compress or split off context for another session to pick up | `[--compress \| --split]` |
| `/human-oversight-protocol` | `skills/human-oversight-protocol/SKILL.md` | Clarify approval gates, intervention commands, and transparency requirements | `[context]` |
| `/review-summary` | `skills/review-summary/SKILL.md` | Generate compact session summary for context continuity | `[--from <json-file>]` |
| `/long-eval` | `skills/long-eval/SKILL.md` | Run an eval that outlives a single cloud-session container — agent calibration, prompt sweeps, judge-panel scoring — so it survives container recycles and can be resumed | `[status\|ensure-alive] --module <file> --out <dir>` |
| `/orchestration-benchmark` | `skills/orchestration-benchmark/SKILL.md` | Run the pre-registered solo-vs-coordinated A/B benchmark (three arms over one task matrix) measuring cost, token band, quality, rework, and wall-clock | `[--task-class <trivial\|standard\|complex>] [--runs <n>] [--dry-run]` |

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/harness-e2e-check` | `skills/harness-e2e-check/SKILL.md` | On-demand end-to-end integration check of the harness's own mechanisms | `[--item N] [--output <path>]` |
| `/headless-run` | `skills/headless-run/SKILL.md` | Run a skill/command headlessly in an isolated subprocess | `<prompt-or-slash-command> [--cwd DIR] [--model MODEL] [--timeout SECS]` |
| `/cost-report` | `skills/cost-report/SKILL.md` | Report actual token spend and dollar cost of dispatched work and flag regressions | `[--transcript <path>] [--tolerance <n>]` |
| `/artifact-lifecycle` | `skills/artifact-lifecycle/SKILL.md` | Report on skill and agent usage data from `~/.claude/metrics/artifact-usage.json` | `[--json]` |
| `/telemetry` | `skills/telemetry/SKILL.md` | Manage and report the opt-in usage telemetry beacon | `[on\|off\|status\|report]` |
| `/version` | `skills/version/SKILL.md` | Report the installed plugin version | `(none)` |
| `/upgrade` | `skills/upgrade/SKILL.md` | Check for and apply plugin updates from within a session | `(none)` |
| `/help` | `skills/help/SKILL.md` | List the main dev-team workflows; `--all` shows every user command | `[--all]` |
| `/agent-readiness` | `skills/agent-readiness/SKILL.md` | Score how ready the current repo is for AI-assisted development against the Agent-Readiness Scorecard and emit a tiered report | `[repo-path] [--json <file>] [--markdown <file>]` |
| `/run-report` | `skills/run-report/SKILL.md` | Report one orchestrated run's timeline — per-state dwell time, rejection count, hook denials/bypasses, and cost — joined from the boundary/cost/state event logs | `[--session <id>]` |
| `/report-pdf` | `skills/report-pdf/SKILL.md` | Render a dev-team Markdown report (`.dev-team-reports/` or `reports/`) to a polished, shareable PDF | `<path.md> [--out <path>]` |

---

## Session Guards and Scope Control

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/careful` | `skills/careful/SKILL.md` | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE, etc.) | `[off]` |
| `/freeze` | `skills/freeze/SKILL.md` | Scope-lock editing to a glob pattern; blocks edits outside the pattern | `<glob-pattern>` |
| `/unfreeze` | `skills/unfreeze/SKILL.md` | Lift the scope lock set by `/freeze` | `(none)` |
| `/guard` | `skills/guard/SKILL.md` | Combined `/careful` + `/freeze` for production-critical sessions | `<glob-pattern>` |
| `/proxy-resilience` | `skills/proxy-resilience/SKILL.md` | Bounded backoff, retry ceiling, and escalation convention for repeated proxy failures | `(none)` |

---

## Infrastructure and Docker

### Standalone

| Command | File | What It Does | Arguments |
| --- | --- | --- | --- |
| `/docker-image-audit` | `skills/docker-image-audit/SKILL.md` | Audit Docker images and Dockerfiles for security vulnerabilities, bloat, and best-practice violations | `[path] [--image <name>]` |
| `/docker-image-create` | `skills/docker-image-create/SKILL.md` | Generate production-ready Dockerfiles from project source code | `[path]` |

---

## Multi-Phase Pipeline Reference

The two commands below are the plugin's **multi-phase pipelines with inter-phase human gates**.

---

## `/ship`

**File:** [`skills/ship/SKILL.md`](../skills/ship/SKILL.md)
**Role:** orchestrator.
**Use when:** the user says "ship this", "take this feature end to end", or
wants the spec → plan → build → PR flow without re-assembling it each time.

### Steps

| # | Step | Delegates to | Human gate after? |
| --- | --- | --- | --- |
| 1 | **Approach contract** — screen request against [`knowledge/decision-defaults.md`](../knowledge/decision-defaults.md); resolve ambiguous high-reversal-cost axes in one batch. | (orchestrator only) | yes, if a blocker remains |
| 2 | **Spec** *(skipped with `--skip-spec`)* — produce Intent, Architecture, Acceptance Criteria. | [`/specs`](../skills/specs/SKILL.md) | **yes** — operator approves the spec |
| 3 | **Plan** — decompose into vertical slices with Gherkin scenarios; a tier-scaled set of plan-review personas (1–5, by plan complexity) runs in parallel before the gate. | [`/plan`](../skills/plan/SKILL.md) | **yes** — operator approves the plan |
| 4 | **Build** — small per-behavior batches per slice (Code-First Small Batches), inline review checkpoints, verification evidence. Do not proceed until the suite is green. | [`/build`](../skills/build/SKILL.md) | no |
| 5 | **Review** — run quality-review agents and let the auto-fix loop converge. Only judgment-call findings escalate to the operator. | [`/code-review`](../skills/code-review/SKILL.md) | no |
| 6 | **PR** — pre-PR quality gate, open PR, arm auto-merge by default (`--no-auto-merge` to opt out). | [`/pr`](../skills/pr/SKILL.md) | **yes** — the PR is the final review artifact |
| 7 | **Report** — PR URL, quality-gate result, whether auto-merge is armed. | (orchestrator only) | — |

### Agents involved (dispatched by the delegated skills)

`/build`'s inline review checkpoints dispatch the review agents listed in
[`team-structure.md` → Review Agent Dispatch](team-structure.md#review-agent-dispatch-phase-3-inline-checkpoints).
`/plan` dispatches a tier-scaled subset of the five plan-review persona
agents (`agents/plan-review-*.md`) — the Acceptance Test Critic always
runs; the rest are added as the plan's tier (`trivial`/`standard`/`complex`)
warrants — and the
[`progress-guardian`](../agents/progress-guardian.md) gate-keeper.
`/code-review` re-runs the same review agents over the full changeset.

### Arguments

`/ship <feature-description> [--skip-spec] [--no-auto-merge]`

| Flag | Behavior |
| --- | --- |
| `<feature-description>` | Positional. The feature to build (required). |
| `--skip-spec` | Skip the spec phase (use when a spec already exists for this work). |
| `--no-auto-merge` | Open the PR without arming auto-merge. |

### Notes

- Sequencing only — every gate, fix loop, and evidence requirement comes from
  the underlying skills. If any phase stops at a gate, `/ship` stops with it.
- For a plan-only pass, use [`/plan`](../skills/plan/SKILL.md);
  for build-only, use [`/build`](../skills/build/SKILL.md).
- Resume across sessions with [`/continue`](../skills/continue/SKILL.md).

---

## `/test-improve`

**File:** [`skills/test-improve/SKILL.md`](../skills/test-improve/SKILL.md)
**Role:** orchestrator.

The full seven-phase reference — phase-by-phase gates, arguments, and the flow
diagram — lives on its own page: **[test-improve.md](test-improve.md)**.

---

## Cross-command lifecycle

Use `/test-improve` alongside `/ship` for multi-phase quality pipelines — run
`/test-improve` to raise baseline coverage and health first, then `/ship` to
carry the feature through spec → build → PR.

`/ship` and `/test-improve` are the two **multi-phase pipelines with
inter-phase human gates** in the plugin. Every other slash
command is either a single-step worker (e.g. `/coverage-baseline`,
`/triage`) or a one-shot orchestrator that returns in a single pass (e.g.
`/code-review`, `/test-design`). Knowing the phase order, the owning skill
or agent for each step, and where the human gates fall is the difference
between operating these workflows confidently and re-reading every SKILL.md
each time.

One cross-command lifecycle *is* documented separately: the defect workflow
that connects `/triage`'s triage records, `/code-review`'s correction
prompts, and `/apply-fixes` — from discovery to applied fix, including who
owns leftover `corrections/` files — lives in
[triage-workflow.md](triage-workflow.md).
