---
name: init-dev-team
description: >-
  Install required tools for the agentic-dev-team plugin. OS-aware (macOS,
  Linux, Windows Git Bash): installs jq and python3 as hard dependencies, then
  prompts for language selection (JS/TS, Java, C#) to install the matching
  mutation testing tool (Stryker, pitest, Stryker.NET). Run this when the
  mutation gate reports a missing tool.
user-invocable: true
allowed-tools: Read, Bash, Write
---

# Init Dev Team

Role: worker. Installs tools required by the agentic-dev-team plugin, with a
focus on the mutation gate. Run after the plugin is installed, or when the
mutation gate reports a missing dependency.

You have been invoked with the `/init-dev-team` command.

## Step 1 — Detect OS

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
(<https://scoop.sh>), then re-run `/init-dev-team`."

## Step 2 — Install hard dependencies (jq and python3)

These are required by the mutation gate regardless of language.

### jq

Check if already installed:

```bash
command -v jq && jq --version
```

If missing, install:

| OS | Command |
|----|---------|
| macOS | `brew install jq` |
| Linux (apt) | `sudo apt-get install -y jq` |
| Linux (dnf/yum) | `sudo dnf install -y jq` or `sudo yum install -y jq` |
| Linux (pacman) | `sudo pacman -S --noconfirm jq` |
| Windows (winget) | `winget install jqlang.jq` |
| Windows (choco) | `choco install jq` |
| Windows (scoop) | `scoop install jq` |
| Unknown | Tell the user: "Install jq manually from <https://jqlang.github.io/jq/> and re-run `/init-dev-team`." |

### python3

Check if already installed:

```bash
command -v python3 && python3 --version
```

If missing, install:

| OS | Command |
|----|---------|
| macOS | `brew install python3` |
| Linux (apt) | `sudo apt-get install -y python3` |
| Linux (dnf/yum) | `sudo dnf install -y python3` or `sudo yum install -y python3` |
| Linux (pacman) | `sudo pacman -S --noconfirm python` |
| Windows (winget) | `winget install Python.Python.3` |
| Windows (choco) | `choco install python` |
| Windows (scoop) | `scoop install python` |
| Unknown | Tell the user: "Install Python 3 manually from <https://python.org> and re-run `/init-dev-team`." |

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
`<tool>`. Please install it manually and re-run `/init-dev-team`."

## Step 2.5 — Offer CodeGraph

CodeGraph (<https://github.com/colbymchenry/codegraph>) is a third-party SQLite
knowledge graph of every symbol, edge, and file in the workspace. When present,
the plugin's `codegraph-nudge` hook recommends `codegraph_context` /
`codegraph_explore` over multi-file Read/Grep/Glob exploration. This step
detects current state and offers the right next action.

**Classify state** (run both, record results as `installed` and `initialized`):

```bash
command -v codegraph > /dev/null 2>&1 && echo "installed" || echo "not-installed"
[ -d "${PWD}/.codegraph" ] && echo "initialized" || echo "not-initialized"
```

Read `.claude/init-state.json` if it exists (top-level `codegraph` key holds
the four state booleans: `install_accepted`, `install_declined`,
`init_accepted`, `init_declined`).

**Branch on (installed, initialized):**

| installed | initialized | Action |
|-----------|-------------|--------|
| any       | true        | Print "CodeGraph: initialized ✓" and continue to Step 3. State file untouched. |
| true      | false       | **Init prompt branch** (below). |
| false     | false       | **Install prompt branch** (below). |

**Stale-state override.** Before consulting the recorded state, apply these
rules: `install_declined` is ignored when `installed=true` (the user has since
installed CodeGraph); `init_declined` is ignored when `initialized=true` (the
project got initialized by other means). The live filesystem/PATH check
supersedes the recorded preference.

### Install prompt branch (installed=false, initialized=false)

- If `.codegraph.install_declined == true`: print
  `CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)`
  and continue to Step 3.
- Otherwise prompt: `Install CodeGraph for code intelligence? (y/N)`
  - On `y` or `Y`: print `CodeGraph install instructions: https://github.com/colbymchenry/codegraph#installation`.
    Merge `{"codegraph": {"install_accepted": true}}` into `.claude/init-state.json`.
  - On any other response (including empty): merge
    `{"codegraph": {"install_declined": true}}` and continue silently.

### Init prompt branch (installed=true, initialized=false)

- If `.codegraph.init_declined == true`: print
  `CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)`
  and continue.
- Otherwise prompt: `CodeGraph is installed but not initialized in this project. Initialize now? (y/N)`
  - On `y` or `Y`:
    1. Print: `Running 'codegraph init -i' in this project...`
    2. Execute `codegraph init -i` with the current working directory as cwd.
       Surface its stdout/stderr to the user.
    3. On exit 0: print `CodeGraph: initialized ✓` and merge
       `{"codegraph": {"init_accepted": true}}` into `.claude/init-state.json`.
    4. On non-zero exit N: print
       `CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph.`
       Do NOT modify `.claude/init-state.json`.
  - On any other response: merge `{"codegraph": {"init_declined": true}}`
    and continue silently.

`.claude/init-state.json` uses a top-level `codegraph` key so future plugins
can claim sibling keys without collision. Always merge into existing JSON
rather than overwriting it.

## Step 3 — Select languages

Ask the user which language ecosystems they are working with. Allow multiple
selections:

> "Which languages do you need mutation testing for? (Select all that apply)"
>
> 1. **JS/TS** — Stryker (`@stryker-mutator/core`)
> 2. **Java / Kotlin** — pitest (`pitest-maven` or `info.solidsoft.gradle.pitest`)
> 3. **C# / .NET** — Stryker.NET (`dotnet-stryker`)
> 4. **All of the above**
> 5. **None — just install jq and python3**

Parse the user's response. If they choose 4, treat it as selecting 1, 2, and 3.

## Step 4 — Install per-language mutation tools

Run only the sections for the languages the user selected.

---

### JS/TS — Stryker

**Prerequisites check:**

```bash
command -v node && node --version
command -v npm  && npm --version
```

If `node` or `npm` is not found, tell the user:
"Node.js is required for Stryker. Install it from <https://nodejs.org> and
re-run `/init-dev-team`." Do not proceed with this language section.

**Bootstrap project if package.json is missing:**

```bash
test -f package.json && echo "package.json found" || echo "no-package"
```

If the result is `no-package`:

1. Print: `No package.json found. Running /agentic-dev-team:js-project-init first to scaffold the project.`
2. Invoke the `/agentic-dev-team:js-project-init` skill. It will scaffold a
   functional ES-module project with prettier, eslint, editorconfig, and
   vitest (see the skill's own documentation for the full default set).
3. After the skill returns:
   - If `package.json` now exists → proceed to "Check if already installed".
   - If `package.json` still does not exist (user aborted js-project-init):
     print `Stryker skipped — no package.json. Re-run /init-dev-team after scaffolding your JS project.`
     and skip the rest of the JS/TS section.
   - If the skill reported an explicit failure: print
     `Stryker skipped — js-project-init failed. See errors above and re-run /init-dev-team after resolving them.`
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
|-----------------|----------------|
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

---

### Java / Kotlin — pitest

**Prerequisites check:**

```bash
command -v mvn   && echo "maven found"
command -v gradle && echo "gradle found"
```

If neither is found, tell the user:
"Maven or Gradle is required for pitest. Install one from
<https://maven.apache.org> or <https://gradle.org> and re-run `/init-dev-team`."

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

### C# / .NET — Stryker.NET

**Prerequisites check:**

```bash
command -v dotnet && dotnet --version
```

If `dotnet` is not found, tell the user:
".NET SDK is required for Stryker.NET. Install it from <https://dotnet.microsoft.com>
and re-run `/init-dev-team`."

**Check if dotnet-stryker already installed:**

```bash
dotnet tool list --global 2>/dev/null | grep stryker
dotnet tool list --local  2>/dev/null | grep stryker
```

**If not installed globally or locally, install as a local tool:**

Create or update `.config/dotnet-tools.json`:

```bash
# If the file doesn't exist, create the tool manifest
test -f .config/dotnet-tools.json || dotnet new tool-manifest

# Install dotnet-stryker as a local tool
dotnet tool install dotnet-stryker
```

If the user prefers global install (e.g., using Stryker across many projects),
offer:

```bash
dotnet tool install --global dotnet-stryker
```

**Verify:**

```bash
dotnet stryker --version 2>/dev/null || dotnet tool run dotnet-stryker --version
```

---

## Step 4.5 — Probe model availability (opt-in)

Present the following prompt **verbatim** to the user and read a single
character from stdin:

```
Probe Anthropic's model list to detect which tiers are available?

  What this does:    one GET request to $ANTHROPIC_BASE_URL/v1/models (5s timeout)
  What it writes:    .claude/model-overrides.json (only if a default tier is missing)
  What it skips:     Bedrock, Vertex, or non-Anthropic proxies (auto-detected)
  Default is "n":    the resolver works without probing; this just makes the
                     first dispatch faster for restricted endpoints.

Probe model availability? [y/N]
```

If the user answers "y" or "Y", run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/lib/model-probe.sh" <<<"y"
```

`${CLAUDE_PLUGIN_ROOT}` is set by Claude Code when running plugin commands and resolves to the installed plugin directory. The repo-layout path `plugins/agentic-dev-team/hooks/lib/model-probe.sh` only works when running from the plugin source tree and must not be used here.

The probe writes `.claude/model-overrides.json` only when a default
tier is missing from the endpoint's `/v1/models` response. On any
failure (timeout, HTTP 5xx, malformed JSON, non-Anthropic host) it
emits a single explanatory line and continues — `/init-dev-team` exit
status is unaffected.

Skip the probe and continue to Step 5 if the user answers anything
other than "y" or "Y" (including pressing Enter to accept the default).

---

## Step 5 — Summary

Print a summary of what was installed:

```
agentic-dev-team: init complete

Hard dependencies:
  jq:       ✓ <version>
  python3:  ✓ <version>

Mutation testing:
  JS/TS  (Stryker):          ✓ <version>   [or: ✗ skipped | ✗ failed]
  Java   (pitest-maven):     ✓ configured  [or: ✗ skipped | ✗ manual steps needed]
  C#     (Stryker.NET):      ✓ <version>   [or: ✗ skipped | ✗ failed]

The mutation gate will now block zero-kill tests after each RED→GREEN transition.
Run a test suite to verify: when tests go from failing to passing, the gate
should analyze them within 60 seconds.
```

If any step failed, add a "Next steps" section with the specific manual actions
needed.
