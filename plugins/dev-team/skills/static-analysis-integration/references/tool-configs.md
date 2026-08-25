# Tool Configurations (SARIF-first)

Per-tool invocation commands, install hints, and adapter-specific notes. Organized by tier per the skill's `## Tool tiers` section.

## Tier 1 — required baseline (SARIF native)

### semgrep

```bash
semgrep scan \
  --sarif \
  --config auto \
  --quiet \
  <target-paths>
```

- **Install**: `pip install semgrep`
- **Install hint**: `semgrep — SAST. install: pip install semgrep`
- **Detection**: `command -v semgrep`
- **Capability tier**: SAST
- **Adapter**: none; consumed raw by the shared SARIF parser.

### gitleaks

```bash
gitleaks detect \
  --report-format sarif \
  --report-path - \
  --no-verify \
  --source <path>
```

- **Install**: `brew install gitleaks` (macOS) / `docker run --rm -v "$PWD:/path" zricethezav/gitleaks:latest detect ...`
- **Install hint**: `gitleaks — secrets detection. install: brew install gitleaks`
- **Detection**: `command -v gitleaks`
- **Capability tier**: secrets
- **Offline posture**: `--no-verify` disables gitleaks' active-credential verification, which would otherwise make outbound API calls (e.g. to AWS/GitHub) to confirm a detected secret is live. Detection is purely pattern-based and runs with zero network egress. Always on — this flag carries no detection cost.
- **Adapter**: none.

### trivy

```bash
# IaC scanning
trivy config \
  --format sarif \
  --output /dev/stdout \
  --skip-update \
  --offline-scan \
  <path>

# Filesystem / supply-chain scanning
trivy fs \
  --format sarif \
  --output /dev/stdout \
  --scanners vuln,config,secret \
  --skip-update \
  --offline-scan \
  <path>
```

- **Install**: `brew install trivy`
- **Install hint**: `trivy — IaC + supply-chain scanning. install: brew install trivy`
- **Detection**: `command -v trivy`
- **Capability tier**: IaC + supply-chain
- **Offline posture**: both `trivy config` and `trivy fs` run with `--skip-update --offline-scan`. `--skip-update` pins trivy to the local vulnerability DB (no DB refresh over the network); `--offline-scan` suppresses the remote metadata lookups trivy otherwise performs for some package ecosystems. Run the **offline DB preflight** below before dispatch.
- **Offline DB preflight**: locate the local DB at trivy's cache path (`${TRIVY_CACHE_DIR:-$HOME/.cache/trivy}/db/trivy.db`) and check its `mtime`:
  - **absent** → skip trivy, warn `trivy local DB missing — run: trivy image --download-db-only`
  - **mtime age ≤ 7 days** → run normally (fresh)
  - **mtime age > 7 days** → run anyway, warn `trivy DB is N days old — consider refreshing with: trivy image --download-db-only` (substitute `N` with the integer day count)

  The 7-day boundary is inclusive: exactly 7 days old is still fresh; strictly greater than 7 days is stale. A missing or stale DB is never a hard pipeline failure.
- **Adapter**: none.

### hadolint

```bash
hadolint --format sarif <Dockerfile>
```

- **Install**: `brew install hadolint`
- **Install hint**: `hadolint — Dockerfile linting. install: brew install hadolint`
- **Detection**: `command -v hadolint`
- **Capability tier**: IaC (Dockerfile)
- **Adapter**: none.

### actionlint

actionlint does not emit SARIF directly as of its current stable release.
Invoke with JSON output and wrap with a thin adapter (≤ 15 LOC) that
produces SARIF-compliant results.

```bash
actionlint -format '{{json .}}' <target-path>
```

The adapter maps each actionlint finding:

| actionlint field | SARIF field |
|---|---|
| `.Filepath` | `results[*].locations[0].physicalLocation.artifactLocation.uri` |
| `.Line` | `results[*].locations[0].physicalLocation.region.startLine` |
| `.Column` | `results[*].locations[0].physicalLocation.region.startColumn` |
| `.Kind` | `results[*].ruleId` |
| `.Message` | `results[*].message.text` |

Severity: all actionlint findings map to `warning` by default; upgrade to
`error` if `.Kind` starts with `shellcheck` and message contains "error".

