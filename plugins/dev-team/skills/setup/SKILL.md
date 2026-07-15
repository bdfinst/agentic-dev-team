---
name: setup
description: >-
  Provision a repo for the dev-team plugin end to end — install the plugin's
  own prerequisites (jq, python3, per-language mutation tooling — Stryker,
  pitest, Stryker.NET), then generate dev-team-specific project
  configuration — project-level CLAUDE.md, the PostToolUse formatting hook,
  language-specific agent template activation, and a generated `/pr`
  command — from the stack signal `/dev-team:project-init` establishes. This
  is NOT where toolchain detection/installation itself lives (that's
  `/project-init`); `/setup` only consumes it. Use this when onboarding a
  new project to the dev-team plugin, when the mutation gate reports a
  missing tool, or when the user says "setup", "bootstrap", "configure this
  project for dev-team", "install required tools for the dev-team plugin",
  or "activate agent templates".
argument-hint: "[--dry-run]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Project Setup

Role: orchestrator. See frontmatter description for scope; delegates all
stack detection and toolchain install/inventory to `/dev-team:project-init`,
which `/setup` never re-derives.

## Orchestrator constraints

1. Detect and scaffold; delegate generation, do not review code yourself.
2. Install prerequisites and write config only where the user confirms.
3. Do not overwrite existing project config without confirming.
4. Be OS-aware; do not assume a package manager.
5. **Be concise.** Report detected stack, installed prerequisites, and
   generated artifacts — no narration.

## Parse Arguments

Arguments: $ARGUMENTS

- `--dry-run`: Report what would be created/installed without writing any
  files or installing anything.

## Steps

### 1. Detect OS

Run the following and record the result:

```bash
uname -s
```

- `Darwin` → macOS (use `brew`)
- `Linux` → Linux (detect package manager below)
- `MINGW*` or `MSYS*` (e.g. `MINGW64_NT-10.0-22621`) → Windows running Git Bash
  (detect Windows package manager below)
- Other → note the platform; provide manual instructions and continue

> **Windows note:** Claude Code on Windows runs in Git Bash (MINGW) or WSL.
> WSL reports `Linux` and is fully handled by the Linux steps. The Windows
> steps below apply to native Git Bash only. If you are using WSL, follow
> the Linux steps instead.

For Linux, detect the available package manager:

```bash
command -v apt-get && echo apt
command -v dnf     && echo dnf
command -v yum     && echo yum
command -v pacman  && echo pacman
```

Use the first one found.

For Windows (Git Bash), detect the available package manager:

```bash
command -v winget && echo winget
command -v choco  && echo choco
command -v scoop  && echo scoop
```

