# Command taxonomy — what each user-invocable command is *for*

Generated 2026-07-05 from the working tree (`plugins/dev-team/skills/`, 80
user-invocable skills). This report classifies every user-invocable command by
**purpose** (the question "what is this command for") rather than by graph
topology (who-calls-what). The appendix keeps the earlier who-calls-what wiring
analysis, condensed, because the analysis surfaced two real defects.

The three lists a maintainer reasons about:

1. **Orchestration workflows** — invoking the command starts or steers a chain that hands
   work between skills/agents/gates toward a deliverable (a PR, a spec set, a
   passing suite, a triage record).
2. **Standalone utilities** — the user calls the command, the command does its one job, and stops.
3. **Plugin lifecycle & self-maintenance** — the command acts on the dev-team plugin
   itself: install it, upgrade it, or audit/eval/tune it as a product.

A residual fourth group (internal workers, project onboarding, harness plumbing)
is user-invocable but is not a natural user entry point. The report lists this group last so the
taxonomy stays honest and totals 80.

## 1. Orchestration workflows — drive an outcome (22)

### Core delivery pipeline

| Command | Outcome it drives |
| --- | --- |
| `ship` | Umbrella: spec → plan → build → review → PR → auto-merge, pausing at human gates |
| `specs` | The three spec artifacts, through the cross-artifact consistency gate |
| `design-doc` | Research-phase design doc (approval gate) → feeds `plan` |
| `plan` | Structured implementation plan → feeds `build` |
| `build` | Executes the plan (Code-First Small Batches by default; Classic TDD opt-in) with inline review checkpoints |
| `code-review` | Runs all enabled review agents over the diff |
| `review` | Pure alias for `code-review` |
| `apply-fixes` | Applies `code-review` corrections back to the working tree |
| `pr` | Pre-PR quality gate (tests, typecheck, lint, review) → opens the PR |
| `branch-workflow` | Branch completion: review → PR → merge → cleanup |
| `continue` | Resumes an in-progress pipeline from phase files in `.claude/memory/` |
| `triage` | Bug → root cause → portable triage record with a TDD fix plan |

### Review gates/lenses inside the pipeline

| Command | Role in the flow |
|---|---|
| `frontend-architecture` | Reviews component changes during `code-review` and rejects bad component design so the coding agent fixes it. It is a gate in the review→fix loop and runs whenever frontend component files are in scope |

### Test & quality orchestrations

These commands dispatch sub-agents/workers and roll up a report or drive convergence.

| Command | Outcome it drives |
| --- | --- |
| `test-improve` | Analyze → improve the suite; dispatches coverage/gherkin/mutation workers |
| `test-design` | Fans out test-review + test-smell-review + the test-design advisor |
| `test-health` | Project-wide test-strategy audit rollup (shape, quadrants, coverage + mutation) |
| `cd-test-architecture` | Assess tests → recommend a CD-aligned architecture (feeds `issues-from-assessment`) |
| `domain-analysis` | Strategic DDD health assessment → friction / value-stream report |
| `exploratory-testing` / `explore` | Charter-driven probe → adversarial expansion → auto-triaged report |
| `quality-gate-pipeline` | Unified multi-gate self-validation + review-correction loop |
| `systematic-debugging` | Four-phase reproduce → investigate → root-cause → fix protocol |

## 2. Standalone utilities — one job, then stop (35)

**Modes & session controls:** `careful`, `freeze`, `unfreeze`, `guard`, `browse`

**Info / status:** `help`, `version` (report the installed plugin version for the
user), `cost-report`, `agent-readiness` (scores *your* repo — contrast
`harness-audit`, which audits the plugin)

**Single-purpose analysis & advisory:** `benchmark`, `docker-image-audit`,
`docker-image-create`, `mermaid-diagramming`, `semgrep-analyze`, `api-design`,
`threat-modeling`, `ci-debugging`, `proxy-resilience`, `farley-score`,
`mutation-testing`, `feature-file-validation`, `adr-tools`, `ubiquitous-language`,
`hexagonal-architecture`, `domain-driven-design`, `legacy-code`, `design-it-twice`,
`design-interrogation`, `review-agent`, `review-summary`, `governance-compliance`,
`human-oversight-protocol`, `gherkin-public`, `semantic-scan`,
`test-driven-development` (an opt-in cadence *mode* that steers `build`)