- **Install**: `brew install actionlint`
- **Install hint**: `actionlint — GitHub Actions linting. install: brew install actionlint`
- **Detection**: `command -v actionlint`
- **Capability tier**: CI-CD
- **Adapter**: thin JSON → SARIF wrapper (see `adapters/actionlint-to-sarif.sh` — created in P2 Step 3b alongside the optional adapters).

### Roslyn ErrorLog (C#)

C#'s primary static analysis (Roslyn analyzers) is built into the compiler:
`dotnet build` exports native SARIF when passed the `ErrorLog` property — a
build-flag change on the build the pipeline already runs, not a separate tool
invocation.

```bash
dotnet build /p:ErrorLog=results.sarif,version=2.1
```

- **Install**: nothing beyond the .NET SDK a C# project already requires
  (SDK ≥ 6 for built-in `dotnet format`; Roslyn 3.8+ / .NET 5 SDK or later for
  the SARIF v2.1 export). Where the SDK version matters it is repo-pinned via
  `global.json` — the .NET-native repo-level pin. No standalone install script.
- **Install hint**: `dotnet — .NET SDK (C# build, format, ErrorLog SARIF). install: https://dotnet.microsoft.com/download`
- **Detection**: `command -v dotnet` — **language-conditional**: probe and hint
  only when `.cs` files are in the target set, so a non-C# repo never sees a
  "dotnet missing" warning. A missing SDK degrades to `status: skip` with the
  hint above — never a pipeline failure.
