# Agentic Dev Team

Two Claude Code plugins for engineering workflows. Install one or both.

- **`dev-team`** gives Claude Code a full persona-driven development team: an Orchestrator that routes tasks, specialist agents (engineer, QA, architect, reviewers…), skills that encode reusable knowledge, and the four-command feature workflow `/specs → /plan → /build → /pr`.
- **`security-assessment`** is the security companion. It adds a deterministic-first `/security-assessment` pipeline (SAST + LLM judgment + FP-reduction + exec report), a `/cross-repo-analysis` command for multi-repo attack chains, and an adversarial ML red-team harness (`/redteam-model`) for self-owned model endpoints.

The two plugins share a primitives contract (`codebase-recon`, `ACCEPTED-RISKS.md`, unified finding envelope) that lives in `dev-team`. Install that plugin first; add the security companion when you need it.

## Plugins

| Plugin | What it does | Key commands | Required tools | Optional tools |
| --- | --- | --- | --- | --- |
| **[dev-team](plugins/dev-team/README.md)** | Persona-driven development team, reviewer swarm, TDD-gated build loop | `/specs`, `/plan`, `/build`, `/pr`, `/code-review`, `/triage` | `jq`, `gh` | `semgrep`, `playwright`, `hadolint`/`trivy`/`grype`; auto-detected formatters and test/type/lint runners |
| **[security-assessment](plugins/security-assessment/README.md)** | Tool-first security assessment + red-team pipeline | `/security-assessment`, `/cross-repo-analysis`, `/redteam-model`, `/export-pdf` | `dev-team`, Python ≥ 3.10, tier-1 SAST (`semgrep`, `gitleaks`, `trivy`, `hadolint`, `actionlint`) | `grype`, PDF-export deps |

Plugin names link to each plugin's README, where the full tool list and per-tool install commands live. Claude Code itself is assumed. **First time here?** Start with `dev-team`; add `security-assessment` only when you run full `/security-assessment` pipelines against target repos.

## Getting Started

### Install `dev-team`

