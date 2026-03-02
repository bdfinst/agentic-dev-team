# Agent-Readiness Scanner — Implementation Plan

An automated tool that scans repositories across Azure DevOps and Jenkins environments, scores them against the [Agent-Readiness Scorecard](agent-readiness-scorecard.md), and produces a dashboard report.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI / Scheduler                         │
│  (manual run, cron, Azure Pipeline, or Jenkins scheduled job)│
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator                               │
│  - Discovers repos via Azure DevOps REST API or Jenkins API  │
│  - Clones each repo (shallow) to temp directory              │
│  - Runs analyzer pipeline per repo                           │
│  - Aggregates results                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐┌────────────┐┌────────────┐
   │  Repo      ││  Repo      ││  Repo      │  (parallel)
   │  Analyzer  ││  Analyzer  ││  Analyzer  │
   └─────┬──────┘└─────┬──────┘└─────┬──────┘
         │             │             │
         ▼             ▼             ▼
   ┌─────────────────────────────────────────┐
   │          Category Analyzers             │
   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
   │  │ Test │ │Build │ │Code  │ │Type  │   │
   │  │Infra │ │& Env │ │Qual. │ │Safety│   │
   │  └──────┘ └──────┘ └──────┘ └──────┘   │
   │  ┌──────┐ ┌──────┐                     │
   │  │ Docs │ │ VCS  │                     │
   │  │      │ │Safety│                     │
   │  └──────┘ └──────┘                     │
   └─────────────────┬───────────────────────┘
                     │
                     ▼
   ┌─────────────────────────────────────────┐
   │            Report Generator             │
   │  - JSON results per repo                │
   │  - Markdown summary report              │
   │  - HTML dashboard (optional)            │
   │  - Azure DevOps Wiki push (optional)    │
   └─────────────────────────────────────────┘
