# Agent-Readiness Scorecard

A weighted scoring system to measure how ready a repository is for AI-assisted code generation. Use this scorecard to assess repositories, communicate gaps to stakeholders, and track improvement over time through an automated dashboard.

---

## Scoring Model

Each criterion is scored **0 / 1 / 2**:

| Score | Meaning |
|-------|---------|
| **0** | Not present or non-functional |
| **1** | Partially present, inconsistent, or not enforced |
| **2** | Fully present, consistent, and enforced |

**Category scores** are calculated as:

```
category_score = (sum of criterion scores) / (max possible score) * weight
```

**Overall readiness** is the sum of all weighted category scores, yielding a value from **0 to 100**.

---

## Readiness Tiers

| Tier | Score | Interpretation |
|------|-------|----------------|
| **Agent-Ready** | 75 - 100 | Agents can operate autonomously with standard code review. High confidence in output quality. |
| **Agent-Assisted** | 50 - 74 | Agents are productive but require heavier human guidance and more review cycles. |
| **Agent-Limited** | 25 - 49 | Significant friction. Agents help with isolated, well-scoped tasks only. |
| **Agent-Hostile** | 0 - 24 | Fix fundamentals first. Agent use will create more problems than it solves. |

---

## Category Weights

| # | Category | Weight | Rationale |
|---|----------|--------|-----------|
| 1 | Test Infrastructure | **25%** | The single most important factor. Agents need automated verification to confirm their changes work. Without tests, every agent output requires full manual validation, eliminating the productivity benefit. |
| 2 | Build & Dev Environment | **20%** | If an agent can't build, run, or validate the project reliably, it can't close any feedback loop. A reproducible, single-command environment is the foundation everything else depends on. |
| 3 | Code Quality & Consistency | **20%** | Agents learn patterns from the code they read. Consistent patterns mean agents produce code that fits the codebase. Inconsistent codebases produce inconsistent agent output. |
| 4 | Type Safety & Contracts | **15%** | Strong typing and explicit interfaces constrain the solution space. Agents make fewer mistakes when the compiler/type checker catches errors before runtime. This is the highest-leverage passive safety net. |
| 5 | Documentation & Context | **10%** | Documentation helps agents understand intent and constraints, but agents can also infer patterns from well-structured code. This category matters more when the codebase is complex or domain-specific. |
| 6 | Version Control & Safety Nets | **10%** | Branch protection, CI gates, and pre-commit hooks form the last line of defense. They prevent agent mistakes from reaching production even when other safeguards fail. |

### Why These Weights?

The weights reflect a simple principle: **agents need fast, automated feedback loops**. The categories are ordered by how directly they enable that loop:

1. **Tests** tell the agent if its change is correct.
2. **Build environment** lets the agent run those tests.
3. **Code consistency** reduces the chance the agent writes something wrong in the first place.
4. **Type safety** catches mistakes at compile time, before tests even run.
5. **Documentation** helps the agent understand what to build.
6. **Safety nets** catch whatever slips through everything else.

Categories 1-2 (45% combined) represent the **feedback loop** — the ability to verify. Categories 3-4 (35% combined) represent **error prevention** — reducing mistakes upfront. Categories 5-6 (20% combined) represent **guidance and guardrails**.

---

## Detailed Criteria

### 1. Test Infrastructure (25%)

Tests are the agent's primary feedback mechanism. An agent with a strong test suite can iterate toward correct solutions autonomously. An agent without tests is guessing.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| T1 | **Test coverage** | No tests or < 20% coverage | 20-60% coverage | > 60% coverage with critical paths covered |
| T2 | **Test reliability** | Tests frequently fail non-deterministically | Occasional flaky tests | All tests are deterministic and reliable |
| T3 | **Test execution speed** | Full suite > 15 minutes | Full suite 5-15 minutes | Full suite < 5 minutes |
| T4 | **Single command execution** | Multi-step manual setup required | Works but needs env-specific configuration | `npm test` / `pytest` / `make test` works out of the box |
| T5 | **Test type coverage** | Only one type (e.g., only e2e) | Two types present (e.g., unit + integration) | Unit, integration, and e2e tests present |

