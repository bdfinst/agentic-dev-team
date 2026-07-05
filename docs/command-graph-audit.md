# Command graph audit — top-level and isolated commands

Generated 2026-07-05 from the working tree (`plugins/dev-team/skills/`, 81
user-invocable skills). Revised twice after review caught reference forms the
first pass missed; the method below is the corrected one.

## Method

Three reference classes are checked, because a command can be wired into the
system without another command ever naming it:

1. **Command → command** — another user-invocable SKILL.md references it, in any
   of the observed forms: `/name`, `dev-team:name`, `Skill(name ...)`,
   "the `name` skill", or a backticked `` `name` `` citation (e.g. "schema in
   `performance-metrics`"). Every bare-name mention of a listed command in every
   other command body was manually classified to catch novel forms.
2. **Agent / knowledge → command** — an agent's routing table or a curated
   knowledge file dispatches or links the skill (e.g. orchestrator's skill
   table, an agent's "invoke when…" list). Exhaustive catalogs that list every
   skill by design (`knowledge/skills-registry.md`, `knowledge/agent-registry.md`,
   `knowledge/index.json`, `docs/skills.md`, `hooks/lib/skill_categories.yaml`)
   are excluded — appearing there carries no signal.
3. **Everything else** (README, workflow docs) is user documentation of entry
   points and is not counted as wiring.

**Corrections over the first drafts** (kept so the earlier versions can't
mislead): `farley-score` was wrongly listed isolated — it is dispatched by
`/test-design` (`Skill(farley-score ...)`) and `/build` step 7. `legacy-code`
was wrongly listed top-level. `performance-metrics` was wrongly listed
top-level — `/build`, `/cost-report`, and `/harness-audit` all cite its
`review-value.jsonl` schema.

## Isolated in the command graph — no command callers or callees (13)

Nothing in the *command* graph routes into them, but most are wired in via
agents or knowledge — the right-hand column is what the first draft missed.

| Command | Description | Referenced by (agents / knowledge) |
|---|---|---|
| `adr-tools` | ADR CLI mechanics (npryce adr-tools). | `knowledge/adr-decision-criteria.md` (pairs with adr-author agent) |
| `api-design` | Contract-first API design. | architect, software-engineer agents ("invoke when…") |
| `ci-debugging` | Systematic CI/CD failure diagnosis. | qa-engineer agent |
| `competitive-analysis` | Gap analysis vs external plugins/tools. | — |
| `design-it-twice` | N parallel interface designs, compare and synthesize. | — |
| `docker-image-audit` | Scan images/Dockerfiles (hadolint, Trivy, Grype). | `knowledge/deployment-pipeline.md` |
| `docker-image-create` | Generate production multi-stage Dockerfiles. | — |
| `help` | List all slash commands. | — |
| `mermaid-diagramming` | Mermaid diagrams in the project theme. | — |
| `model-routing-check` | Read-only effort-band routing diagnostic. | orchestrator agent (twice) |
| `proxy-resilience` | Backoff/retry convention for corporate-proxy failures. | — |
| `threat-modeling` | STRIDE threat analysis. | architect, security-engineer agents |
| `upgrade` | Apply plugin updates. | — |

## Top-level in the command graph — no command callers, has callees (13)

| Command | Description | Calls | Referenced by (agents / knowledge) |
|---|---|---|---|
| `agent-audit` | Structural compliance audit of agents/skills/hooks. | `build`, `code-review` | orchestrator agent |
| `benchmark` | Web-page runtime performance metrics. | `browse`, `build` | — |
| `branch-workflow` | PR creation, merge strategy, cleanup. | `code-review` | orchestrator agent |
| `design-interrogation` | Interview the user to surface hidden decisions. | `plan`, `specs` | product-manager agent |
| `frontend-architecture` | Component-architecture review dispatch. | `apply-fixes`, `build`, `code-review`, `plan` | — |
| `governance-compliance` | Audit logging, gates, ethics procedures. | `feedback-learning`, `quality-gate-pipeline` | platform-engineer, qa-engineer, security-engineer, tech-writer agents |
| `guard` | careful + freeze composite. | `careful`, `freeze`, `unfreeze` | — |
| `human-oversight-protocol` | Approval gates and intervention commands. | `feedback-learning` | orchestrator, product-manager agents |
| `review` | Alias for `/code-review`. | `code-review` | — |
| `semgrep-analyze` | Semgrep run with structured findings. | `code-review` | orchestrator agent |
| `setup` | Detect stack; generate CLAUDE.md, hooks, templates. | `pr` | — |
| `test-driven-development` | Classic TDD cycle with hard gates (opt-in cadence). | `build`, `systematic-debugging` | qa-engineer, software-engineer agents |
| `ubiquitous-language` | Build/refresh the domain glossary. | `code-review`, `domain-analysis`, `domain-driven-design`, `specs` | domain-review agent |

## Zero references anywhere (12) — the real audit shortlist

No command, agent, or curated-knowledge reference at all. These are reachable
only by a user typing them. Zero wiring is not the same as dead — several are
deliberately user-only utilities — but nothing breaks if one is removed, so
keep/cut is decided purely by intent and usage telemetry
(`/artifact-lifecycle` over `metrics/artifact-usage.json`):

`benchmark`, `competitive-analysis`, `design-it-twice`, `docker-image-create`,
`frontend-architecture`, `guard`, `help`, `mermaid-diagramming`,
`proxy-resilience`, `review`, `setup`, `upgrade`

Of these, `help`, `upgrade`, `guard`, and `review` are plausibly intentional
user-only utilities (`review` is a pure alias, `guard` a pure composite —
their value is discoverability). The other eight warrant a usage-telemetry
check.

## Notes for the audit

- The remaining 55 commands are referenced by at least one other command and
  are load-bearing in the command graph; removing any requires updating callers.
- Lesson encoded in the method above: a "who calls this" audit over skills must
  match dispatch forms (`Skill(name)`, "the `name` skill", backticked schema/doc
  citations) and must include agent routing tables — the `/name` form alone
  misclassified three commands across the first two drafts.