Use the first one found. If none are found, tell the user:
"No Windows package manager detected. Install winget (built into Windows 10/11
via the App Installer), Chocolatey (<https://chocolatey.org>), or Scoop
(<https://scoop.sh>), then re-run `/setup`."

### 2. Detect the agentic-dev-team repo and delegate to dev-setup.sh

Before installing anything, check whether this invocation is running inside
the agentic-dev-team plugin-dev repo itself (as opposed to a downstream
project that merely has the plugin installed):

```bash
test -f requirements-dev.txt && test -f plugins/dev-team/.claude-plugin/plugin.json && echo "in-repo" || echo "downstream"
```

- **`in-repo`**: print "Detected the agentic-dev-team repo — running
  scripts/dev-setup.sh to bootstrap the plugin-dev toolchain (shellcheck, jq,
  python3, Python dev dependencies)." Then run:

  ```bash
  bash scripts/dev-setup.sh
  ```

  Surface its stdout/stderr to the user. `dev-setup.sh` is a separate,
  intentionally-kept bash entry point — it works before Claude Code or the
  plugin is installed, and is reused as a generic template by
  `/new-marketplace` for other marketplace repos (see the note at the top of
  `scripts/dev-setup.sh`). This skill calls it rather than reimplementing its
  install logic. After it runs, still execute Step 3's jq/python3 checks below
  — they are idempotent and confirm dev-setup.sh's work rather than
  duplicating installation, so running both is a harmless double-check, not
  redundant install logic.
- **`downstream`**: no plugin-dev repo detected — proceed exactly as before
  with Step 3 (existing downstream-user behavior, unchanged).

### 3. Install hard dependencies (jq and python3)

These are required by the mutation gate regardless of language.

#### jq

Check if already installed:

```bash
command -v jq && jq --version
```

If missing, install:

| OS | Command |
| ---- | --------- |
| macOS | `brew install jq` |
| Linux (apt) | `sudo apt-get install -y jq` |
| Linux (dnf/yum) | `sudo dnf install -y jq` or `sudo yum install -y jq` |
| Linux (pacman) | `sudo pacman -S --noconfirm jq` |
| Windows (winget) | `winget install jqlang.jq` |
| Windows (choco) | `choco install jq` |
| Windows (scoop) | `scoop install jq` |
| Unknown | Tell the user: "Install jq manually from <https://jqlang.github.io/jq/> and re-run `/setup`." |

#### python3

Check if already installed:

```bash
command -v python3 && python3 --version
```

If missing, install:

| OS | Command |
| ---- | --------- |
| macOS | `brew install python3` |
| Linux (apt) | `sudo apt-get install -y python3` |
| Linux (dnf/yum) | `sudo dnf install -y python3` or `sudo yum install -y python3` |
| Linux (pacman) | `sudo pacman -S --noconfirm python` |
| Windows (winget) | `winget install Python.Python.3` |
| Windows (choco) | `choco install python` |
| Windows (scoop) | `scoop install python` |
| Unknown | Tell the user: "Install Python 3 manually from <https://python.org> and re-run `/setup`." |

> **Windows python3 alias:** Windows installers often register the binary as
> `python`, not `python3`. After installing, check:
>
> ```bash
> command -v python3 || python --version
> ```
>
> If only `python` is found, create a Git Bash alias so the mutation gate can
> find it:
>
> ```bash
> echo "alias python3='python'" >> ~/.bashrc && source ~/.bashrc
> ```
>
> Verify with `python3 --version` before proceeding.

If either installation fails, stop and tell the user: "Could not install
`<tool>`. Please install it manually and re-run `/setup`."

### 4. Invoke `/dev-team:project-init` for stack detection and toolchain

Run `/dev-team:project-init` and let it complete, including its confirmation
gate, before continuing.

### 5. Record the stack signal for dev-team's own use

`/setup` still needs a small, cheap signal of its own to populate
`.claude/project-stack.json` and to drive Step 6's mutation-tool selection
and Step 7's template selection. `/dev-team:project-init` performs its own
detection in Step 4 but persists no machine-readable artifact for `/setup`
to consume, so this is a deliberate lightweight re-probe using the same
indicator conventions (`skills/project-init/SKILL.md` Step 1 and Step 2) —
`package.json`, `tsconfig.json`, `pyproject.toml`/`requirements*.txt`,
`*.csproj`/`*.sln`, `pom.xml`/`build.gradle*` — plus the handful of framework
dependency checks (`react`, `vue`, `svelte`, `@angular/core`, `next`,
`django`, `flask`, `fastapi`) that project-init's own stack table doesn't
record. It does not repeat project-init's heavier JS/TS ES-module/
TypeScript/require-scan checks or its formatter-selection logic (those stay
entirely project-init's job — its Step 4/Scaffold steps and Step 4b/4c) and
it does not install anything.

Write findings to `.claude/project-stack.json`:

```json
{
  "detected": "2026-03-18",
  "stacks": ["typescript", "node"],
  "frameworks": ["react", "vitest"],
  "packageManager": "npm|yarn|pnpm|bun",
  "hasDocker": true,
  "indicators": {
    "package.json": true,
    "tsconfig.json": true
  }
}
```

### 6. Install per-language mutation tooling

Determine which of the language sections below to run from the stack signal
just recorded in Step 5 (`.claude/project-stack.json`'s `stacks` array —
`typescript`/`node` maps to the JS/TS section, `csharp`/`dotnet` maps to the
C# section, `java`/`kotlin` maps to the Java section). Run every matching
section; more than one may apply in a polyglot repo.

If the signal is empty or ambiguous (e.g. `--dry-run` scanning a repo with
no recognizable stack, or a layout project-init's detection table doesn't
cleanly classify), fall back to asking:

> "Which languages do you need mutation testing for? (Select all that apply)"
>
> 1. **JS/TS** — Stryker (`@stryker-mutator/core`)
> 2. **Java / Kotlin** — pitest (`pitest-maven` or `info.solidsoft.gradle.pitest`)
> 3. **C# / .NET** — Stryker.NET (`dotnet-stryker`)
> 4. **All of the above**
> 5. **None — skip mutation tooling**

Parse the response. If they choose 4, treat it as selecting 1, 2, and 3. If
5 (or the signal maps to none of the above, e.g. a pure-Python repo — there
is no Python mutation tool wired into this step), skip the rest of this
step.

---

#### JS/TS — Stryker

**Prerequisites check:**

```bash
command -v node && node --version
command -v npm  && npm --version
```

If `node` or `npm` is not found, tell the user:
"Node.js is required for Stryker. Install it from <https://nodejs.org> and
re-run `/setup`." Do not proceed with this language section.

**Bootstrap project if package.json is missing:**

Step 4 already ran `/dev-team:project-init` once this invocation, so this
should rarely trigger — it only fires when Step 5's signal maps to JS/TS but
the user's Step 4 selections didn't result in a scaffolded `package.json`
(e.g. they declined scaffolding, or picked a non-JS path there).

```bash
test -f package.json && echo "package.json found" || echo "no-package"
```

If the result is `no-package`:

1. Print: `No package.json found. Running /dev-team:project-init first to scaffold the project.`
2. Invoke the `/dev-team:project-init` skill. It will scaffold a
   functional ES-module project with prettier, eslint, editorconfig, and
   vitest (see the skill's own documentation for the full default set).
3. After the skill returns:
   - If `package.json` now exists → proceed to "Check if already installed".
   - If `package.json` still does not exist (user aborted project-init):
     print `Stryker skipped — no package.json. Re-run /setup after scaffolding your JS project.`
     and skip the rest of the JS/TS section.
   - If the skill reported an explicit failure: print
     `Stryker skipped — project-init failed. See errors above and re-run /setup after resolving them.`
     and skip the rest of the JS/TS section.

If the result is `package.json found`, proceed directly to "Check if already installed".

**Check if already installed (project-local):**

```bash
test -f node_modules/.bin/stryker && echo "installed" || echo "not found"
```

**If not installed, add Stryker as a dev dependency:**

```bash
npm install --save-dev @stryker-mutator/core
```

Then detect the test runner and install the matching Stryker plugin:

```bash
# Check package.json for test runner hints
cat package.json 2>/dev/null | grep -E '"vitest"|"jest"|"mocha"|"jasmine"' | head -5
```

Install the appropriate runner plugin:

| Detected runner | Install command |
| ----------------- | ---------------- |
| vitest | `npm install --save-dev @stryker-mutator/vitest-runner` |
| jest | `npm install --save-dev @stryker-mutator/jest-runner` |
| mocha | `npm install --save-dev @stryker-mutator/mocha-runner` |
| jasmine | `npm install --save-dev @stryker-mutator/jasmine-runner` |
| none detected | Install vitest runner as default: `npm install --save-dev @stryker-mutator/vitest-runner` and note to the user they may need to swap this for their runner |

**Initialize Stryker config if not already present:**

```bash
test -f stryker.config.js -o -f stryker.config.mjs -o -f stryker.config.ts \
  -o -f stryker.config.cjs -o -f .strykerrc.json && echo "config exists" || echo "no config"
```

If no config exists, run:

```bash
npx stryker init
```

This generates a `stryker.config.mjs` interactively. Tell the user it will ask
a few questions; they should accept defaults unless they have a specific setup.

**Verify:**

```bash
npx stryker --version
```

**Coverage baseline readiness (Jest/Vitest):**

`/coverage-baseline` (Phase 2 of `/test-improve`) parses
`coverage/coverage-summary.json` for `total.lines.pct` / `total.branches.pct`.
Jest and Vitest only emit that file when the **`json-summary`** reporter is
enabled, and the floor is only meaningful when coverage measures the whole
source tree (Jest `collectCoverageFrom` / Vitest `coverage.include`). Without
both, a repo that otherwise passes `/setup` still aborts `/test-improve`
Phase 2 (issue #1086). Probe and repair it now:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_readiness.py" .
```

Read the JSON report. `ready` is the hard requirement (the summary can be
parsed **and**, for Vitest, a coverage provider is installed); `meaningful`
is whether the baseline reflects the whole tree.

- **Vitest with `has_provider` `false`** (no `@vitest/coverage-v8` or
  `@vitest/coverage-istanbul` — Vitest emits no coverage at all without one,
  unlike Jest's built-in Istanbul) → show `provider_hint` and, on
  confirmation, install it as a devDependency:

  ```bash
  npm install --save-dev @vitest/coverage-v8
  ```

  Then re-run the probe. This is orthogonal to the reporter/scope checks
  below — both must be satisfied for `ready` to flip to `true`.
- **`ready` is `true`** → record it for the Step 11 report and continue.
- **`ready` is `false` and `patchable` is `true`** (config lives in
  `package.json`'s `jest` block or a `*.json` config) → tell the operator
  exactly which reporter will be added, and on confirmation re-run with
  `--patch`:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_readiness.py" . --patch
  ```

  The patch only appends `json-summary`, preserving existing reporters.
- **`ready` is `false` and `patchable` is `false`** (config is a JS/TS file
  like `jest.config.js` or `vitest.config.ts` — the probe never rewrites
  these) → show the operator `reporter_hint` and, on confirmation, apply that
  one-line edit with the Edit tool. Re-run the probe (no `--patch`) to confirm
  `ready` flipped to `true`.
- **`meaningful` is `false`** → show `scope_hint` and offer to add the
  suggested `collectCoverageFrom`/`coverage.include` (confirm first; never
  overwrite an existing scope). This is advisory — a missing scope doesn't
  block the baseline, it just inflates it.

Never write or patch coverage config without operator confirmation. Record
the final `ready`/`meaningful`/`patched` state for the Step 11 report.

---

#### Java / Kotlin — pitest

**Prerequisites check:**

```bash
command -v mvn   && echo "maven found"
command -v gradle && echo "gradle found"
```

If neither is found, tell the user:
"Maven or Gradle is required for pitest. Install one from
<https://maven.apache.org> or <https://gradle.org> and re-run `/setup`."

**Detect build tool:**

```bash
test -f pom.xml      && echo "maven"
test -f build.gradle -o -f build.gradle.kts && echo "gradle"
```

**Maven — check if pitest-maven already configured:**

```bash
grep -q 'pitest-maven' pom.xml 2>/dev/null && echo "configured" || echo "not configured"
```

If not configured, add the pitest-maven plugin to `pom.xml`. Find the
`<build><plugins>` section and insert:

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.4</version>
  <configuration>
    <outputFormats>
      <param>XML</param>
    </outputFormats>
    <timestampedReports>false</timestampedReports>
  </configuration>
</plugin>
```

Tell the user: "Added pitest-maven plugin to `pom.xml`. Run
`mvn pitest:mutationCoverage` to verify."

**Gradle — check if pitest plugin already applied:**

```bash
grep -q 'pitest' build.gradle 2>/dev/null || grep -q 'pitest' build.gradle.kts 2>/dev/null \
  && echo "configured" || echo "not configured"
```

If not configured, tell the user to add the following to `build.gradle` or
`build.gradle.kts` manually (Gradle plugins cannot be added programmatically):

For `build.gradle`:

```groovy
plugins {
    id 'info.solidsoft.pitest' version '1.15.0'
}

pitest {
    outputFormats = ['XML']
    timestampedReports = false
}
```

For `build.gradle.kts`:

```kotlin
plugins {
    id("info.solidsoft.pitest") version "1.15.0"
}

configure<com.info.solidsoft.pitest.PitestPluginExtension> {
    outputFormats.set(setOf("XML"))
    timestampedReports.set(false)
}
```

**Verify (Maven only — Gradle requires manual add):**

```bash
mvn pitest:mutationCoverage -DtimestampedReports=false -DoutputFormats=XML --help 2>&1 | head -5
```

---

#### C# / .NET — Stryker.NET

**Prerequisites check:**

```bash
command -v dotnet && dotnet --version
```

If `dotnet` is not found, tell the user:
".NET SDK is required for Stryker.NET. Install it from <https://dotnet.microsoft.com>
and re-run `/setup`."

**Check if dotnet-stryker is already installed as a project-local tool:**

```bash
dotnet tool list --local 2>/dev/null | grep stryker
```

Only the **local** (project-manifest) install satisfies this check. A
global `dotnet tool install --global dotnet-stryker` on this machine does
not — it doesn't propagate to teammates who clone the repo and run
`dotnet tool restore`, so it must never substitute for the local manifest
entry (issue #937).

**If not installed locally, install as a local tool:**

```bash
# If the file doesn't exist, create the tool manifest
test -f .config/dotnet-tools.json || dotnet new tool-manifest

# Install dotnet-stryker as a local tool, tracked in .config/dotnet-tools.json
dotnet tool install dotnet-stryker
```

If a global install is also detected, mention it informationally in the
summary (e.g. "also found globally installed") — it's harmless, just not a
substitute for the local manifest entry above.

**Verify:**

```bash
dotnet stryker --version 2>/dev/null || dotnet tool run dotnet-stryker --version
```

---

### 7. Select agent templates

Based on detected stack, select applicable templates from `templates/agents/`:

| Template | Condition |
| ---------- | ----------- |
| `ts-enforcer` | `tsconfig.json` exists or TypeScript in deps |
| `esm-enforcer` | Any JS/TS project (always-on) |
| ~~`functional-patterns`~~ | ~~Any JS/TS project~~ — **deprecated**, superseded by `js-fp-review` agent |
| `react-testing` | `react` or `react-dom` in deps |
| `front-end-testing` | Any frontend framework (React, Vue, Svelte, Angular) |
| `twelve-factor-audit` | Has Dockerfile, server entry point, or cloud config |
| `python-quality` | Python stack detected |
| `go-quality` | Go stack detected |
| `csharp-quality` | C#/.NET stack detected |
| `angular-testing` | `@angular/core` in deps |

Present the list to the user and ask for confirmation before scaffolding.

### 8. Generate project-level CLAUDE.md

If `.claude/CLAUDE.md` does not already exist in the target project, generate one containing:

- Project name and detected stack summary
- Discovered conventions (formatter, linter, test runner)
- References to activated agent templates
- Build/test/lint commands detected from `package.json` scripts, `Makefile`, etc.

If `.claude/CLAUDE.md` already exists, ask whether to merge or skip.

### 9. Generate PostToolUse formatting hook

Wire a PostToolUse hook entry for the project's `.claude/settings.json` that
runs the formatter for the detected stack, mapped by extension (Node/TS →
prettier + eslint, Python → ruff, Go → gofmt, Rust → rustfmt, Ruby →
rubocop, Java/Kotlin → google-java-format/ktlint, C# → dotnet format). The
tool itself is `/project-init`'s responsibility to install — since Step 4
already ran it, the formatter should be present. Only if a formatter is
still missing (check e.g. `npx prettier --version`, `ruff --version`), warn
the user and re-point them at `/project-init` rather than installing it here.

### 10. Generate /pr command

Create a project-specific `skills/pr/SKILL.md` if one doesn't exist, referencing the project's test/lint/typecheck commands.

### 11. Report

Display a summary of everything installed and created:

```
## Setup Complete

**Stack**: TypeScript, React, Vitest
**Package manager**: pnpm

### Prerequisites
- jq:       ✓ <version>
- python3:  ✓ <version>
- Mutation testing (Stryker): ✓ <version>   [or: ✗ skipped | ✗ failed]

### Coverage baseline readiness (JS/TS only)
- ✓ json-summary + coverage scope present   [ready + meaningful]
- ✓ patched (added json-summary reporter to <config>)   [was not ready, now fixed]
- ✓ installed @vitest/coverage-v8   [Vitest provider was missing, now present]
- ⚠ manual action needed — <reporter_hint>   [JS/TS config the operator declined or must edit]
- ⚠ Vitest coverage provider missing — <provider_hint>   [not ready]
- ⚠ coverage scope unset — baseline will be inflated (<scope_hint>)   [not meaningful]

### Created
- `.claude/project-stack.json` — stack detection results
- `.claude/CLAUDE.md` — project conventions
- `.claude/settings.json` — PostToolUse formatting hook (prettier + eslint)
- Activated templates: ts-enforcer, esm-enforcer, react-testing

### Recommendations
- Add `"type": "module"` to package.json
- 3 files using `require()` — consider migrating to ES imports
```

If any prerequisite step failed, add a "Next steps" section with the
specific manual actions needed (mirroring the per-step failure messages
above).

If `--dry-run` was specified, prefix the report with "**DRY RUN** — no files were written and nothing was installed." and skip all writes/installs.
