# Command graph audit — top-level and isolated commands

Generated 2026-07-05 from the working tree (`plugins/dev-team/skills/`, epic/823 branch,
81 user-invocable skills). A command "calls" another when its SKILL.md body references
it as `/name`, `dev-team:name`, `Skill(name ...)`, or "the `name` skill" / "skill
`name`". **Caveat:** an edge counts any such reference — actual dispatch *and* prose
mentions ("use after `/plan`") — so these lists are conservative: an isolated command
truly has zero cross-references, but a command's outgoing edges may include
mention-only links.

## Isolated commands — no callers, no callees (13)

Fully self-contained leaves: nothing routes into them and they route nowhere.
Prime candidates for the stale/keep audit — if one is unused, removing it breaks no
other command.

| Command | Description |
|---|---|
| `adr-tools` | Create and manage Architecture Decision Records using the npryce adr-tools CLI. |
| `api-design` | Contract-first API design for stable, evolvable interfaces. |
| `ci-debugging` | Systematic CI/CD failure diagnosis with hypothesis-first approach and environment delta analysis. |
| `competitive-analysis` | Compare this plugin against external plugins/tools/feature sets to find gaps; produces a gap-analysis report. |
| `design-it-twice` | Generate multiple radically different interface designs via parallel sub-agents, then compare and synthesize. |
| `docker-image-audit` | Audit Docker images/Dockerfiles for vulnerabilities, bloat, and best-practice violations (hadolint, Trivy, Grype). |
| `docker-image-create` | Generate production-ready multi-stage Dockerfiles from project source. |
| `help` | List all available slash commands with their descriptions. |
| `mermaid-diagramming` | Create Mermaid diagrams using the project's blue-gray theme. |
| `model-routing-check` | Read-only diagnostic for effort-band model routing. |
| `proxy-resilience` | Bounded backoff, retry ceiling, and escalation convention for repeated corporate-proxy failures. |
| `threat-modeling` | Structured STRIDE security analysis for threats, attack surfaces, and mitigations. |
| `upgrade` | Check for and apply plugin updates via the official plugin update mechanism. |

## Top-level commands with outgoing calls — entry points only (14)

Never referenced by another command, but fan out into the graph. These are
user-facing entry points; auditing one means checking its callees still exist and
the workflow it fronts is still current.

| Command | Description | Calls |
|---|---|---|
| `agent-audit` | Audit code-review agents, skills, and hooks for structural compliance. | `build`, `code-review` |
| `benchmark` | Capture runtime performance metrics (Core Web Vitals, resource sizes, load times) for web pages. | `browse`, `build` |
| `branch-workflow` | Clean branch completion workflow — PR creation, merge strategy, cleanup. | `code-review` |
| `design-interrogation` | Relentlessly interview the user about a plan/design to surface unresolved decisions and hidden assumptions. | `plan`, `specs` |
| `frontend-architecture` | Dispatch component-architecture-review over frontend components (extraction, duplication, prop drilling). | `apply-fixes`, `build`, `code-review`, `plan` |
| `governance-compliance` | Audit logging, quality gates, and ethics procedures for the agent team. | `feedback-learning`, `quality-gate-pipeline` |
| `guard` | Activate careful mode and freeze mode together (production-critical sessions). | `careful`, `freeze`, `unfreeze` |
| `human-oversight-protocol` | Approval gates, intervention commands, and transparency requirements. | `feedback-learning` |
| `performance-metrics` | Log task completion data to `metrics/`. | `build`, `cost-report`, `plan` |
| `review` | Alias for `/code-review`. | `code-review` |
| `semgrep-analyze` | Run Semgrep static analysis on target files, return structured findings. | `code-review` |
| `setup` | Detect a project's tech stack and auto-generate project CLAUDE.md, hooks, and agent templates. | `pr` |
| `test-driven-development` | Enforce Classic TDD RED-GREEN-REFACTOR with hard gates — the opt-in test-first cadence (default is Code-First Small Batches). | `build`, `systematic-debugging` |
| `ubiquitous-language` | Build or refresh the project's ubiquitous-language glossary under `.plans/domain/`. | `code-review`, `domain-analysis`, `domain-driven-design`, `specs` |

## Notes for the audit

- The isolated set overlaps heavily with utility/one-shot tools (Docker pair, help,
  upgrade, diagnostics). Their health signal is usage telemetry
  (`/artifact-lifecycle` reads `metrics/artifact-usage.json`), not graph position.
- Earlier drafts of this report listed `farley-score` as isolated and `legacy-code`
  as top-level; both were artifacts of matching only the `/name` form. `farley-score`
  is dispatched by `/test-design` (`Skill(farley-score ...)`) and `/build` step 7
  ("invoke the `farley-score` skill"); `legacy-code` is likewise referenced by
  another command in skill-invocation form.
- `review` is a pure alias; `guard` is a pure composite — both are thin wrappers whose
  value is discoverability.
- The remaining 54 commands (not listed) are referenced by at least one other command
  and are load-bearing in the graph; removing any of them requires updating callers.