- **Capability tier**: SAST (C# compiler + analyzer diagnostics)
- **Adapter**: none; native SARIF v2.1, consumed raw by the shared SARIF parser.
- **Reuse rule (`/code-review`)**: the full-repo pass invokes
  `dotnet build /p:ErrorLog=...` for any C# project in scope unless a SARIF
  produced from the current HEAD commit already exists (e.g. a CI artifact) —
  **same-commit** is the reuse test.
- **Incremental-build caveat**: the SARIF is rewritten only when the compiler
  actually runs; an up-to-date incremental build skips compilation and leaves
  the previous file in place (still valid for the code on disk). Pass the flag
  on **every** build invocation. A *missing* SARIF (no compile has happened
  yet) degrades to skip — never a pipeline failure.
- **Scope (v1): single-project builds.** `ErrorLog` is a per-project compiler
  property: in a multi-project solution each project's compilation writes its
  own log — a relative path resolves per project directory, and an absolute
  path is overwritten by whichever project compiles last. Multi-project
  solutions are a documented gap; the v2 plan of record is a per-project path
  via `Directory.Build.props` with `$(MSBuildProjectName)` in the ErrorLog path
  (e.g. `<ErrorLog>$(MSBuildProjectName).sarif,version=2.1</ErrorLog>` — one
  SARIF per project, no overwrite risk) plus a glob-collect.
- **Dedup-chain placement**: none needed — the only cross-duplicating source is
  semgrep, which already outranks all language-specific sources; revisit only
  if a second Java/C# source is ever added.
- **Build-time (`/build`) consumption**: the same SARIF doubles as the C#
  lane's diagnostic (verify) source — see the C# lane row under "Build-time
  lanes" below.

### pmd

```bash
pmd check -d . -R <resolved-ruleset> -f sarif --no-progress
```

- **Language-conditional**: dispatch pmd, and surface its missing-tool
  install hint, only when `.java` files are in the target set — a non-Java
  repo never sees a "pmd missing" warning (graceful-degradation constraint).
- **Install**: repo-level, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install-java-static-analysis.py`
  — installs the pinned PMD distribution into the target repo's gitignored
  `.pmd/` directory (`PMD_INSTALL_DIR` overrides). Never user-level/global.
- **Install hint**: `pmd — Java code quality. install: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install-java-static-analysis.py` (surfaced only for Java target sets)
- **Detection**: repo-local first — the `.pmd/pmd-bin-*/bin/pmd` launcher
  (`pmd.bat` on Windows) — then `command -v pmd`; verify with `pmd --version`.
- **Capability tier**: Java code quality
- **Exit codes**: `pmd check` exits 0 on clean and **4 when violations are
  found** — 4 is findings, not a tool failure; treat only other non-zero
  codes as tool errors.
- **Adapter**: none; SARIF renderer is native (PMD 6.36+; we pin 7.x) —
  consumed raw by the shared SARIF parser.
- **Dedup**: no dedup-chain slot needed — the only cross-duplicating source
  is semgrep, which already outranks all language-specific sources; revisit
  only if a second Java/C# source is added.

#### Ruleset resolution (shared by both pmd invocations)

The `/code-review` invocation above and the build-time Java lane below
resolve `<resolved-ruleset>` identically, so the two layers never disagree
about what a violation is:

1. **Repo-root `pmd-ruleset.xml`**, when present — the project override,
   matching the repo-root convention (`ruff.toml`, `.editorconfig`) the
   other lanes honor. A custom `pmd-ruleset.xml` carries its own
   `<exclude-pattern>` entries.
2. Otherwise the **plugin's quickstart-wrapping default**:
   `${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/rulesets/pmd-quickstart.xml`,
   which references PMD's documented quickstart set
   (`rulesets/java/quickstart.xml`) and ships `<exclude-pattern>` entries
   for generated-output directories — `target/`, `build/`, `out/`,
   `.gradle/` — so the full-repo walk produces no duplicate/noise findings
   on copied sources.

Test sources run the same ruleset as production code (recorded decision;
revisit with a documented exclusion list only if real-world noise shows up
on JUnit-style test classes).

### ruff

```bash
ruff check --output-format sarif .
```

- **Minimum version**: 0.3.1 — the first release with the SARIF output format.
- **Install**: `python3 -m pip install ruff` (project venv / dev requirements — repo-level, versioned with the repo; never `pip install --user` or a global pipx install)
- **Install hint**: `ruff — Python lint + autofix. install: python3 -m pip install ruff (project venv / dev requirements)`
- **Detection**: `command -v ruff`
- **Capability tier**: Python lint + autofix
- **Presence**: language-conditional, never `[REQUIRED]` — dispatch ruff, and surface its missing-tool install hint, only when `.py` files are in the target set. A non-Python repo never sees a "ruff missing" warning, consistent with the skill's "absence is never a pipeline failure" constraint.
- **Config resolution**: the project's own `ruff.toml`/`pyproject.toml` wins when present (Ruff's default config discovery — no override flags); Ruff's defaults otherwise. The plugin pins no curated rule set — the project owns its quality bar.
- **Adapter**: none; consumed raw by the shared SARIF parser.

## Tier 2 — optional SARIF adapters (shipped in P2 Step 3b)

Placeholder for the remaining Step 3b tools: checkov, kube-linter, bandit, gosec, bearer, osv-scanner, grype, trufflehog.

### oxlint

Primary JS/TS linter (Oxc project, Rust-based, ESLint-compatible) for `/code-review`'s full-repo pre-pass. Pin **oxlint >= 1.0.0**. Oxlint's CLI surface evolves quickly — verify the exact flag names (`--fix`, `--format sarif`) against the project's pinned version; verified against oxlint 1.72.0.

```bash
npx oxlint --format sarif .
```

- **Tier substitution**: #808 originally specified a Tier 3 bespoke JSON adapter (`--format json`, ≤ 40 LOC). At implementation time the pinned line had gained a native `sarif` output format (verified on 1.72.0), so per the issue's version-pin instruction oxlint lands as a SARIF-native entry instead — no adapter.
- **Install**: `npm install --save-dev oxlint` — a project devDependency pins the version in `package.json`/lockfile, versioned with the repo and reproducible for every contributor and CI. Never `npm install -g oxlint`.
- **Install hint**: `oxlint — JS/TS linting. install: npm install --save-dev oxlint`
- **Detection**: `npx --no-install oxlint --version` (or `node_modules/.bin/oxlint`) — oxlint is a project-local npm devDependency, not a global binary, so PATH probes (`command -v`) would miss it.
- **Capability tier**: JS/TS linting
- **Adapter**: none; consumed raw by the shared SARIF parser (`sarif-parser.md`), which prefixes rule ids as `oxlint.js.<rule-id>` (`runs[*].tool.driver.name` is `oxlint`; SARIF `ruleId` values look like `eslint(no-unused-vars)`).
- **Coexistence with legacy ESLint (Tier 4)**: this entry sits alongside the ESLint entry, not replacing it. When a project runs both, the same finding can arrive twice — the dedup chain (SKILL.md step 4) ranks oxlint ahead of the legacy JS tools. While both run, add [`eslint-plugin-oxlint`](https://github.com/oxc-project/eslint-plugin-oxlint) to the ESLint config to turn off ESLint rules oxlint already covers, so the ESLint pass only pays for the plugin-only remainder.

#### When a project may drop ESLint entirely

Decidable checklist — a project drops ESLint only when **all three** hold:

1. Every rule enabled in the project's ESLint config is either implemented by the pinned oxlint version (per oxlint's supported-rules list) or explicitly acknowledged in the project as not relied on.
2. No framework plugin in the ESLint config (React/Vue/Svelte/etc.) contributes an enabled rule oxlint lacks.
3. A one-time dual run over the repo shows ESLint reporting no finding that oxlint misses.

Otherwise run both, with `eslint-plugin-oxlint` suppressing the overlap. In the build-time lane's provider terms (§ Build-time lanes → JS/TS lane), this checklist is the decidable test for rebinding the autofix slot from eslint to oxlint.

## Tier 3 — bespoke JSON adapters (shipped in P2 Step 3b)

Placeholder — populated by Step 3b. Expected tools: detect-secrets, depcheck, deptry, kube-score, govulncheck. Each adapter is ≤ 40 LOC.

### mypy

```bash
mypy $(python3 adapters/mypy-src-layout.py .) --output json . 2>&1 | python3 adapters/mypy-adapter.py
```

- **Minimum version**: 1.11 — the first release with `--output json`. Older mypy rejects the flag; the adapter detects the rejection and degrades to a skip-with-warning (exit 0, zero findings) — never a pipeline failure.
- **Install**: `python3 -m pip install mypy` (project venv / dev requirements — repo-level, versioned with the repo; never `pip install --user` or a global pipx install)
- **Install hint**: `mypy — Python type checking. install: python3 -m pip install mypy (project venv / dev requirements)`
- **Detection**: `command -v mypy`
- **Capability tier**: Python type checking
- **Presence**: language-conditional, like ruff — dispatched only when `.py` files are in the target set.
- **src/-layout auto-detection**: `../adapters/mypy-src-layout.py` (invoked as `python3 adapters/mypy-src-layout.py <project-root>`) detects a plain `src/` layout — a `src/` directory holding `.py` modules with no `__init__.py` anywhere under it, and no project-level mypy package-base config (`mypy.ini`/`.mypy.ini` present, or a `[mypy]` section in `setup.cfg`/`tox.ini`, or a `[tool.mypy]` section in `pyproject.toml`) — and prints `--explicit-package-bases` (mypy >= 0.990) so mypy can resolve the layout without requiring `__init__.py` files or hand-written config. Prints nothing when the layout doesn't apply or the project already owns its mypy config ("bind, don't replace"). Without this, a project on this layout hits a stable, deterministic `mypy` failure — `Source file found twice under different module names: "calc" and "src.calc"` — the moment any checked file imports a `src/` module by its dotted `src.` path; degradation rung 4 then silently drops all mypy coverage for the run.
- **Adapter**: `../adapters/mypy-adapter.py` (≤ 40 LOC) maps mypy's JSONL diagnostics to the unified finding envelope:

| mypy JSON field | Unified finding field | Notes |
|---|---|---|
| `file` | `file` | |
| `line` | `line` | clamped to ≥ 1 |
| `column` | `column` | omitted when mypy reports no real column (`< 1`) |
| `code` | `rule_id` | Prefixed `mypy.python.<error-code>`; `mypy.python.note` when absent |
| `message` | `message` | truncated to 500 chars |
| `severity` | `severity` | `error`→`error`, `note`→`suggestion`, unknown→`info` |

### lizard

```bash
lizard --csv <target paths> | python3 adapters/lizard-adapter.py
```

- **Capability tier**: complexity metrics
- **Install**: `python3 -m pip install lizard` (project venv / dev requirements)
- **Install hint**: `lizard — complexity metrics. install: python3 -m pip install lizard (project venv / dev requirements)`
- **Detection**: `command -v lizard`
- **Presence**: not language-conditional — lizard covers ~15 languages (C/C++, C#, Java, JS/TS, Python, Go, Ruby, PHP, Swift, Kotlin, Rust, Scala, Lua, Objective-C, TTCN-3), so it is probed on every target set.
- **Never pass `--warnings_only`**: it overrides `--csv` and emits clang-style text the adapter cannot parse (verified against lizard 1.24.0). Thresholds are applied by the adapter, not by lizard.
- **Exit codes**: plain `--csv` exits 0 even when functions are over threshold; a non-zero exit means lizard itself failed. (`--warnings_only`, which this lane does not use, exits 1 on any warning.)
- **Adapter**: `../adapters/lizard-adapter.py` (≤ 40 LOC) emits one finding per **threshold breach** (strictly greater than), so a clean tree produces none:

| lizard CSV column (0-indexed) | Threshold | `rule_id` | Notes |
|---|---|---|---|
| 1 — CCN | > 10 | `lizard.complexity.cyclomatic` | fires on 10.3% of this repo's functions |
| 4 — length | > 60 | `lizard.complexity.function-length` | function length in lines; 6.1% |
| 3 — PARAM | > 5 | `lizard.complexity.parameter-count` | 1.4% |
| 6 — file | — | `file` | absolute paths are relativized to cwd; run from the repo root |
| 9 / 10 — start / end | — | `line` / `end_line` | clamped to ≥ 1 |
| 7 — name | — | `message` prefix | the function name |

  All findings carry `severity: warning` and `metadata.confidence: high` (a measurement, not a judgment), plus `metadata.metric`/`value`/`threshold` so a consumer can re-derive the comparison. Thresholds live in the adapter's `_CHECKS` table.

- **Thresholds are calibrated, not guessed.** Measured over this repo's own `hooks/` + `scripts/` tree (1,247 functions): CCN p50=3 / p90=11, length p50=14 / p95=67, param p50=1 / p99=6. Each threshold sits near that tail, so the lane flags outliers instead of describing the median. Re-measure before moving one.

- **Nesting depth is deliberately NOT covered here.** lizard's only nesting-ish metric is `-Ens`'s *nested-structure complexity*, and it is not max nesting depth: verified on lizard 1.24.0, a function with three sequential one-level `if`s scores **5** while a two-level nested one scores **2**. It is cumulative, so it scales with function size — over the same 1,247-function tree its median is **9**, and a threshold of 6 fired on **57%** of all functions. There is no fixed threshold that means "deeply nested", so the lane omits the metric rather than shipping a noisy one under a misleading name. **Max nesting depth is not a metric lizard exposes** — for JS/TS it is covered by ESLint's `max-depth` rule; elsewhere it remains a judgment call for `complexity-review`, which is part of why that lens keeps a charter after this lane lands.

### jscpd

```bash
jscpd --reporters json --output <report-dir> --silent <target paths> \
  && python3 adapters/jscpd-adapter.py < <report-dir>/jscpd-report.json
```

- **Capability tier**: copy-paste duplication detection
- **Install**: `npm install -g jscpd`
- **Install hint**: `jscpd — copy-paste duplication detection. install: npm install -g jscpd`
- **Detection**: `command -v jscpd`
- **Presence**: not language-conditional — jscpd tokenizes ~150 formats.
- **The JSON reporter writes a FILE, never stdout** (`<output>/jscpd-report.json`, verified against jscpd 5.0.16), which is why the lane redirects the file into the adapter rather than piping the command. `--silent` suppresses the console reporter's own summary; it does not redirect the report.
- **Exit code** is 0 for a normal run regardless of clones found; it is non-zero only when a `--threshold` is configured and exceeded. Do not read a clone count from the exit status.
- **Adapter**: `../adapters/jscpd-adapter.py` (≤ 40 LOC) emits **one** finding per clone, anchored at `firstFile`, with `secondFile` named in the message — not two findings, so a clone pair is not double-counted:

| jscpd report field | Unified finding field | Notes |
|---|---|---|
| `duplicates[].firstFile.name` | `file` | relativized to cwd |
| `duplicates[].firstFile.start` / `.end` | `line` / `end_line` | clamped to ≥ 1 |
| `duplicates[].secondFile.*` | `message`, `metadata.duplicate_of` | the other location |
| `duplicates[].lines` / `.tokens` | `message` | clone size |
| `duplicates[].format` | `metadata.format` | |
| `duplicates[].fragment` | **dropped** | see below |

- **Shared helper**: both this adapter and lizard's normalize paths through `../adapters/_envelope.py`'s `rel()`. Adapters run as standalone scripts, so `sys.path[0]` is the adapters directory and a plain `import _envelope` resolves with no path manipulation. It exists because two byte-identical copies of that function were exactly the finding this duplication lane reports.
- **`fragment` is deliberately never copied into the finding.** It holds the duplicated source verbatim, and these findings are injected into every review agent's prompt — echoing both copies of every clone into that context is precisely the token cost this lane exists to remove.
- **Malformed input degrades to a skip**: a report that is not valid JSON produces a `WARN` on stderr, zero findings, and exit 0 — never a pipeline failure, per the skill's graceful-degradation constraint.

## Tier 4 — legacy (pre-SARIF)

### ESLint

```bash
npx eslint -f json <target-js-ts-files>
```

| ESLint JSON field | Unified finding field | Notes |
|---|---|---|
| `filePath` | `file` | |
| `messages[].line` | `line` | |
| `messages[].ruleId` | `rule_id` | Prefixed as `eslint.js.<rule-id>` |
| `messages[].message` | `message` | |
| `messages[].severity` (1=warn, 2=error) | `severity` | 1→`warning`, 2→`error` |

### TypeScript compiler

```bash
npx tsc --noEmit 2>&1
```

Output is line-based diagnostics; the legacy adapter parses
`<file>(line,col): error TSNNNN: <message>` entries and maps to
`rule_id: tsc.ts.ts<NNNN>`.

Legacy adapters emit the same unified finding envelope as SARIF tools. Migrate to SARIF-native invocation when upstream support lands.

## Build-time lanes

The registry for `/build`'s static self-heal pass: one subsection per
language lane, filled in by the issue that registers the lane with the lane's
file extensions, each capability slot's (**autofix** / **diagnostic**)
ordered provider list — default provider first; it doubles as the last-resort
provider named by install hints — and each provider's detection probe
(repo-local locations first, then PATH).

Everything else — what a lane is, scoping, the shared fix loop, the
2-attempt cap, detection/provider binding, the provider qualification
contract, the degradation ladder, granularity, and ordering — is specified
once, in `${CLAUDE_PLUGIN_ROOT}/skills/build/references/static-self-heal.md`.
Rows registered here must satisfy that contract and must not restate the
mechanism. User-facing setup for each lane lives in
[`language-setup.md`](language-setup.md).

A language whose subsection still reads "No lane registered" is skipped by
the self-heal pass with one info line — never a failure.

### Python lane

- **Extensions**: `.py`
- **Autofix slot** — ordered provider list:
  1. **ruff** (default, last-resort provider) — probe `command -v ruff`. Qualification: qualified.
     - Fix (mechanical pre-fix): `ruff check --fix <scoped-files>`
     - Verify (check mode): `ruff check <scoped-files>`
     - Honors the project's `ruff.toml`/`pyproject.toml` when present; Ruff defaults otherwise — no plugin-curated rule set.
  2. **black + flake8** — qualifies only as a **combined pair**: black fills the format-autofix half (`black <scoped-files>`), flake8 the lint-diagnostic half (`flake8 <scoped-files>`). Probes `command -v black` **and** `command -v flake8`; both must be present for the pair to bind. Qualification: qualified as a pair, with a recorded caveat — a **partial mapping**, not 1:1 with ruff's rule surface; the binding info line must say so.
- **Diagnostic slot** — ordered provider list:
  1. **mypy** (default, last-resort provider) — probe `command -v mypy`. Qualification: qualified; diagnostic-only — no autofix, no mechanical pre-fix; findings go to the coding agent inside the shared fix loop.
     - Verify: `mypy $(python3 adapters/mypy-src-layout.py <project-root>) --follow-imports=silent <scoped-files>`
     - `--follow-imports=silent` keeps a scoped run honest: imported modules are still analyzed for type context, but errors are reported only in the scoped files — without it a scoped pass reports errors in unchanged followed modules, polluting the loop.
     - The `$(...)` prefix is the src/-layout auto-detection documented in the mypy Tier 3 entry above (`../adapters/mypy-src-layout.py`) — prints `--explicit-package-bases` when the project needs it, nothing otherwise. Same detection, same script, for both the build-time lane and the `/code-review` backstop.
  2. **pyright** — Qualification: **gated** — machine-readable output qualifies it in principle, but recognition requires a ≤ 40 LOC Tier 3 adapter in this skill's `adapters/`, which does not exist yet; until that adapter lands, pyright binds nothing and is reported honestly with the mypy default offered alongside.
- **`/code-review` counterparts**: ruff is the Tier 1 native-SARIF source and mypy the Tier 3 JSON adapter documented above — same tools, full-repo invocations.

### JS/TS lane

Registered by #808.

- **Extensions**: `*.js`, `*.jsx`, `*.ts`, `*.tsx`, `*.mjs`, `*.cjs`
- **Diagnostic slot**: none registered — the lane verifies with the bound autofix provider's own check mode (degradation-ladder rung 2 in `static-self-heal.md`).
- **Autofix slot** — ordered provider list (default first; it doubles as the last-resort provider named by install hints):

1. **oxlint** — default, last-resort provider. Pin **>= 1.0.0**; verify the exact flag names (`--fix`, `--format sarif`) against the project's pinned version — verified against oxlint 1.72.0.
   - Fix pass (mechanical pre-fix): `npx oxlint --fix <scoped-files>`
   - Verify pass (check mode): `npx oxlint <scoped-files>`
   - Detection probe: `npx --no-install oxlint --version` — resolves the project-local `node_modules/.bin` first; oxlint is a project devDependency, never a global binary
   - Install hint (rung 3): `oxlint — JS/TS linting. install: npm install --save-dev oxlint`
   - Partial autofix: oxlint autofixes a subset of its rules — residue surviving the pre-fix goes to the coding agent on the same attempt, per the shared fix loop.
2. **biome** — full-speed provider: fast and machine-readable, meets all four qualification-contract items at per-step granularity.
   - Fix pass: `npx biome check --write <scoped-files>`
   - Verify pass: `npx biome check <scoped-files>`
   - Detection probe: `npx --no-install biome --version`
3. **eslint** — bound with demotion: meets contract items (a), (b), and (d) but fails the per-step latency budget (item c). A project that arrives configured for ESLint binds it with the lane demoted to slice-boundary granularity only, and one info line tells the user the fast default (oxlint) exists.
   - Fix pass: `npx eslint --fix <scoped-files>`
   - Verify pass: `npx eslint <scoped-files>`
   - Detection probe: `npx --no-install eslint --version`

Rebinding the slot from eslint to oxlint (dropping ESLint) is decided by the checklist under the Tier 2 oxlint entry ("When a project may drop ESLint entirely"); while both tools run, `eslint-plugin-oxlint` suppresses the overlap.

### C# lane

- **Extensions**: `.cs`
- **Autofix slot** (ordered provider list): `dotnet format` — the default and
  only provider; SDK-builtin (.NET SDK ≥ 6), so the last-resort provider the
  install hint names is the SDK itself.
- **Diagnostic slot**: the Roslyn ErrorLog SARIF exported by the
  GREEN-confirming `dotnet build` (see the Tier 1 "Roslyn ErrorLog (C#)"
  entry above for the flag and caveats) — not a separate scoped invocation.
  Scoping is post-hoc filtering to the changed set and freshness is
  build-then-filter, per the C# accommodation in
  `${CLAUDE_PLUGIN_ROOT}/skills/build/references/static-self-heal.md` — not
  restated here.
- **Detection probe** (one probe covers both slots): `command -v dotnet`.

`dotnet format` operates on an **MSBuild project or solution**, not on bare
file paths — `--include` is a filter of relative paths *within* that
project/solution, not the operand. When no project/solution argument is
given, the tool searches the working directory and errors on zero or multiple
candidates, so pass the project/solution explicitly whenever auto-discovery
is ambiguous.

**Fix pass** — scoped to the checkpoint's changed `.cs` files (paths relative
to the project/solution root); the `whitespace` and `style` subcommands run
at every checkpoint:

```bash
dotnet format whitespace <project-or-solution> --include <changed .cs files>
dotnet format style <project-or-solution> --include <changed .cs files>
```

At the slice-boundary checkpoint, additionally run the `analyzers`
subcommand, whose Roslyn workspace-load + implicit-restore cost amortizes
over the slice — no per-step analyzer visibility is lost, because the
ErrorLog SARIF from the GREEN-confirming build still surfaces analyzer
diagnostics at every step at zero cost:

```bash
dotnet format analyzers <project-or-solution> --include <slice's changed .cs files>
```

**Verify pass** — same subcommand split; `--verify-no-changes` formats
nothing and exits non-zero (with diagnostics; add `--report <path>` for a
JSON report) if any changes would have been made:

```bash
dotnet format whitespace <project-or-solution> --verify-no-changes --include <same files>
dotnet format style <project-or-solution> --verify-no-changes --include <same files>
# slice boundary only:
dotnet format analyzers <project-or-solution> --verify-no-changes --include <same files>
```

- **Severity threshold**: honor the project's `.editorconfig` at the tool's
  default `--severity warn` — the project's own config is the contract,
  consistent with how the other lanes' tools use project config.
- **Never invoke with an empty `--include` list** — per the CLI, an empty
  include set means "format all files in the project/solution". The
  mechanism's empty-partition guarantee (a lane with no matching changed
  files is never dispatched) is load-bearing for this lane.
- **Division of labor**: `dotnet format` applies only the fixes it has
  code-fixes for; diagnostics it can't fix surface via the ErrorLog SARIF
  from the next `dotnet build` and reach the coding agent as the lane's
  diagnostic findings on the same attempt — the two pieces are complementary,
  not redundant.
- **Recognized equivalent providers**: none — `dotnet format` is SDK-builtin,
  and third-party Roslyn analyzers (StyleCop.Analyzers etc.) automatically
  ride the same ErrorLog SARIF once referenced in the project's `.csproj`.
  C# equivalents join via the `.csproj`, not via lane providers.

### Java lane

Registered by #810.

- **Extensions**: `*.java`
- **Autofix slot**: none — Java has no autofix tool fast enough for the
  per-step loop. The lane is **diagnostic-only**: it runs the shared fix
  loop minus the mechanical pre-fix (degradation rung 1 by construction).
- **Diagnostic slot** — ordered provider list: **PMD** (default,
  last-resort) → **checkstyle**.

**PMD (default, last-resort provider)**

- **Detection probe**: repo-local `.pmd/pmd-bin-*/bin/pmd` launcher
  (`pmd.bat` on Windows) first, then `command -v pmd`; verify with
  `pmd --version`.
- **Invocation** (the mechanism resolves the changed-file set; write its
  `.java` subset to a temp file — PMD's `-d` takes directories/paths, not a
  shell-expanded word list, so `--file-list` is the robust scoped shape):

  ```bash
  pmd check --file-list "$TMP/pmd-files.txt" -R <resolved-ruleset> -f json --no-progress
  ```

- **Wrapper contracts**:
  - **Empty file set → skip the invocation entirely.** PMD errors when
    given no input files; an empty changed-`.java` set means "nothing to
    check", not a tool failure. The mechanism's empty-partition guarantee
    (a lane with no matching files is never dispatched) is load-bearing
    for this tool.
  - **Exit code 4 = violations found, not tool breakage.** `pmd check`
    exits 0 on clean, 4 when findings exist; treat only other non-zero
    codes as tool errors (degradation rung 4).
- **Ruleset**: identical to the `/code-review` invocation — see
  [Ruleset resolution](#ruleset-resolution-shared-by-both-pmd-invocations)
  under the Tier 1 pmd entry.
- **Install**: repo-level, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install-java-static-analysis.py`
  (pinned PMD into the gitignored `.pmd/` dir; `PMD_INSTALL_DIR` overrides).

**checkstyle (recognized equivalent provider)**

- **Qualification**: Tier 1 via native SARIF output (Checkstyle ≥ 10.3), no
  adapter; recognition still requires this registry row — the lists are
  small and explicit.
- **Binding**: a project arriving with a repo-root `checkstyle.xml` binds
  checkstyle (bind-don't-replace); PMD is installed only when the slot
  binds no recognized provider.
- **Detection probe**: `command -v checkstyle`, configured by the repo-root
  `checkstyle.xml`.
- **Invocation** (scoped): `checkstyle -f sarif -c checkstyle.xml <files>`.

**SpotBugs is not a provider candidate** for this slot: it requires
compiled bytecode, forcing a build step beyond what TDD's GREEN already
produces — it belongs at the end-of-build `/code-review` pass (opt-in deep
mode), tracked as a post-landing follow-up.