## 3. Plugin lifecycle & self-maintenance — acts on the plugin itself (11)

### Manage the installed plugin

| Command | Purpose |
| --- | --- |
| `upgrade` | Check for and apply plugin updates via the official mechanism |

### Develop & improve the plugin

| Command | What it maintains |
| --- | --- |
| `agent-audit` | Structural compliance of agents / skills / hooks |
| `agent-eval` | Runs eval fixtures against the review agents; grades detection accuracy |
| `harness-audit` | Review-agent effectiveness, model routing, orchestration complexity → simplification candidates |
| `model-routing-check` | Read-only effort-band model-routing diagnostic |
| `competitive-analysis` | Gap analysis of this plugin vs external plugins/tools |
| `artifact-lifecycle` | Finds stale / archive-candidate skills & agents from usage data |
| `session-review` | Mines session transcripts → plugin-improvement suggestions |
| `feedback-learning` | `amend`/`learn`/`remember`/`forget` → tunes agent/skill configs |
| `telemetry` | Manages the opt-in usage-telemetry beacon |
| `performance-metrics` | Logs per-task token/cost/rework metrics that feed the improvement loop |

## Not user entry points (12)

- **Internal workers** — the orchestrators in list 1 dispatch these; they are user-invocable
  only for isolated testing: `coverage-baseline`, `coverage-delta`,
  `quality-targets-converge`, `issues-from-plan`, `issues-from-assessment`,
  `test-audit-disable`, `gherkin-derive`, `semantic-duplication-scan`
- **Project onboarding** — you invoke these *after adding the plugin to a repo*. They
  configure the target repo, not the plugin: `setup` (install plugin
  prerequisites — jq, python3, per-language mutation tooling; detect stack;
  generate CLAUDE.md, hooks, templates — absorbed the former `init-dev-team`
  command) and `project-init` (detect stack, inventory/install
  static-analysis tools, offer opt-in graph-tools — CodeGraph and/or Graphify, see
  `plugins/dev-team/knowledge/codegraph-vs-graphify.md`). See the open gap below. A command that needs a missing
  tool should prompt the user to run these.
- **Harness plumbing** — context management, rarely typed directly:
  `context-loading-protocol`, `handoff`

## Open gaps / defects

- **`adr-author` ↔ `adr-tools`** ([#837](https://github.com/bdfinst/agentic-dev-team/issues/837)) —
  the adr-author agent lacks `Bash`/`Skill`, so it cannot drive the `adr` CLI it is
  meant to author through. The agent hand-rolls numbering instead.
- **Missing-tool → onboarding prompt** ([#838](https://github.com/bdfinst/agentic-dev-team/issues/838)) — commands that need an absent
  tool hand-roll their own install hint (`semgrep-analyze` → "pip install
  semgrep"; `benchmark`/`browse` → "npx playwright install"; `docker-image-audit`
  → "read install-guide.md") instead of prompting the user to run `/project-init`
  (or `/setup`). Only `build`'s self-heal path routes to `project-init`. Expected
  behavior: any command that hits a missing required tool points the user at
  the onboarding command, consistently.

## Appendix — command-graph wiring notes (condensed)

The prior analysis of this file walked the *command* call graph (which SKILL.md
references which, plus agent/knowledge routing). Its durable findings:

- **Reference forms must all be matched.** A "who calls this" audit over skills
  must match every dispatch form — `Skill(name)`, "the `name` skill", and
  backticked schema/doc citations — and must include agent routing tables. The
  `/name` form alone misclassified three commands across the first drafts
  (`farley-score`, `legacy-code`, `performance-metrics`).
- **Exhaustive catalogs carry no signal.** `knowledge/skills-registry.md`,
  `knowledge/agent-registry.md`, `knowledge/index.json`, `docs/skills.md`, and
  `hooks/lib/skill_categories.yaml` list every skill by design. Appearing there
  is not "wiring."
- **Graph-isolated ≠ dead.** Users reach most commands with no *command* callers
  directly (list 2), or agents/knowledge wire them in. The genuinely
  zero-reference commands are the user-only utilities in lists 2 and 3. Nothing
  breaks if you remove one, so keep/cut is an intent + telemetry decision
  (`/artifact-lifecycle` over `~/.claude/metrics/artifact-usage.json`).