```

---

## Technology Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | **Python 3.12+** | Best ecosystem for file analysis, REST APIs, and report generation. Rich SDKs for both ADO and Jenkins. |
| CI Platform APIs | **azure-devops Python SDK** + **python-jenkins** / Jenkins REST API | ADO SDK covers repo/project discovery. Jenkins API covers job/build data. Platform auto-detected or specified in config. |
| Git operations | **Shallow clones via CLI** (`git clone --depth 1`) | Minimize disk and time. We only need file presence and content, not full history. |
| Static analysis | **radon** (Python complexity), **ts-morph** (TS analysis), or line-count heuristics | Keep dependencies minimal; shell out to language-specific tools only when present. |
| Report output | **JSON** (machine-readable) + **Markdown** (human-readable) | JSON feeds dashboards; Markdown works in Azure DevOps Wiki, Jenkins dashboard, PRs, and Slack. |
| Dashboard | **Power BI**, **Azure DevOps Wiki**, or **Jenkins HTML Publisher** | Power BI for interactive dashboards from JSON; Wiki/HTML Publisher for lightweight static reports. |
| Scheduling | **Azure Pipeline (cron)**, **Jenkins scheduled job**, or **local cron** | Run nightly or weekly; store results as pipeline artifacts. |

---

## Component Design

### 1. Repository Discovery

```
Input:  CI platform config (ADO org URL + PAT, or Jenkins URL + credentials)
Output: List of (project, repo_name, default_branch, clone_url)
```

**Azure DevOps mode:**
- Use `azure-devops` SDK `GitClient.get_repositories()` per project
- Filter options: include/exclude by project name, repo name regex, last-activity date
- Skip archived/disabled repositories

**Jenkins mode:**
- Use Jenkins REST API (`/api/json?tree=jobs[name,url,scm]`) to discover jobs and their SCM configurations
- Extract Git repo URLs from job SCM config (supports Git, GitHub, Bitbucket, ADO Git)
- Filter options: include/exclude by job name regex, folder path, last-build date
- Skip disabled jobs
- Deduplicate repos that appear in multiple jobs

**Common:**
- Support scanning a single repo by URL (for local dev/testing)
- Platform auto-detected from config or specified via `--platform` CLI flag

### 2. Repository Cloner

```
Input:  clone_url, branch
Output: temp directory path with repo contents
```

- Shallow clone (`--depth 1 --single-branch`) to minimize I/O
- Use temp directories, cleaned up after analysis
- Authenticate via Git credential helper using the PAT
- Parallelize across repos (configurable concurrency, default 4)

### 3. Category Analyzers

Each analyzer is a self-contained module that receives a repo root path and returns a dict of criterion scores.

#### 3a. Test Infrastructure Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| T1 — Coverage | Parse CI config for coverage report steps. Check for `.nycrc`, `pytest.ini` with `--cov`, `jacoco` in `pom.xml`. If coverage reports exist as CI artifacts, fetch the latest via ADO Build Artifacts API or Jenkins `lastSuccessfulBuild/artifact` endpoint. Score: 0 if no coverage config, 1 if config present, 2 if config present AND last coverage report shows > 60%. |
| T2 — Reliability | **ADO**: Query test results API for the last 30 pipeline runs. **Jenkins**: Query test result trend via `/api/json?tree=builds[result,actions[totalCount,failCount]]` for last 30 builds, or parse JUnit XML artifacts. Calculate per-test pass/fail variance. Score: 0 if > 10% flaky rate, 1 if 2-10%, 2 if < 2%. Falls back to score 1 if no test result data available. |
| T3 — Speed | **ADO**: Query pipeline API for test stage duration over last 10 runs. **Jenkins**: Query build durations via `/api/json?tree=builds[duration]` for last 10 builds; if test stage is a separate build step, parse `wfapi` (Pipeline/Workflow API) for stage-level timing. Score: 0 if median > 15 min, 1 if 5-15 min, 2 if < 5 min. Falls back to score 1 if not measurable. |
| T4 — Single command | Check for test scripts in `package.json` (`test` script), `Makefile` (`test` target), `tox.ini`, `pytest.ini`, `build.gradle` (test task). Score: 0 if none found, 1 if present but requires env setup (detected via `.env.example` or docker-compose dependency), 2 if straightforward command detected. |
| T5 — Test types | Scan for directory patterns: `**/test/**`, `**/tests/**`, `**/__tests__/**`, `**/e2e/**`, `**/integration/**`, `**/spec/**`. Classify by path convention. Score: 0 if only one type or none, 1 if two types, 2 if three+. |

#### 3b. Build & Dev Environment Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| B1 — Single command build | Check for `Makefile` (build target), `package.json` (build script), `Dockerfile`, `build.gradle`, `pom.xml`. Score: 0 if none, 1 if present but no CI build step matches, 2 if build script present AND CI uses it (detected from ADO pipeline YAML or Jenkinsfile). |
| B2 — Reproducible environment | Check for `Dockerfile`, `.devcontainer/devcontainer.json`, `flake.nix`, `docker-compose.yml`. Score: 0 if none, 1 if Dockerfile only, 2 if devcontainer or Nix or Docker Compose. |
| B3 — Dependency management | Check for lock files: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Pipfile.lock`, `go.sum`, `Cargo.lock`, `composer.lock`. Score: 0 if no lock file, 1 if lock file exists but `.gitignore` excludes it, 2 if lock file committed. |
| B4 — CI pipeline | Detect CI config: `.azure-pipelines.yml`, `azure-pipelines/*.yml`, `Jenkinsfile`, `Jenkinsfile.*`, `jenkins/*.groovy`, `.github/workflows/*.yml`, `.gitlab-ci.yml`. Parse for build, test, lint steps. For Jenkinsfiles, detect `stage` blocks and `sh`/`bat` commands for build/test/lint invocations. Score: 0 if no CI, 1 if CI but missing test or lint, 2 if CI runs build + test + lint. |

#### 3c. Code Quality & Consistency Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| C1 — Formatting | Check for `.prettierrc*`, `.editorconfig`, `rustfmt.toml`, `pyproject.toml` (black/ruff format config). Check CI config for format-check step. Score: 0 if no formatter, 1 if config present but no CI enforcement, 2 if CI enforces. |
| C2 — Linting | Check for `.eslintrc*`, `ruff.toml`, `pylintrc`, `.golangci.yml`, `clippy` in Cargo config. Check CI for lint step. Score: 0 if no linter, 1 if config but no CI, 2 if CI enforces. |
| C3 — Architecture patterns | Check for structural conventions: `src/domain/`, `src/application/`, `src/infrastructure/` (hexagonal); `controllers/`, `models/`, `views/` (MVC); `cmd/`, `internal/`, `pkg/` (Go convention). Check for architecture docs in `docs/`. Score: 0 if flat structure, 1 if some structure visible, 2 if recognizable pattern + documented. **Flag for manual review.** |
| C4 — Module size | Compute line counts for all source files (exclude generated, vendor, node_modules). Score: 0 if p90 > 500 lines, 1 if p90 300-500 lines, 2 if p90 < 300 lines. Optionally run `radon` for Python complexity if available. |
| C5 — Naming conventions | Check linter config for naming rules (e.g., `@typescript-eslint/naming-convention`, pylint `naming-style`). Score: 0 if no naming rules, 1 if some rules, 2 if comprehensive naming rules enforced. |

#### 3d. Type Safety & Contracts Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| S1 — Type system | For TS: check `tsconfig.json` for `strict: true`. For Python: check for `mypy.ini`, `pyrightconfig.json`, or `pyproject.toml` mypy/pyright section. For Java/C#/Go/Rust: score 2 (inherently typed). Score: 0 if dynamic with no hints, 1 if partial, 2 if strict. |
| S2 — API contracts | Check for `openapi.yaml`, `openapi.json`, `swagger.*`, `*.proto`, `*.graphql`, `schema.json`. Check for validation libraries in dependencies (`zod`, `joi`, `pydantic`, `marshmallow`). Score: 0 if none, 1 if validation library only, 2 if schema files present + validation. |
| S3 — Interface-driven design | Count interface/abstract class definitions relative to total classes. Check for dependency injection config (`inversify`, `tsyringe`, Spring annotations, `.NET DI`). Score: 0 if no interfaces, 1 if some, 2 if prevalent. **Flag for manual review.** |
| S4 — Database schema management | Check for migration directories: `migrations/`, `alembic/`, `db/migrate/`, `flyway/`, `liquibase/`. Check for ORM config (`prisma/schema.prisma`, `typeorm`, `sqlalchemy`). Score: 0 if none, 1 if ORM but no explicit migrations, 2 if migration history present. |

#### 3e. Documentation & Context Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| D1 — README | Check for `README.md`. Parse for setup/build/test section headers. Score: 0 if missing, 1 if present but < 200 words or no setup section, 2 if > 200 words with setup/build/test sections. |
| D2 — AI instructions | Check for `CLAUDE.md`, `.claude/CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, `AGENTS.md`, `CODING_GUIDELINES.md`. Score: 0 if none, 1 if basic (< 100 words), 2 if detailed (> 100 words with specific guidance). |
| D3 — Architecture docs | Check for `docs/adr/`, `docs/architecture*`, `docs/design*`, `ARCHITECTURE.md`. Score: 0 if none, 1 if present but files older than 1 year, 2 if present and recently updated. |
| D4 — Domain context | Check for `docs/domain*`, `docs/glossary*`, `GLOSSARY.md`, domain model files. Score: 0 if none, 1 if minimal, 2 if documented glossary or domain model. **Flag for manual review.** |

#### 3f. Version Control & Safety Nets Analyzer

| Criterion | Automated Detection |
|-----------|-------------------|
| V1 — Branch protection | **ADO**: Query Branch Policy API for default branch. Check for minimum reviewers policy, build validation policy. **Jenkins**: Not directly applicable (Jenkins doesn't manage branch policies). Check for GitHub/Bitbucket branch protection via SCM provider API if credentials are available, or fall back to checking for PR-based build triggers in Jenkinsfile (e.g., `when { branch 'main' }`, multibranch pipeline config). Score: 0 if no policies, 1 if some but incomplete, 2 if min reviewers + build validation both set. Falls back to score 1 for Jenkins if not determinable. |
| V2 — Pre-commit hooks | Check for `.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`, `.lintstagedrc*`. Score: 0 if none, 1 if partial (e.g., only format), 2 if comprehensive (format + lint + test). |
| V3 — Commit conventions | Check for `commitlint.config.*`, `.commitlintrc.*`, commit-msg hook in `.husky/`. Optionally sample last 20 commit messages for pattern consistency. Score: 0 if no convention tooling, 1 if tooling present but not enforced in CI, 2 if enforced. |
| V4 — Dependency scanning | Check for `.github/dependabot.yml`, `.snyk`, `renovate.json`, Azure DevOps Advanced Security config. Score: 0 if none, 1 if one tool configured, 2 if scanning + auto-PR creation configured. |

---

## Output Format

### Per-Repository JSON

```json
{
  "repository": "acispeedpay/payment-service",
  "project": "acispeedpay",
  "scanned_at": "2026-02-20T14:30:00Z",
  "scanner_version": "1.0.0",
  "overall_score": 63.25,
  "tier": "Agent-Assisted",
  "categories": {
    "test_infrastructure": {
      "weight": 0.25,
      "score_pct": 60.0,
      "weighted_score": 15.0,
      "criteria": {
        "T1_coverage": { "score": 2, "max": 2, "evidence": "pytest --cov in CI, last report: 72%" },
        "T2_reliability": { "score": 1, "max": 2, "evidence": "3 flaky tests in last 30 runs (6%)" },
        "T3_speed": { "score": 1, "max": 2, "evidence": "median test duration: 8m 12s" },
        "T4_single_command": { "score": 2, "max": 2, "evidence": "Makefile test target found" },
        "T5_test_types": { "score": 0, "max": 2, "evidence": "only tests/ directory found (1 type)" }
      }
    }
  },
  "manual_review_flags": [
    { "criterion": "C3", "reason": "Architecture pattern detection is heuristic-based" },
    { "criterion": "S3", "reason": "Interface prevalence requires human judgment" },
    { "criterion": "D4", "reason": "Domain documentation quality needs expert review" }
  ],
  "improvement_suggestions": [
    { "criterion": "T5", "current": 0, "action": "Add integration and e2e test directories" },
    { "criterion": "T2", "current": 1, "action": "Investigate 3 flaky tests: [list]" }
  ]
}
```

### Summary Report (Markdown)

Generated as a Markdown table suitable for Azure DevOps Wiki, Jenkins HTML Publisher, or PR comments:

```markdown
# Agent-Readiness Report — 2026-02-20

## Overview
| Tier | Count |
|------|-------|
| Agent-Ready (75-100) | 4 |
| Agent-Assisted (50-74) | 12 |
| Agent-Limited (25-49) | 7 |
| Agent-Hostile (0-24) | 2 |

## Repository Scores
| Repository | Score | Tier | Test | Build | Quality | Types | Docs | VCS |
|------------|-------|------|------|-------|---------|-------|------|-----|
| payment-service | 78.5 | Ready | 80% | 100% | 70% | 62% | 75% | 87% |
| legacy-batch | 31.0 | Limited | 20% | 50% | 30% | 0% | 25% | 50% |
| ... | | | | | | | | |

## Top Improvement Opportunities
1. **legacy-batch**: Add any test coverage (T1) — would move score from 31 → ~44
2. **user-portal**: Add TypeScript strict mode (S1) — would move score from 68 → 75
```

---

## Project Structure

```
agent-readiness-scanner/
├── pyproject.toml                 # Project config, dependencies
├── README.md
├── src/
│   └── scanner/
│       ├── __init__.py
│       ├── cli.py                 # CLI entry point (click or typer)
│       ├── config.py              # Scanner configuration (org, PAT, filters)
│       ├── orchestrator.py        # Discovers repos, fans out analysis
│       ├── cloner.py              # Shallow clone + cleanup
│       ├── scorer.py              # Weight application, tier calculation
│       ├── analyzers/
│       │   ├── __init__.py
│       │   ├── base.py            # Analyzer interface
│       │   ├── test_infra.py      # T1-T5
│       │   ├── build_env.py       # B1-B4
│       │   ├── code_quality.py    # C1-C5
│       │   ├── type_safety.py     # S1-S4
│       │   ├── documentation.py   # D1-D4
│       │   └── vcs_safety.py      # V1-V4
│       ├── ci_platforms/
│       │   ├── __init__.py
│       │   ├── base.py            # CI platform interface (abstract)
│       │   ├── azure_devops/
│       │   │   ├── __init__.py
│       │   │   ├── client.py      # Azure DevOps API wrapper
│       │   │   ├── repos.py       # Repo discovery
│       │   │   ├── pipelines.py   # CI pipeline data
│       │   │   └── policies.py    # Branch policies
│       │   └── jenkins/
│       │       ├── __init__.py
│       │       ├── client.py      # Jenkins API wrapper
│       │       ├── repos.py       # Repo discovery from job SCM config
│       │       ├── pipelines.py   # Build/test data from Jenkins builds
│       │       └── jenkinsfile_parser.py  # Parse Jenkinsfile stages
│       └── reporting/
│           ├── __init__.py
│           ├── json_report.py     # JSON output
│           ├── markdown_report.py # Markdown summary
│           └── trend.py           # Historical comparison
├── tests/
│   ├── conftest.py
│   ├── fixtures/                  # Sample repo structures for testing
│   │   ├── repo_minimal/
│   │   ├── repo_well_configured/
│   │   └── repo_typescript_strict/
│   ├── test_analyzers/
│   │   ├── test_test_infra.py
│   │   ├── test_build_env.py
│   │   ├── test_code_quality.py
│   │   ├── test_type_safety.py
│   │   ├── test_documentation.py
│   │   └── test_vcs_safety.py
│   ├── test_scorer.py
│   └── test_orchestrator.py
├── scorecard.yaml                 # Scoring weights + thresholds (configurable)
├── azure-pipeline.yml             # Scheduled pipeline for nightly scans (ADO)
└── Jenkinsfile                    # Scheduled pipeline for nightly scans (Jenkins)
```

---

## Configuration File (`scorecard.yaml`)

Externalizes weights and thresholds so they can be tuned without code changes:

```yaml
version: "1.0"

platform: "azure_devops"              # "azure_devops" or "jenkins"

azure_devops:                         # used when platform: "azure_devops"
  organization: "acispeedpayportfolio"
  projects: ["acispeedpay"]           # or ["*"] for all
  exclude_repos: ["archived-*", "test-*"]
  pat_env_var: "ADO_PAT"             # env var name containing the PAT

jenkins:                              # used when platform: "jenkins"
  url: "https://jenkins.example.com"
  credentials_env_var: "JENKINS_TOKEN" # env var name containing API token
  username_env_var: "JENKINS_USER"     # env var name containing username
  folders: ["acispeedpay"]             # or ["*"] for all top-level folders
  exclude_jobs: ["archived-*", "test-*"]
  scm_credentials_id: "git-creds"     # Jenkins credential ID for Git clones (optional)

clone_concurrency: 4

weights:
  test_infrastructure: 0.25
  build_env: 0.20
  code_quality: 0.20
  type_safety: 0.15
  documentation: 0.10
  vcs_safety: 0.10

tiers:
  agent_ready: 75
  agent_assisted: 50
  agent_limited: 25

thresholds:
  coverage_high: 60          # % for score 2
  coverage_low: 20           # % for score 1
  test_speed_fast: 300       # seconds for score 2
  test_speed_slow: 900       # seconds for score 1
  flaky_rate_low: 2          # % for score 2
  flaky_rate_high: 10        # % for score 1
  file_size_p90_small: 300   # lines for score 2
  file_size_p90_large: 500   # lines for score 1
  readme_min_words: 200      # words for score 2
  ai_instructions_min_words: 100

reporting:
  output_dir: "./reports"
  formats: ["json", "markdown"]
  history_file: "./reports/history.jsonl"  # append each run for trending
```

---

## Implementation Phases

### Phase 1 — Foundation (Week 1-2)

**Goal**: Scan a single repo end-to-end and produce a JSON report.

1. Project scaffolding (`pyproject.toml`, `src/`, `tests/`)
2. CI platform abstraction layer (`CIPlatform` interface)
3. Azure DevOps client — repo discovery and shallow clone
4. Jenkins client — repo discovery from job SCM config and shallow clone
5. Base analyzer interface
6. File-presence analyzers (B2, B3, C1, C2, D1, D2, V2, V3, V4) — these only check if files exist
7. Scorer — weight application, tier calculation
8. JSON report output
9. Tests with fixture repos

**Deliverable**: `scanner scan --repo payment-service` produces JSON output.

### Phase 2 — CI-Aware Analyzers (Week 3-4)

**Goal**: Analyzers that read CI config and query CI platform APIs (ADO and Jenkins).

1. CI platform abstraction layer — common interface for pipeline data across ADO and Jenkins
2. CI config parser — detect build/test/lint steps in Azure Pipelines YAML and Jenkinsfiles
3. ADO pipeline API + Jenkins build API — test duration, pass rates
4. ADO test results API + Jenkins JUnit results — flaky test detection
5. ADO branch policy API + Jenkins multibranch config — branch protection scoring
6. Coverage report fetching from pipeline artifacts (ADO artifacts API / Jenkins artifact endpoint)
7. Full scoring for T1-T5, B1, B4, V1

**Deliverable**: `scanner scan --project acispeedpay` scores all repos with CI data from either platform.

### Phase 3 — Code Analysis (Week 5-6)

**Goal**: Analyzers that read and analyze source code.

1. File line count distribution (C4)
2. Language detection and type system analysis (S1)
3. API schema detection (S2)
4. Interface/DI pattern detection (S3)
5. Migration directory analysis (S4)
6. Test type classification by directory structure (T5)
7. Architecture pattern heuristics (C3)

**Deliverable**: All 26 criteria scored automatically (with manual review flags).

### Phase 4 — Reporting & Dashboard (Week 7-8)

**Goal**: Human-readable reports and historical trending.

1. Markdown summary report generator
2. Historical JSONL storage and trend comparison
3. Improvement suggestions engine (identify highest-impact changes per repo)
4. Azure DevOps Wiki push (optional) or Jenkins HTML Publisher report (optional)
5. Power BI template or simple HTML dashboard
6. Azure Pipeline or Jenkins scheduled job for nightly/weekly runs

**Deliverable**: Automated nightly scan → Wiki/Jenkins report + dashboard.

### Phase 5 — Refinement (Ongoing)

- Tune thresholds based on real data across repos
- Add manual override file (`.agent-readiness-overrides.yaml` in repo) for criteria that can't be auto-detected
- PR comment integration — post score diff when CI config or test structure changes
- Alerting — notify teams when score drops below a threshold

---

## CI Platform API Endpoints Used

### Azure DevOps

| Purpose | API | SDK Method / REST Path |
|---------|-----|----------------------|
| List projects | Core | `GET {org}/_apis/projects` |
| List repos in project | Git | `GitClient.get_repositories(project)` |
| Clone repo | Git CLI | `git clone --depth 1 {clone_url}` |
| Branch policies | Policy | `GET {org}/{project}/_apis/policy/configurations?scope.repositoryId={id}` |
| Pipeline runs | Pipelines | `GET {org}/{project}/_apis/pipelines/{id}/runs` |
| Pipeline artifacts | Build | `GET {org}/{project}/_apis/build/builds/{id}/artifacts` |
| Test results | Test | `GET {org}/{project}/_apis/test/runs?minLastUpdatedDate={date}` |
| Test result details | Test | `GET {org}/{project}/_apis/test/runs/{runId}/results` |

**Authentication**: Personal Access Token (PAT) with scopes: `Code (Read)`, `Build (Read)`, `Test Management (Read)`, `Project and Team (Read)`.

### Jenkins

| Purpose | API | REST Path |
|---------|-----|-----------|
| List jobs/folders | Remote API | `GET {url}/api/json?tree=jobs[name,url,scm,disabled,lastBuild[timestamp]]` |
| Job SCM config | Remote API | `GET {url}/job/{name}/api/json?tree=scm[userRemoteConfigs[url],branches[name]]` |
| Clone repo | Git CLI | `git clone --depth 1 {scm_url}` |
| Build history | Remote API | `GET {url}/job/{name}/api/json?tree=builds[number,result,duration,timestamp]{0,30}` |
| Build artifacts | Remote API | `GET {url}/job/{name}/{build}/artifact/{path}` |
| Test results | Remote API | `GET {url}/job/{name}/{build}/testReport/api/json` |
| Pipeline stages | Workflow API | `GET {url}/job/{name}/{build}/wfapi/describe` |
| Multibranch config | Remote API | `GET {url}/job/{name}/api/json?tree=sources[source[remote,includes]]` |

**Authentication**: API token with username (`user:token` as Basic Auth), or Jenkins-Crumb for CSRF-protected instances. Required permissions: `Overall/Read`, `Job/Read`, `Job/ExtendedRead` (to view SCM config).

---

## Key Design Decisions

**1. Shallow clones, not API-only file listing**
Azure DevOps Items API can list/read files, but it requires one API call per file. Jenkins has no file-listing API at all. A shallow clone gets all files in one operation and allows running local tools (line counts, regex scans). Tradeoff: more disk I/O, but massively fewer API calls and works identically across CI platforms.

**2. Evidence strings on every score**
Every criterion score includes a human-readable `evidence` field explaining why that score was assigned. This is critical for trust — teams need to understand and dispute scores. It also makes the manual review process efficient.

**3. External config for weights and thresholds**
Weights will need tuning as you learn what actually correlates with agent success in your specific environment. Hardcoding them would require code changes for every adjustment. The YAML config makes it a data problem.

**4. Manual review flags, not manual scores**
The scanner scores everything automatically but flags criteria where the heuristic is weak (C3, S3, D4). This keeps the process automated while being transparent about confidence. Manual overrides can be committed per-repo.

**5. JSONL history for trending**
Each scan run appends to a `history.jsonl` file. This enables trend charts without needing a database. Power BI and pandas both read JSONL natively.

**6. CI platform abstraction layer**
Both Azure DevOps and Jenkins provide pipeline, test, and artifact data but through very different APIs. A common `CIPlatform` interface abstracts repo discovery, build history, test results, and artifact fetching behind a uniform contract. Each platform implements this interface. The analyzer layer never calls platform-specific APIs directly — it only consumes the abstraction. This means adding a third CI platform (GitHub Actions, GitLab CI) later is a single new implementation, not a cross-cutting change.

**7. Jenkins repo discovery via SCM config, not manual mapping**
Jenkins doesn't have a built-in "repository" concept — repos are configured per-job in SCM settings. The scanner extracts Git URLs from job configs, deduplicates across jobs (the same repo may appear in build, deploy, and test jobs), and associates all related jobs with a single repo entry. This avoids requiring users to manually list repos when using Jenkins.