**Why it matters**: An agent that changes a function and immediately runs tests to verify the change works 10x faster than one that produces code for a human to manually test. Fast, reliable tests are the difference between an agent that iterates to a solution and one that guesses once.

**Dashboard automation**: Coverage % from CI reports, test duration from CI logs, flaky test tracking from test result history, presence of test scripts in `package.json` / `Makefile` / CI config.

---

### 2. Build & Dev Environment (20%)

If the agent can't build the project, it can't verify anything. Reproducibility and simplicity are key — every manual step is a step the agent can't perform.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| B1 | **Single command build** | No documented build process | Build works but requires manual steps | `make build` / `npm run build` / equivalent works cleanly |
| B2 | **Reproducible environment** | "Works on my machine" only | Partial containerization or documented manual setup | Devcontainer, Nix, or Docker Compose for full environment |
| B3 | **Dependency management** | No lock files, unpinned versions | Lock files present but not always updated | Lock files committed, pinned versions, reproducible installs |
| B4 | **CI pipeline** | No CI | CI exists but incomplete (e.g., builds but doesn't test) | CI runs build, test, lint, and security checks on every PR |

**Why it matters**: Agents operate in automated environments. Every step that requires human intervention (installing a specific tool version, setting env vars, running a database) is a step where the agent gets stuck. A fully reproducible environment means the agent can go from clone to working in one command.

**Dashboard automation**: Presence of `Dockerfile` / `devcontainer.json` / `flake.nix`, presence of lock files (`package-lock.json`, `poetry.lock`, `go.sum`), CI config detection, CI pass rate from pipeline history.

---

### 3. Code Quality & Consistency (20%)

Agents generate code by pattern-matching against what they see. A codebase with consistent patterns produces consistent agent output. A codebase where every file does things differently produces unpredictable output.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| C1 | **Enforced formatting** | No formatter configured | Formatter configured but not enforced (no CI check) | Formatter enforced via CI and/or pre-commit hooks |
| C2 | **Linting** | No linter | Linter configured but many violations ignored | Linter enforced, clean lint passes on CI |
| C3 | **Consistent architecture patterns** | No recognizable structure | Some patterns visible but inconsistently applied | Clear, documented patterns followed across the codebase (e.g., hexagonal, MVC) |
| C4 | **Module size and complexity** | Many files > 500 lines, high cyclomatic complexity | Mixed — some well-structured, some monolithic | Files generally < 300 lines, functions focused and readable |
| C5 | **Naming conventions** | Inconsistent naming across the codebase | Mostly consistent with some drift | Consistent naming enforced by linter rules |

**Why it matters**: When an agent sees 10 services all structured the same way, it can reliably produce an 11th. When every service is structured differently, the agent has to guess which pattern to follow — and often guesses wrong. Formatting and linting provide automated correction for surface-level consistency; architecture patterns provide structural consistency.

**Dashboard automation**: Presence and enforcement of `.prettierrc` / `.eslintrc` / `ruff.toml` / equivalent, lint results from CI, average file length and cyclomatic complexity from static analysis tools (SonarQube, CodeClimate, radon).

---

### 4. Type Safety & Contracts (15%)

Types are the most cost-effective error prevention tool for agents. Every type annotation is a constraint that prevents the agent from producing invalid code. The compiler catches mistakes before runtime, before tests, before human review.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| S1 | **Type system usage** | Dynamically typed with no type hints | Partial type coverage (e.g., some TypeScript, some JS) | Fully typed (TypeScript strict mode, Python with mypy/pyright enforced, etc.) |
| S2 | **API contracts / schemas** | No schema definitions | Schemas exist but incomplete or not validated | OpenAPI, GraphQL schema, Protobuf, or JSON Schema with validation |
| S3 | **Interface-driven design** | No clear boundaries between modules | Some interfaces/abstractions present | Explicit interfaces at module boundaries, dependency injection |
| S4 | **Database schema management** | Direct DDL or no schema tracking | Migrations exist but incomplete history | Full migration history, schema validated in CI |

**Why it matters**: An agent working in a strictly typed TypeScript codebase gets immediate compiler feedback on type errors — wrong argument types, missing fields, incompatible return values. The same agent in a plain JavaScript codebase can produce code that looks correct but fails at runtime. Types shift error detection left, which is exactly where agents need it.

**Dashboard automation**: TypeScript `strict` flag in `tsconfig.json`, mypy/pyright config and CI enforcement, presence of OpenAPI/schema files, migration file tracking, type coverage tools (`pyright --verifytypes`, TypeScript coverage).

---

### 5. Documentation & Context (10%)

Documentation helps agents understand the "why" behind code. While agents can infer patterns from well-structured code, they cannot infer business rules, architectural decisions, or domain constraints that aren't expressed in code.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| D1 | **README with setup instructions** | No README or outdated | README exists but incomplete setup steps | README with working build, run, and test instructions |
| D2 | **AI-specific instructions** | None | Basic instructions present | CLAUDE.md / AGENTS.md / .cursorrules with detailed guidance |
| D3 | **Architecture documentation** | No architecture docs | Some docs but outdated or incomplete | Current ADRs, diagrams, or architecture docs maintained |
| D4 | **Domain context** | No domain documentation | Some domain docs or glossary | Domain model documented, ubiquitous language defined |

**Why it matters**: An agent asked to "add a new payment method" needs to understand the payment domain, the existing payment flow, and where new code should go. Without documentation, the agent must infer all of this from code — possible in a clean codebase, nearly impossible in a complex one. AI-specific instructions (CLAUDE.md) are particularly high-leverage: a few hundred tokens of guidance can prevent entire categories of mistakes.

**Dashboard automation**: README presence and length, CLAUDE.md / equivalent detection, ADR directory presence, doc freshness (last modified dates vs. code change dates).

---

### 6. Version Control & Safety Nets (10%)

Safety nets don't help agents write better code — they prevent bad code from causing damage. They are the last line of defense when the agent produces something incorrect despite all other safeguards.

| ID | Criterion | 0 | 1 | 2 |
|----|-----------|---|---|---|
| V1 | **Branch protection** | No protection, direct push to main | Some protection but bypassable | Protected main branch, PR reviews required |
| V2 | **Pre-commit hooks** | None | Some hooks present | Comprehensive hooks (lint, format, test) enforced |
| V3 | **Commit conventions** | No conventions | Informal conventions sometimes followed | Enforced conventional commits or equivalent |
| V4 | **Dependency security scanning** | No scanning | Manual or occasional scanning | Automated scanning (Dependabot, Snyk, Trivy) on every PR |

**Why it matters**: Agents are confidently wrong more often than humans expect. Branch protection ensures a human reviews before merge. Pre-commit hooks catch formatting and lint errors before they reach CI. Security scanning catches vulnerable dependencies the agent might introduce. These safeguards have low cost and high value specifically because agents make different kinds of mistakes than humans.

**Dashboard automation**: Branch protection rules via Git provider API, `.pre-commit-config.yaml` / `husky` config detection, commit message pattern analysis, Dependabot/Snyk config detection.

---

## Score Calculation

### Per-Category Formula

```
category_percentage = sum(criterion_scores) / (num_criteria * 2) * 100
weighted_score = category_percentage * category_weight
```

### Example Calculation

| Category | Raw Score | Max | Category % | Weight | Weighted Score |
|----------|-----------|-----|------------|--------|----------------|
| Test Infrastructure | 6 / 10 | 10 | 60% | 0.25 | 15.0 |
| Build & Dev Environment | 7 / 8 | 8 | 87.5% | 0.20 | 17.5 |
| Code Quality & Consistency | 6 / 10 | 10 | 60% | 0.20 | 12.0 |
| Type Safety & Contracts | 4 / 8 | 8 | 50% | 0.15 | 7.5 |
| Documentation & Context | 3 / 8 | 8 | 37.5% | 0.10 | 3.75 |
| Version Control & Safety Nets | 6 / 8 | 8 | 75% | 0.10 | 7.5 |
| **Total** | | | | | **63.25** |

**Result**: 63.25 — **Agent-Assisted** tier.

---

## Dashboard Implementation Notes

### Data Sources for Automation

| Signal | Source | Collection Method |
|--------|--------|-------------------|
| Test coverage % | CI artifacts (lcov, cobertura, JaCoCo) | Parse CI coverage reports |
| Test duration | CI pipeline logs | Extract timing from CI API |
| Test flakiness | CI test result history | Track pass/fail variance per test over N runs |
| Build reproducibility | Dockerfile, devcontainer.json, flake.nix | File presence detection via repo scan |
| Lock files | package-lock.json, poetry.lock, go.sum | File presence detection |
| CI configuration | .github/workflows/, .gitlab-ci.yml, Jenkinsfile | File presence detection |
| CI pass rate | CI pipeline API | Aggregate pass/fail over last 30 days |
| Formatter config | .prettierrc, .eslintrc, ruff.toml, .editorconfig | File presence + CI step detection |
| Linter enforcement | CI config | Check for lint step in CI pipeline |
| Static analysis | SonarQube, CodeClimate API | Pull complexity metrics |
| File size distribution | Git repo scan | Compute average/p95 file line counts |
| Type system | tsconfig.json (strict), mypy.ini, pyrightconfig.json | File presence + config value checks |
| API schemas | openapi.yaml, .graphql, .proto files | File presence detection |
| Migration files | migrations/ directory, alembic/, flyway/ | Directory presence + file count |
| README | README.md | File presence + word count |
| AI instructions | CLAUDE.md, .cursorrules, AGENTS.md | File presence detection |
| ADRs | docs/adr/, docs/decisions/ | Directory presence + file count |
| Branch protection | Git provider API (GitHub, GitLab, Azure DevOps) | API call per repo |
| Pre-commit hooks | .pre-commit-config.yaml, .husky/ | File presence detection |
| Dependency scanning | .github/dependabot.yml, .snyk | File presence detection |

### Criteria Requiring Manual Assessment

Some criteria resist full automation and benefit from periodic manual review:

| Criterion | Why Manual | Suggested Approach |
|-----------|-----------|-------------------|
| C3 - Architecture patterns | Subjective, requires understanding intent | Periodic tech lead assessment (quarterly) |
| C5 - Naming conventions | Linter can catch some, not all | Partial automation + manual spot check |
| D4 - Domain context | Quality matters more than presence | Product/domain expert review |
| S3 - Interface-driven design | Structural analysis is imprecise | Architect review during scorecard update |

For the dashboard, score these criteria based on the last manual assessment and flag them for re-evaluation on a quarterly cadence.

---

## Using the Scorecard

### For Communicating to Peers

> "We score our repositories on a 0-100 scale across six categories that determine how effectively AI agents can work in the codebase. The categories are weighted by impact: test infrastructure and build environment account for 45% of the score because agents need fast feedback loops to verify their work. A repository scoring below 50 will see limited benefit from agent-assisted development — the investment in improving fundamentals pays for itself."

### For Prioritizing Improvements

Focus improvements in this order (highest impact per effort):

1. **Single command build + test** (B1, B3, T4) — Unblocks everything else
2. **CI pipeline with lint + test** (B4, C1, C2) — Automated enforcement
3. **Test coverage on critical paths** (T1, T2) — Agent verification capability
4. **Type enforcement** (S1) — Passive error prevention
5. **AI-specific instructions** (D2) — Highest leverage documentation investment
6. **Branch protection** (V1) — Safety net for agent output

### For Tracking Over Time

Run the scorecard monthly. Track:
- Overall score trend per repository
- Category-level trends (identify systemic gaps)
- Tier transitions (celebrate when repos move up a tier)
- Cross-repo comparisons (identify teams that could share practices)