Start here — most users install only this plugin. Required tools (`jq`, `gh`) are listed in the [Plugins](#plugins) table above.

```bash
claude plugin marketplace add bdfinst/agentic-dev-team
claude plugin install dev-team@bfinster
```

The `owner/repo` shorthand and the full `https://github.com/bdfinst/agentic-dev-team` URL are equivalent. For self-hosted or other git hosts, install scopes (`user`/`project`/`local`), and the upgrade/re-point commands, see the [plugin install guide](plugins/dev-team/README.md#install).

Then, in your project, install tool dependencies and generate config:

```text
/init-dev-team
/setup
```

- **`/init-dev-team`** installs the tools the plugin depends on — `jq` and `python3` (mutation gate), language-specific mutation testing (Stryker for JS/TS, pitest for Java/Kotlin, Stryker.NET for C#), an optional CodeGraph index for code intelligence, and an opt-in model-availability probe for restricted API endpoints.
- **`/setup`** detects your stack and generates project-level config and hooks, including the automated pre-commit review gate.

After `/setup`, run `/specs` to start a feature, or ask a question and let the Orchestrator route it.

### Install `security-assessment` (optional)

Add this plugin only if you want the `/security-assessment` pipeline. Install `dev-team` first.

```bash
claude plugin install security-assessment@bfinster
```

For a self-hosted git host, see the [plugin install guide](plugins/dev-team/README.md#install); for a local clone, see [Local development](CONTRIBUTING.md#local-development) in CONTRIBUTING.

### Update an installed plugin

Run `/upgrade` from any Claude Code session with `dev-team` installed. It:

1. Reads the current installed scope from `claude plugin list` and passes `--scope <scope>` to `claude plugin update`, so project- and local-scope installs upgrade correctly rather than silently failing against the `user` default.
2. Asks before enabling marketplace-level auto-update (the same `extraKnownMarketplaces.<marketplace>.autoUpdate` flag the `/plugin` UI toggles); decline to keep manual control.
3. Reports the previous and new version, and prompts you to restart Claude Code so the new code loads.

Manual fallback when `/upgrade` is unavailable:

```bash
claude plugin update --scope <scope> dev-team@bfinster
claude plugin update --scope <scope> security-assessment@bfinster
```

Then install the tier-1 static-analysis tools:

```bash
# macOS
./plugins/security-assessment/install-macos.sh           # tier-1 only
./plugins/security-assessment/install-macos.sh --all     # tier-1 + optional + PDF deps
./plugins/security-assessment/install-macos.sh --dry-run # preview without running

# Windows (requires Scoop)
.\plugins\security-assessment\install-windows.ps1
```

Verify: `./plugins/security-assessment/install.sh`

## Dev team workflow

Four commands drive feature development from idea to pull request:

```text
/specs  →  /plan  →  /build  →  /pr
```

| Step | Command | What it does |
| --- | --- | --- |
| **1. Specify** | `/specs` | Describe the change and its goals — Intent, Architecture notes, Acceptance Criteria. A consistency gate must pass before moving on. Skip for bug fixes, refactors, or trivial changes. |
| **2. Plan** | `/plan` | Decompose the feature into vertical slices, author each slice's Gherkin scenarios, and lay out the TDD steps that satisfy them. Four plan-review personas (Acceptance Test, Design, UX, Strategic critics) challenge the plan before the human sees it. Human approves before any code is written. |
| **3. Build** | `/build` | Execute the approved plan slice by slice. Each step follows RED-GREEN-REFACTOR with inline review checkpoints (spec-compliance first, then quality agents). Produces verification evidence. |
| **4. Ship** | `/pr` | Run quality gates (tests, typecheck, lint, code review) and open a pull request. |

Each step produces artifacts the next step consumes. The spec describes *what* and *why*; the plan turns that into per-slice behavioral contracts (Gherkin) and *how*. Human review gates sit between transitions.

![Workflow: specs → plan → build → pr](plugins/dev-team/docs/diagrams/workflow-linear.svg)

For bug fixes or simple tasks, skip `/specs` and start at `/plan` — or go straight to implementation.

### Supporting commands

| Command | When to use |
| --- | --- |
| `/code-review` | Run review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations) |
| `/continue` | Resume an in-progress build or plan across sessions |
| `/browse` | Visual QA via Playwright |
| `/benchmark` | Runtime performance metrics (Core Web Vitals, resource sizes) against baselines |
| `/careful` / `/freeze` / `/guard` | Safety modes for production-critical sessions |
| `/triage` | Investigate a bug and file a GitHub issue with a TDD fix plan |

### Automated pre-commit review

Every `git commit` is automatically gated by `/code-review`. A `PreToolUse` hook detects commit attempts and blocks them until a passing review exists for the exact set of staged files.

**Flow**: attempt commit → hook blocks → Claude runs `/code-review` → if pass/warn, a `.review-passed` gate file is written → next commit attempt succeeds.

**Bypass**: `git commit --no-verify` skips the review gate.

## Security assessment pipeline

`/security-assessment <path>` runs a six-phase pipeline against one or more target repos. Deterministic tools do the detection; LLM agents handle the judgment stages.

| Phase | Runs | Output |
| --- | --- | --- |
| **0. Recon** | `codebase-recon` agent | `memory/recon-<slug>.{json,md}` |
| **1. Tool-first detection** | semgrep, gitleaks, trivy, hadolint, actionlint, custom rulesets | unified findings stream |
| **1b. Judgment** | `security-review`, `business-logic-domain-review` agents | appended findings |
| **1c. Suppression** | `ACCEPTED-RISKS.md` gate (deterministic) | filtered stream + audit log |
| **2. FP-reduction** | 5-stage rubric (reachability, environment, controls, dedup, severity) | disposition register |
| **2b. Severity floors** | deterministic domain-class calibration | floor-adjusted scores |
| **3. Narrative + compliance** | `tool-finding-narrative-annotator`, compliance-mapping skill | 4-domain narrative + compliance JSON |
| **4. Cross-repo** | service-comm parser, shared-cred hash match (multi-target only) | mermaid diagram + SARIF |
| **5. Exec report** | `exec-report-generator` agent | publication-ready 7-section markdown |

**Zero-install flow**: `scripts/run-assessment-local.sh` runs the same pipeline from the repo checkout without installing the plugin. Auto-detects the `claude` CLI; degrades to deterministic-only when absent. See [the user guide](plugins/security-assessment/docs/user-guide-security-assessment.md) for the full runbook.

**Adversarial ML red-team**: `/redteam-model` probes a self-owned model endpoint (localhost / RFC1918 by default; public targets require a signed `authorization.md`). Eight probes covering recon, evasion, extraction, and report synthesis.

---

## Contributing

Developing, testing, or releasing the plugins? See **[CONTRIBUTING.md](CONTRIBUTING.md)** — local-dev setup (including live installs via symlinks), the `/agent-eval` and `/agent-audit` test commands, the security comparative-testing harness, how to add agents and skills, and the release process.

## Documentation

### Start here

| Doc | Covers |
| --- | --- |
| [Getting Started](GETTING-STARTED.md) | User tutorial — the workflow, suggested skills, worked examples |
| [Contributing](CONTRIBUTING.md) | Local development, testing, adding agents/skills, releasing |
| [Plugin Development Guide](CLAUDE.md) | Project North Star, repo structure, working rules |

### dev-team — architecture

| Doc | Covers |
| --- | --- |
| [Plugin README](plugins/dev-team/README.md) | Install, prerequisites, optional tools, quality gates |
| [Orchestration Pipeline](plugins/dev-team/CLAUDE.md) | Three-phase workflow, registries, context management |
| [Architecture](plugins/dev-team/docs/agent-architecture.md) | Context management, quality assurance, governance, model routing |
| [Team Structure](plugins/dev-team/docs/team-structure.md) | Org chart, team + review-agent dispatch diagrams |
| [Agents](plugins/dev-team/docs/agent_info.md) | Agent roster, persona template, adding/removing/customizing |

### dev-team — workflows & skills

| Doc | Covers |
| --- | --- |
| [Workflows](plugins/dev-team/docs/workflows.md) | `/ship` and `/test-modernize` orchestration with human gates |
| [Code Review Process](plugins/dev-team/docs/code-review-process.md) | `/code-review` end-to-end flow and the agents it dispatches |
| [Skills & Commands](plugins/dev-team/docs/skills.md) | Skills catalog and slash-command reference |
| [Session Review](plugins/dev-team/docs/session-review.md) | Mining session transcripts for improvement suggestions |
| [Session Review — OSS complements](plugins/dev-team/docs/session-review-oss-complements.md) | OSS tools that complement the session-review loop |

### dev-team — model routing

| Doc | Covers |
| --- | --- |
| [Model Routing](plugins/dev-team/docs/model-routing.md) | Environment-aware effort-band → model resolution, defaults, ladder, troubleshooting |

### dev-team — evaluation & quality

| Doc | Covers |
| --- | --- |
| [Eval System](plugins/dev-team/docs/eval-system.md) | How review-agent accuracy is measured and graded |
| [Eval Running Guide](plugins/dev-team/docs/eval-running-guide.md) | Running the eval fixtures |
| [Eval Maintenance](plugins/dev-team/docs/eval-maintenance.md) | Maintaining fixtures, catching regressions, tracking accuracy |
| [Test Evaluation](plugins/dev-team/docs/test-evaluation.md) | Test-evaluation procedures |

### dev-team — operations & observability

| Doc | Covers |
| --- | --- |
| [Concurrent Use](plugins/dev-team/docs/concurrent-use.md) | Worktree isolation and concurrent build strategy |
| [CodeGraph Nudge](plugins/dev-team/docs/codegraph-nudge.md) | The hook that nudges CodeGraph over multi-file Read/Grep |
| [Telemetry — CI access](plugins/dev-team/docs/telemetry-ci-access.md) | Giving CI read-only access to the telemetry repo |
| [Telemetry — repo security](plugins/dev-team/docs/telemetry-repo-security.md) | How machines write digests to the telemetry repo |

### security-assessment plugin

| Doc | Covers |
| --- | --- |
| [Plugin README](plugins/security-assessment/README.md) | Design philosophy, install, when to use vs. `/code-review` |
| [Plugin Architecture](plugins/security-assessment/CLAUDE.md) | Hooks, SARIF orchestration, LLM-safety bounds, red-team targets |
| [User Guide](plugins/security-assessment/docs/user-guide-security-assessment.md) | Path-A (plugin) vs. Path-B (zero-install) runbook, tool matrix |
| [Accepted Risks Format](plugins/security-assessment/docs/accepted-risks-format.md) | `ACCEPTED-RISKS.md` schema and format |
| [Comparative Testing](plugins/security-assessment/docs/comparative-testing.md) | Fixture repo, ground truth, scoring methodology |

### Repo-level guides & decision records

| Doc | Covers |
| --- | --- |
| [Marketplace Builder Playbook](docs/marketplace-builder-plugin-playbook.md) | Building a plugin that scaffolds/audits marketplace monorepos |
| [Plugin Skills in the Web Environment](docs/using-plugin-skills-in-the-web-environment.md) | Running a plugin's skills from a Claude Code web session |
| [Architecture Decision Records](docs/adr/README.md) | Indexed ADRs — model routing, knowledge indexing, eval tiers, integration topology |
| [Design Specs](docs/specs/model-complexity-routing.md) | Effort-band model routing design specification |

## CodeGraph

This repository uses [CodeGraph](https://github.com/colbymchenry/codegraph) for semantic code intelligence.
