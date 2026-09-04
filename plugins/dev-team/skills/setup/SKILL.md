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
argument-hint: "[--yes] [--dry-run]"
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
- `--yes`: Run unattended — auto-confirm every prompt with its **safe**
  default and pass `--yes` through when invoking `/dev-team:project-init`
  (Step 4). No step waits for input.

### `--yes` semantics (the unattended contract)

When `--yes` is set, take these actions without prompting. **Affirmative** —
auto-confirm and proceed:

- Per-language mutation tooling for the detected stack (Step 6). Already
  non-interactive when the stack is definite; `--yes` additionally suppresses
  the ambiguous-stack fallback below.
- Agent-template activation for the detected stack (Step 7).
- Project `CLAUDE.md` (Step 8) and `/pr` (Step 10) generation **when the file
  is absent**; the downstream `.gitignore` append (Step 11).
- Everything `/dev-team:project-init` auto-confirms under its own `--yes`
  (its three-column plan, capability tools whose signal fired, and the keyless
  CodeGraph + Repowise pair — see that skill's Arguments section).

**Conservative** — never silently overwrite an existing file or mutate the
repo in a surprising way; take the skip default and print a one-line note:

- **Existing project `CLAUDE.md`** (Step 8) — never overwritten (orchestrator
  constraint 3). Skip and note it, exactly as the interactive "merge or skip"
  path's skip branch.
- **Coverage-config edits** (Step 6, JS/TS readiness) — `--yes` may install the
  additive `@vitest/coverage-v8` devDependency, but does **not** run `--patch`
  or hand-edit an existing `jest.config.js` / `vitest.config.*`. Report the
  hints as it does interactively; the operator applies those edits.
- **Graphify** — declined for this run inside `/dev-team:project-init` (see
  that skill); it writes to the repo, so it stays opt-in even under `--yes`.
- **Unrecognized / ambiguous stack** — `--yes` never guesses a toolchain. Do
  the language-neutral steps and report what could not be set up.
- **Concise-response preference** (Step 8a) — `--yes` never guesses a
  communication-style preference. Skip the prompt and the `CLAUDE.md`
  append entirely; note `concise-preference-skipped-under-yes`.

**Precedence.** If both `--yes` and `--dry-run` are passed, `--dry-run` wins:
report only, write and install nothing, and add "`--yes` ignored under
`--dry-run`" to the report.

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
gate, before continuing. **Under `--yes`, invoke it as
`/dev-team:project-init --yes`** so its own gates auto-confirm with their safe
defaults rather than blocking (see that skill's Arguments section).

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

Mutation-tool installation is **strictly relative to the detected stack**.
Do not decide which language sections to run by hand — the mapping is a
deterministic helper, so the wrong-stack probe (e.g. `dotnet` on a JS repo)
cannot fire. Call it once:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mutation_stack_sections.py" .
```

It reads `.claude/project-stack.json`'s `stacks` array (recorded in Step 5)
and prints one JSON object:

```json
{ "sections": ["js"], "stacks": ["typescript", "node"], "ambiguous": false, "note": null }
```

- `sections` — the sections to run, from `js` (JS/TS — Stryker), `java`
  (Java/Kotlin — pitest), `csharp` (C#/.NET — Stryker.NET), `python`
  (Python — mutmut). The mapping is `typescript`/`node`/`javascript` → `js`,
  `java`/`kotlin` → `java`, `csharp`/`dotnet` → `csharp`, `python` →
  `python`. **Run every section in `sections` and no others.** More than one
  may apply in a polyglot repo.
- `ambiguous` — `true` **only** when the stack signal is genuinely empty or
  missing (no `.claude/project-stack.json`, unreadable/invalid, or an empty
  `stacks` array). This is the **only** outcome that authorizes the
  interactive fallback below.
- `note` — set when a definite stack matched no section (e.g. a Ruby or
  Elixir repo — there is no mutation tool wired into this step for that
  stack). When `note` is non-null, `sections` is empty and `ambiguous` is
  `false`: install **nothing**, probe **nothing** (no `dotnet`, `node`,
  `mvn`, or `pip`), print the `note` line verbatim, and skip the rest of
  this step.

**Interactive fallback — only when `ambiguous` is `true`.** When a definite
stack was detected (`ambiguous` is `false`), never prompt; honor `sections`
exactly. **Under `--yes`, skip this fallback entirely even when `ambiguous`
is `true`** — never guess a stack: install no mutation tooling and print
`Mutation tooling skipped — no stack detected (run /setup without --yes to choose)`.
Otherwise, only when `ambiguous` is `true` (e.g. `--dry-run` scanning a repo
with no recognizable stack) fall back to asking:

> "Which languages do you need mutation testing for? (Select all that apply)"
>
> 1. **JS/TS** — Stryker (`@stryker-mutator/core`)
> 2. **Java / Kotlin** — pitest (`pitest-maven` or `info.solidsoft.gradle.pitest`)
> 3. **C# / .NET** — Stryker.NET (`dotnet-stryker`)
> 4. **Python** — mutmut
> 5. **All of the above**
> 6. **None — skip mutation tooling**

Parse the response. If they choose 5, treat it as selecting 1, 2, 3, and 4
(i.e. `sections` = `["js", "java", "csharp", "python"]`). If 6, skip the
rest of this step.

Each language subsection below **re-asserts its own gate as its literal
first step** — a section whose key is not in `sections` returns immediately,
before any `command -v` / tool probe. The guard is therefore robust even if
a section is reached out of order.

---

#### JS/TS — Stryker

**Stack gate (first step — hard precondition):** if `js` is not in the
Step 6 helper's `sections`, return immediately. Do **not** run the
prerequisites probe below. Only proceed when `js` is in `sections`.

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

**If not installed** (the check above reported `not found`)**, add Stryker as a
dev dependency** — skip this install when it reported `installed`:

```bash
npm install --save-dev @stryker-mutator/core
```

**Detect the test runner and install its Stryker plugin — but only when that
plugin is not already present.** Run this independently of the core check
above: the core binary can be installed while its runner plugin is missing,
and an already-present runner plugin must never be reinstalled.

```bash
# Detect the runner from package.json
cat package.json 2>/dev/null | grep -E '"vitest"|"jest"|"mocha"|"jasmine"' | head -5
# Then, for the detected runner (substitute its name), check before installing:
test -d node_modules/@stryker-mutator/vitest-runner && echo "present" || echo "missing"
```

Install the plugin **only if the check above reported `missing`**
(`npm install --save-dev <package>`):

| Detected runner | Plugin package |
| ----------------- | ---------------- |
| vitest | `@stryker-mutator/vitest-runner` |
| jest | `@stryker-mutator/jest-runner` |
| mocha | `@stryker-mutator/mocha-runner` |
| jasmine | `@stryker-mutator/jasmine-runner` |
| none detected | `@stryker-mutator/vitest-runner` (default; note to the user they may need to swap this for their runner) |

**If any Stryker install above fails with `npm error code ERESOLVE`**, the
conflict is a peer-dependency clash already present in the repo's tree — not
between it and `@stryker-mutator/*`, which carries no such peer relationship.
Retry that command once with `--legacy-peer-deps` (e.g. `npm install
--save-dev @stryker-mutator/core --legacy-peer-deps`), and add a one-line note
to the user that you fell back to `--legacy-peer-deps` because of a
pre-existing peer conflict. Don't abort on the first ERESOLVE.

**Initialize Stryker config if not already present:**

```bash
test -f stryker.config.js -o -f stryker.config.mjs -o -f stryker.config.ts \
  -o -f stryker.config.cjs -o -f .strykerrc.json && echo "config exists" || echo "no config"
```

If no config exists, **write `stryker.config.mjs` directly** — do not run
`npx stryker init`, which is interactive (it prompts for the test runner,
reporters, and package manager) and hangs a non-interactive `/setup` run.
You already detected the test runner above, so emit the config with
`testRunner` set to that runner. Write the file with this shape, substituting
the detected runner (`vitest` / `jest` / `mocha` / `jasmine`; use `vitest`
when none was detected):

```js
// stryker.config.mjs
export default {
  packageManager: "npm",
  testRunner: "jest", // <- the runner detected above
  coverageAnalysis: "perTest",
  reporters: ["html", "clear-text", "progress"],
  mutate: ["src/**/*.{js,ts}", "!src/**/*.{test,spec}.{js,ts}"],
};
```

Runner-specific notes when substituting `testRunner`:

- **jest** — add a `jest` block so Stryker finds the project config, e.g.
  `jest: { projectType: "custom", configFile: "jest.config.js" }` (point
  `configFile` at the repo's actual Jest config). Angular repos also want
  `"!src/**/*.module.ts"` appended to `mutate`.
- **vitest / mocha / jasmine** — no extra runner block is required; the
  `testRunner` value alone wires up the installed runner plugin.

Keep `mutate` scoped to the repo's real source layout — adjust the globs if
sources live somewhere other than `src/`.

> If you'd rather configure interactively, `npx stryker init` walks through
> the same choices with prompts — but only run it in an interactive shell, not
> as part of an automated `/setup`.

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
- **`ready` is `true`** → record it for the Step 12 report and continue.
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

Never write or patch coverage config without operator confirmation. **Under
`--yes`, install only the additive `@vitest/coverage-v8` devDependency without
prompting; do not run `--patch` or hand-edit an existing config file** — leave
those edits to the operator and surface the hints in the report exactly as the
interactive path does. Record the final `ready`/`meaningful`/`patched` state
for the Step 12 report.

---

#### Java / Kotlin — pitest

**Stack gate (first step — hard precondition):** if `java` is not in the
Step 6 helper's `sections`, return immediately. Do **not** run the
prerequisites probe below. Only proceed when `java` is in `sections`.

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

**Stack gate (first step — hard precondition):** if `csharp` is not in the
Step 6 helper's `sections`, return immediately. Do **not** run the
prerequisites probe below (no `command -v dotnet`, no `dotnet tool list`).
Only proceed when `csharp` is in `sections`.

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

#### Python — mutmut

**Stack gate (first step — hard precondition):** if `python` is not in the
Step 6 helper's `sections`, return immediately. Do **not** run the
prerequisites probe below (no `command -v mutmut`, no `pip show mutmut`).
Only proceed when `python` is in `sections`.

**Prerequisites check:**

```bash
command -v python3 && python3 --version
python3 -m pip --version
```

If `python3` or `pip` is not found, tell the user: "Python 3 with pip is
required for mutmut. Install it from <https://www.python.org> and re-run
`/setup`."

**Check if mutmut is already installed:**

```bash
mutmut version 2>/dev/null || python3 -m mutmut version 2>/dev/null
```

Use the `version` **subcommand**, not `--version`. mutmut 2.x — the range this
step pins — has no `--version` flag and exits 2 on it, so a `--version` probe
reports "not installed" for a perfectly good install and this step reinstalls
on every run.

**If not installed, install it — isolated, never `--user` or system-wide** (that
puts mutmut in a location whose `PATH` presence depends on shell config, the
silent-failure trap this step exists to avoid). **Pin `mutmut<3`** — mutmut 3.x
ships an incompatible config/CLI contract (`source_paths` in a `[mutmut]`
setup.cfg section, no `--paths-to-mutate` flag) that the shipped adapter
(`hooks/mutation_adapters/mutmut.py`) does not speak.

**Prefer `uv`, because `pip` cannot build this pin on a current toolchain.**
mutmut 2.x depends on `glob2` 0.7, whose `setup.py` uses `install_layout` and
fails against setuptools >= 60 with `AttributeError: install_layout`, ending in
`Could not build wheels for mutmut, glob2`. That is not an edge case — it is
every machine with a modern setuptools. uv supplies a compatible setuptools
inside its own build isolation and succeeds where pip cannot:

```bash
uv tool install "mutmut<3"
```

uv installs the console script into an isolated environment and puts `mutmut`
on `PATH`, which is exactly what the adapter looks for: `_mutmut_argv()` in
`hooks/mutation_adapters/mutmut.py` resolves `shutil.which("mutmut")` first and
only falls back to `python3 -m mutmut`.

If `uv` is unavailable, fall back to pip **inside an activated virtualenv**
(never `--user`), accepting that it only succeeds on setuptools < 60:

```bash
python3 -m pip install "mutmut<3"
```

If the project declares dev dependencies in `pyproject.toml`
(`[project.optional-dependencies]` / `[tool.poetry.group.dev.dependencies]`),
prefer adding `mutmut<3` there and installing via the project's existing
dev-dependency flow instead of a bare `pip install`.

**Verify:**

```bash
mutmut version 2>/dev/null || python3 -m mutmut version
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
**Under `--yes`, activate the selected templates without prompting** and list
them in the Step 12 report.

### 8. Generate project-level CLAUDE.md

If `.claude/CLAUDE.md` does not already exist in the target project, generate one containing:

- Project name and detected stack summary
- Discovered conventions (formatter, linter, test runner)
- References to activated agent templates
- Build/test/lint commands detected from `package.json` scripts, `Makefile`, etc.

If `.claude/CLAUDE.md` already exists, ask whether to merge or skip. **Under
`--yes`, take the skip branch** — never overwrite existing project config
(orchestrator constraint 3) — and note `CLAUDE.md exists — left unchanged` in
the Step 12 report. This note describes only Step 8's own generate-or-skip
decision — Step 8a runs independently right after and may still append to
this same file, so "left unchanged" here and a `concise-preference-added`
outcome from Step 8a are not a contradiction in the Step 12 report.

### 8a. Ask about concise-response preference

Ask the operator: "Would you like Claude to give concise responses by default in this repo? This appends a block to the project's committed `.claude/CLAUDE.md`, so it becomes a shared convention for every contributor, not just you." **Under `--yes`, skip this prompt entirely** — never
guess a communication-style preference — and note
`concise-preference-skipped-under-yes` (run /setup without --yes to choose)
in the Step 12 report. **Under `--dry-run`, report what would be appended
without writing** (same convention as Step 11's two idempotent blocks).

If the operator declines, note `concise-preference-declined` and move on —
do not write anything.

If the operator confirms, idempotently append the block below to the
project's `CLAUDE.md` (the same file Step 8 generated or left in place —
`.claude/CLAUDE.md`; this step creates `.claude/` and the file itself if
Step 8 somehow left them absent). The marker is a dedicated, content-free
comment — not a substring of the prose — so a future wording tweak to the
block below can never desync it from the idempotency check (the hazard
Step 11's own `.mcp.json` marker note, below, already calls out for its own
pair of blocks). Both `.claude` and `.claude/CLAUDE.md` are checked for
symlinks before any write, since a symlinked parent directory is an
equally valid escape route as a symlinked file:

```bash
MARKER="<!-- dev-team: concise-response preference v1 -->"
if [ -L .claude ] || [ -L .claude/CLAUDE.md ]; then
  echo "concise-preference-skipped-symlink"
else
  mkdir -p .claude
  touch .claude/CLAUDE.md
  if ! grep -qF "$MARKER" .claude/CLAUDE.md; then
    { printf '\n%s\n' "$MARKER"; cat <<'CONCISE_BLOCK'
## General
Unless asked to behave otherwise, always give concise responses and sacrifice grammar for the sake of concision. Ask clarifying questions when needed and offer your best guess at available interpretations/answers for those questions when possible.

### Be RUTHLESSLY concise — this is the rule I break most often
Default to a few sentences. If the answer is "yes", say "yes" and stop.

- **Answer the question asked. Nothing else.** No adjacent findings, no "while I was looking I noticed", no caveats I didn't ask for. Sit on it until I ask.
- **One thing at a time.** Never hand me a numbered list of 3+ considerations, options, or trade-offs unless I asked for options. Pick one, recommend it, move on.
- **No teaching.** Skip the mechanism, the background, the "why this matters". State the conclusion. I'll ask why if I care.
- **No tables, no headers, no bold-label paragraphs** for a simple answer. Prose or a couple of lines.
- **Cut every parenthetical, every "worth noting", every "the real finding is".**
- Corrections: one sentence, no post-mortem.

Length is the tell: if a reply is over ~10 lines and I didn't ask for depth, it's wrong. Detail I have to skim to find the answer is worse than no answer.
CONCISE_BLOCK
    } >> .claude/CLAUDE.md
    echo "concise-preference-added"
  else
    echo "concise-preference-already-covered"
  fi
fi
```

This always appends a fresh, self-contained `## General` heading rather
than trying to detect and merge into a pre-existing one — a prior version
of this step attempted that merge and introduced two bugs of its own (an
orphaned sub-heading when the file's last `##` section wasn't `General`,
and a `^## General$` anchor that silently missed CRLF line endings on
Windows). A file ending up with two `## General` headings is a cosmetic,
rare edge case; a script that silently corrupts document structure on a
supported platform is not an acceptable trade for avoiding it.

Record the outcome — `concise-preference-declined` /
`concise-preference-added` / `concise-preference-already-covered` /
`concise-preference-skipped-under-yes` / `concise-preference-skipped-symlink`
— for the Step 12 report, using these exact tokens. The three the script
can reach (`added` / `already-covered` / `skipped-symlink`) are echoed
verbatim from its own output; the other two (`declined` /
`skipped-under-yes`) are recorded directly from the prose branches above,
since the script never runs on those paths.

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

### 11. Ensure `.gitignore` covers dev-team runtime artifacts

**Downstream projects only** — skip this step entirely when Step 2 detected
`in-repo` (the plugin-dev repo curates its own `.gitignore`, and it tracks
deliverables such as `.claude/memory/decisions.md` and bare `memory/` eval
fixtures that this blanket ignore would wrongly hide). One carve-out: the `.mcp.json`
standing check `project-init`'s Repowise sub-section runs (#1416) is
unconditional and reaches in-repo too, via this skill's own Step 4 — that one
`.gitignore` entry lands regardless of Step 2's result. See the `.mcp.json`
paragraph below.

`/test-improve`, `/build`, and the review workflows write per-run resume
state, progress bookkeeping, and metrics into `.claude/memory/`,
`.claude/metrics/`, and `.claude/plans/`; reports land in
`.dev-team-reports/` (the `.claude/`-scoped artifact migration and
reports-domain consolidation, #1406). `/code-review` additionally writes a
`.pr-review-passed` gate file to `.claude/memory/` (already covered by the
`.claude/memory/` line below), consumed and deleted by `hooks/pre_pr_review.py`
on the next matching `gh pr create` (#1886) — but left behind whenever that
PR is never opened (branch content changed since review, or
`PR_GATE_BYPASS_REASON`), cluttering `git status` and risking capture by a
stray `git add -A` (issue #1377). These
are regeneratable runtime artifacts, not deliverables — but `/build` commits
the working tree per completed step, so without an ignore rule they land in
the project's history (issue #1101).

In a downstream project, `.claude/memory/`, `.claude/metrics/`, and
`.claude/plans/` are exclusively dev-team runtime state, so each whole
folder is safe to ignore. `.dev-team-reports/` is **not** wholly safe to
ignore: `/test-improve` git-tracks a `<slug>/data/` sibling directory
under it (issue #1412) so its report is a pure function of tracked data and
regeneratable from a fresh checkout, so the rule anchors a deny-all and
re-includes that one tracked exception instead of ignoring the whole
folder — the identical shape this repo's own `.gitignore` and
`/project-init`'s JS-scaffold template use. The legacy bare `memory/`,
`reports/`, `metrics/`, `plans/` lines are appended alongside as a safety
net for any pre-#1406 content still landing at the old paths.
Idempotently append the block (create `.gitignore` if absent; do nothing if
the marker is already present):

```bash
MARKER="# dev-team workflow runtime artifacts (.claude/-scoped + .dev-team-reports/, #1406) v2"
if ! grep -qF "$MARKER" .gitignore 2>/dev/null; then
  # Self-heal: a pre-#1412 run of this block (under the v1 marker) may have
  # already appended the superseded blanket `.dev-team-reports/` line. Strip
  # it before appending the anchored replacement below — git never
  # re-includes a path whose parent directory is itself excluded, so leaving
  # the old blanket line in place would silently shadow the new exception.
  if [ -f .gitignore ]; then
    grep -vxF '.dev-team-reports/' .gitignore > .gitignore.tmp && mv .gitignore.tmp .gitignore
  fi
  printf '\n%s\n%s\n' \
    "$MARKER (regeneratable; not deliverables — issues #1101, #1377, #1406, #1412)" \
    ".claude/memory/
.claude/metrics/
.claude/plans/
/.dev-team-reports/*
!/.dev-team-reports/test-improve/
memory/
reports/
metrics/
plans/
.pr-review-passed" >> .gitignore
  echo "gitignore-updated"
else
  echo "gitignore-already-covered"
fi
```

`DEV_TEAM_TASK_METRICS` and `DEV_TEAM_REPORTS` do not override a directory
path in code today — `DEV_TEAM_TASK_METRICS=off` is an on/off opt-out for the
task-log writer only, and `DEV_TEAM_REPORTS` is not an environment variable
at all (it names the legacy `DEV_TEAM_REPORTS/` directory folded into
`.dev-team-reports/` above). There is no "relocated path" case to special-case
here. Record whether the block was added for the Step 12 report. Under
`--dry-run`, report what would be appended without writing.

**`.mcp.json` machine-specific-path hygiene (issues #1376, #1416).**
Separately — still downstream-projects-only, same Step 2 `in-repo` skip — a
project's `.mcp.json` (written by `index-codebase`, hand-registered MCP
servers, or any other means) commonly bakes in the absolute filesystem path
of the machine that wrote it (e.g. a CodeGraph server's `args` array). If
committed, every other clone inherits a path that doesn't exist on their
machine and the server fails to start. Idempotently append its own block
(independent marker, so this check runs and self-heals even on a repo where
the runtime-artifacts block above was already added by an older `/setup`):

```bash
MCP_MARKER="# dev-team hygiene — machine-specific MCP config"
if ! grep -qF "$MCP_MARKER" .gitignore 2>/dev/null; then
  printf '\n%s\n%s\n' \
    "$MCP_MARKER (absolute-path pollution — issue #1376)" \
    ".mcp.json" >> .gitignore
  echo "mcp-json-gitignore-updated"
else
  echo "mcp-json-gitignore-already-covered"
fi
```

This exact marker (including the em dash) is also emitted, unconditionally
and regardless of in-repo/downstream, by the `.mcp.json` machine-specific-path
hygiene standing check in `project-init`'s Repowise sub-section (issue #1416
— Repowise's own install path is the more common source of a project's
`.mcp.json`, and that check no longer waits for this downstream-only Step 11
pass to cover it). The marker prefix (everything up to and including
`machine-specific MCP config`) must stay byte-identical between the two
blocks — `grep -qF` matches that prefix only, so the trailing issue-number
suffix may differ, but changing the prefix itself in only one place breaks
idempotency. This block remains a downstream-only, defense-in-depth backstop
for `.mcp.json` files written by means other than Repowise (e.g.
`index-codebase`, hand-registered MCP servers).

This ignores `.mcp.json` going forward regardless of whether it currently
exists — the same "detect it whenever we write or see it" contract issue
#1376 asks for. If `.mcp.json` is already tracked by git (`git ls-files
--error-unmatch .mcp.json` exits 0), tell the operator to `git rm --cached
.mcp.json` themselves rather than doing it automatically — untracking is a
history-visible action `/setup` should not take silently. Record whether the
block was added for the Step 12 report. Under `--dry-run`, report what would
be appended without writing. Reached via `/setup` (Step 4 runs `/project-init`
before this step), this block normally reports already-covered, since
`/project-init`'s own standing check already ran first — the "added" outcome
is what a direct, standalone `/project-init` invocation reports.

### 12. Report

Display a summary of everything installed and created:

```
## Setup Complete

**Stack**: TypeScript, React, Vitest
**Package manager**: pnpm

### Prerequisites
- jq:       ✓ <version>
- python3:  ✓ <version>
- Mutation testing: ✓ <tool> <version>   [or: ✗ skipped | ✗ failed]

Report a mutation-testing line **only for sections actually in scope** — the
`sections` the Step 6 helper returned (Stryker for `js`, pitest for `java`,
Stryker.NET for `csharp`, mutmut for `python`). Never list a tool for a
stack that was not detected. When the helper's `note` was set (a detected
stack with no mutation tool wired in, e.g. Ruby or Elixir), report that one
line verbatim — `no mutation tooling for detected stack (<stacks>)` — and no
tool line.

### Coverage baseline readiness (JS/TS only)
- ✓ json-summary + coverage scope present   [ready + meaningful]
- ✓ patched (added json-summary reporter to <config>)   [was not ready, now fixed]
- ✓ installed @vitest/coverage-v8   [Vitest provider was missing, now present]
- ⚠ manual action needed — <reporter_hint>   [JS/TS config the operator declined or must edit]
- ⚠ Vitest coverage provider missing — <provider_hint>   [not ready]
- ⚠ coverage scope unset — baseline will be inflated (<scope_hint>)   [not meaningful]

### Code-intelligence indexes (project-init Step 4c — all-or-none group)
- CodeGraph: ✓ installed + `.codegraph/` built (keyless)   [or: ✗ declined | ✗ failed]
- Repowise:  ✓ installed + `.repowise/` indexed (keyless)   [or: ✗ declined | ✗ failed]
  - `.mcp.json` gitignore: ✓ added   [or: ✓ already covered | ⚠ tracked by git — run `git rm --cached .mcp.json` (#1416)]
- Graphify:  ✓ `graphify-out/` built (keyless AST; enrichment key-gated)   [or: ✗ declined | ✗ failed]
  - settings.json guard: ✓ clean   [or: ✓ relocated N machine-specific graphify hook(s) to settings.local.json (#1367)]

The separate "run index-codebase first" step is no longer required — accepting
the group installs and builds all three indexes in the same run. The
settings.json guard line reports project-init's standing check (#1367) — it
runs on every pass, including one where Graphify install itself is skipped
because it's already present, so a repo carrying a machine-specific path from
an install predating this guard gets self-healed the next time `/setup` runs.
The `.mcp.json` gitignore line reports project-init's own standing check
(#1416) the same way — it runs on every pass, in-repo included, regardless of
Repowise's own install/decline state for that run.

### Created
- `.claude/project-stack.json` — stack detection results
- `.claude/CLAUDE.md` — project conventions   [Step 8a concise-response preference, independent of this line's created/left-unchanged status: concise-preference-added | concise-preference-already-covered | concise-preference-declined | concise-preference-skipped-under-yes | concise-preference-skipped-symlink]
- `.claude/settings.json` — PostToolUse formatting hook (prettier + eslint)
- `.gitignore` — dev-team runtime artifacts (.claude/memory/, .claude/metrics/, .claude/plans/, .dev-team-reports/, memory/, reports/, metrics/, plans/, .pr-review-passed)   [downstream only; omit if already covered] plus `.mcp.json` machine-specific-path hygiene (#1376, #1416)   [runs in-repo too, via project-init's Repowise standing check; omit if already covered]
- Activated templates: ts-enforcer, esm-enforcer, react-testing

### Recommendations
- Add `"type": "module"` to package.json
- 3 files using `require()` — consider migrating to ES imports
```

If any prerequisite step failed, add a "Next steps" section with the
specific manual actions needed (mirroring the per-step failure messages
above).

If `--dry-run` was specified, prefix the report with "**DRY RUN** — no files were written and nothing was installed." and skip all writes/installs. If `--yes` was also passed, add "`--yes` ignored under `--dry-run`" to that prefix.
