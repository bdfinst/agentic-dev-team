---
name: project-init
description: Get a repository ready for the dev-team toolchain in one command — detect the tech stack (JS/TS, Python, C#, Java), inventory the static-analysis tools the project already has, confirm a plan, and install only what's missing, repo-level. This is the canonical source of truth for tech-stack detection and toolchain installation — NOT dev-team-specific config (CLAUDE.md generation, agent template activation, PostToolUse hooks, the generated `/pr` command all live in `/setup`, which invokes this skill first for the stack signal). Also installs the detection-gated capability tools other skills depend on — semgrep, Playwright + Chromium, adr, gh, and the docker scanners (hadolint/trivy/grype). For JavaScript it scaffolds a new project with ES modules, functional style, prettier, oxlint, editorconfig, vitest, and gitignore. Use this skill whenever the user wants to start a new JS project, scaffold a Node.js app, create a new package, bootstrap a JavaScript repo, or says things like "init a new project", "set up a JS project", "create a new node app", "start a new frontend project", or "bootstrap a new package". Also trigger when the user says "set up my project's toolchain", "install the linters for this repo", "get this repo ready for the plugin", or asks to add standard tooling (linting, formatting, testing) to a new or existing project in any supported language.
role: worker
user-invocable: true
---

# Project Initializer

One command to get a repository ready for the dev-team toolchain, whatever
the stack. Detect the project's language(s), inventory the static-analysis
tools already present, confirm a three-column plan, then install only the
missing tools — lane tools and Playwright always repo-level, never
user-level or global. It then installs the detection-gated **capability
tools** other skills depend on (semgrep, Playwright, adr, gh, docker
scanners — see Step 4b), which are user/system-level CLIs by nature.

Supported stacks: **JS/TS**, **Python**, **C#**, **Java** — the four lanes
registered in
`${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/references/tool-configs.md`
§ Build-time lanes. Tool facts (choice, versions, install mechanism) follow
that registry; provider-binding semantics (capability slots, ordered
provider lists, bind-don't-replace, the qualification contract) follow
`${CLAUDE_PLUGIN_ROOT}/skills/build/references/static-self-heal.md`. The
manual commands stay documented in
`${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/references/language-setup.md`;
this skill automates them.

## Workflow

### Step 1: Detect the stack

Probe the working directory with cheap, deterministic filesystem signals —
no builds, no network:

| Signal | Stack |
|---|---|
| `package.json`, `tsconfig.json`, `*.js`/`*.jsx`/`*.ts`/`*.tsx` sources | JS/TS |
| `pyproject.toml`, `requirements*.txt`, `setup.cfg`/`setup.py`, `*.py` sources | Python |
| `*.sln`, `*.csproj`, `global.json` | C# |
| `pom.xml`, `build.gradle`/`build.gradle.kts`, `*.java` sources | Java |

- **Multiple stacks detected** → multi-stack setup: run every matched
  language's inventory and install, mirroring the self-heal pass's
  mixed-language lane dispatch.
- **Zero or ambiguous signals** (empty dir, README-only repo) → **ask the
  user**: present the four supported stacks plus "something else".
  "Something else" explains what's supported and exits gracefully — no
  files written, nothing installed.

### Step 2: Inventory the existing toolchain

Stack detection says which lanes apply; the inventory then establishes, per
capability slot (**autofix** / **diagnostic**, as the lane registry defines
them), which recognized provider — if any — the project already has. Three
signal classes, still cheap and deterministic — no builds, no network:

1. **Config-file signals** — `eslint.config.js`/`.eslintrc*`, `biome.json`,
   `[tool.ruff]`/`[tool.black]`/`[tool.mypy]` sections in `pyproject.toml`,
   `.flake8`/`setup.cfg` sections, `.pylintrc`, `checkstyle.xml`, PMD
   rulesets (`pmd-ruleset.xml`).
2. **Dependency signals** — `package.json` devDependencies,
   `requirements-dev.txt`/the `pyproject.toml` dev group, Maven/Gradle
   plugin blocks.
3. **Executable probes** — the lane registry's detection probes, run per
   candidate provider down each slot's ordered provider list
   (`tool-configs.md` § Build-time lanes; repo-local locations first,
   then PATH).

Binding follows **bind-don't-replace**: an existing, configured tool that
passes the qualification contract is bound as its slot's provider, and the
plugin's default is never installed over it. A bound equivalent — black +
flake8 as a pair, biome, an ESLint kept under demotion, checkstyle —
satisfies its slot; nothing is installed for it.

### Step 3: Confirm the three-column plan

Detection is always confirmed, never assumed. Present the stack + inventory
results as a three-column plan and wait for the user to confirm it
**before any file is written or any install runs**:

1. **Found and keeping** — providers the inventory bound. Nothing is
   installed for these slots, and existing configs (`eslint.config.js`,
   `pyproject.toml` sections, `.editorconfig`, …) are never overwritten —
   this column doubles as the report of what already exists and is left
   alone.
2. **Missing and will add** — empty slots to be filled with the lane's
   default tool. **Only this column installs anything.**
3. **Found but can't participate** — a present tool that fails the
   qualification contract (e.g. pyright before its adapter exists), with
   the reason stated and the lane default offered alongside — never a
   silent replacement.

The mode follows from what detection found:

- **Existing project** (sources present) → tools-only mode, driven entirely
  by the three columns: bind, fill empty slots, surface non-conforming
  tools. No existing config file is modified.
- **Greenfield JS/TS** (empty or near-empty dir) → the full scaffold below;
  its defaults are presented as this plan's **missing and will add**
  column.
- **Greenfield Python/C#/Java** → tools plus minimal config (full
  config-scaffold parity with the JS path lands as per-language
  follow-ups).

### Step 4: Install missing tools (repo-level, per lane)

Every install lands in the project, versioned with it, reproducible for
every contributor and CI — never `pip install --user`, never a global
pipx install, never `npm install -g`.

- **JS/TS** — greenfield: the full scaffold below (oxlint as the default
  linter, ESLint behind `lint:deep`). Existing project: fill the empty
  autofix slot as a devDependency, leaving all configs alone:

  ```bash
  npm install --save-dev oxlint
  ```

  If this fails with `npm error code ERESOLVE`, the peer conflict is
  pre-existing in the repo's tree (not with `oxlint`) — retry once with
  `--legacy-peer-deps` and note to the user that you did so, rather than
  aborting.

- **Python** — add `ruff` and `mypy` — plus `pytest` if no test runner is
  present — to the project's own dev-dependency mechanism: the
  `pyproject.toml` dev group or `requirements-dev.txt`, whichever the
  project already uses; create `requirements-dev.txt` if neither exists.
- **C#** — nothing to install: both lane tools ship with the .NET SDK.
  Verify the SDK is present — honoring a `global.json` pin when one
  exists — and that `dotnet format --version` responds.
- **Java** — verify a JDK is present (`java` on PATH), then run the
  plugin's pinned-PMD installer — the user never locates or invokes it by
  hand:

  ```bash
  python3 scripts/install-java-static-analysis.py
  ```

  It installs a pinned PMD distribution into the repo-local, gitignored
  `.pmd/` directory (version pin single-sourced in the script; re-runs are
  idempotent). Add the `.pmd/` entry to the project's `.gitignore` if it
  is missing.

### Step 4b: Install capability tools

Beyond the four static-analysis lanes, other skills and agents depend on a
set of **capability tools**. `references/capability-tools.md` is their single
source of truth — a registry of *tool | skills that need it | offer-when
signal | OS-aware install command | verify probe*. This step installs the
warranted ones so the "run `/project-init`" pointer those skills print is
honest.

**Run the detection signals** (cheap, deterministic — no builds, no network):

| Capability | Skills served | Offer-when signal |
|---|---|---|
| semgrep | `/semgrep-analyze`, security-assessment | any source lane detected (universal SAST) — always offer, opt-in |
| Playwright + Chromium | `/benchmark`, `/browse`, `/browser-testing`, `/performance-benchmark` | frontend signals (React/Svelte/Vue/Angular/Next/Nuxt/SvelteKit/Astro, or an `e2e/` dir, or `playwright.config.*`) in an existing project |
| adr | `/adr-tools`, adr-author | `docs/adr/`, `docs/decisions/`, or existing ADR `*.md` files present |
| gh | `/issues-from-assessment` and other issue/PR skills | git repo with a GitHub remote (`git remote -v` shows `github.com`) |
| docker scanners (hadolint, trivy, grype) | `/docker-image-audit` | a `Dockerfile`/`*.dockerfile`/`compose.y*ml` present |

**Present the warranted capability tools as their own group** in the Step 3
three-column plan — a "capability tools" block alongside the lane columns —
and **confirm before installing**, same gate as the lanes. Install only the
tools whose signal fired *and* that the user confirmed *and* that are still
missing (skip any already on `PATH`). Use the OS-aware install command from
`references/capability-tools.md` for each — never inline a different command.

**Install-level honesty.** The "always repo-level, never user/system" rule
of the lanes applies to the lane tools **plus Playwright**. The other
capability tools are general-purpose CLIs that are **user/system-level by
nature** — there is no repo-local install for `gh`, `semgrep`, `adr`, or the
docker scanners, so they install via the OS package manager (or pipx / user
pip on Linux). **Playwright is the repo-level exception among capability
tools**: it installs as an `npm` devDependency (`@playwright/test`), versioned
with the project like a lane tool — only its Chromium download is machine-level.
State this explicitly to the user when the capability group installs. If the
Playwright `npm` install fails with `npm error code ERESOLVE`, the peer
conflict is pre-existing in the repo's tree (`@playwright/test` has no
framework peer relationship) — retry that install once with
`--legacy-peer-deps` and note to the user that you did so, rather than
aborting.

### Step 4c: Offer the three code-lookup tools (all-or-none)

Three optional, complementary code-intelligence tools — **CodeGraph**,
**Repowise**, and **Graphify** — let the review and analysis agents read
verified skeletons, resolved call graphs, modification risk, and decision
rationale instead of re-reading whole files. None is required. They are
offered as **one all-or-none group** rather than three separate prompts, so
the operator makes a single decision and the agents get a consistent,
predictable set of lookup capabilities (see issue #1108).

Accepting the group both **installs and builds** every missing tool's index in
this same run — it is not a "print instructions and leave it to the user" step
(issues #1134, #1135):

- **CodeGraph and Repowise are keyless** — they build a purely structural
  index with **no model/API key** and are safe to build unattended. CodeGraph
  installs its CLI (`npm install -g @colbymchenry/codegraph`) and runs
  `codegraph init .`; Repowise installs and runs a `--index-only` index.
- **Graphify additionally requires a model/API key** to build its graph — its
  extraction is LLM-driven, heavier, and produces a different kind of graph.
  Because all three are offered as one all-or-none group, the group prompt
  **must disclose Graphify's key requirement up front** so accepting is never a
  surprise key cost. When Graphify is absent the agents that use it fall back
  gracefully (see `knowledge/codegraph-vs-graphify.md`).

**Detect which are already present** (so re-runs are idempotent and the group
scopes to the *missing* set):

- CodeGraph — `command -v codegraph` succeeds **and** `.codegraph/` exists.
- Repowise — the Repowise MCP server is registered / `.repowise/` exists.
- Graphify — `command -v graphify` succeeds **and** `graphify-out/graph.json` exists.

Also read `.claude/init-state.json`: honor any prior **explicit decline**
(e.g. `codegraph.install_declined == true`) — a declined tool is excluded from
the "missing" set rather than silently re-offered, and the existing unstick
instruction still applies (`remove the <tool> key from .claude/init-state.json
to re-prompt`).

**The group prompt.** Compute the *missing* set = tools that are neither
already present nor previously declined.

- If the missing set is **empty**: print
  `Code-lookup tools: all present (or previously declined) — nothing to install.`
  and continue. No prompt.
- Otherwise, first show the user the "When to use which" section of
  `${CLAUDE_PLUGIN_ROOT}/knowledge/codegraph-vs-graphify.md`, then prompt
  **once**, listing the missing tools by name and disclosing Graphify's repo
  footprint (this is an explicit `y`/`n`, and the recommended default is
  **yes** when anything is missing):

  ```
  Install the code-lookup tools <missing list> to enable faster, verified
  code navigation for the review and analysis agents? [Y/n]
    - CodeGraph  — personal, user-level MCP; nothing committed to the repo.
                   Keyless: `npm install -g @colbymchenry/codegraph` + `codegraph init .`.
    - Repowise   — local keyless index under .repowise/ (gitignored); MCP server.
                   Keyless: `--index-only`, no API key requested.
    - Graphify   — repo-level: writes a `## graphify` section into this repo's
                   CLAUDE.md and installs git hooks (guarded against the known
                   over-delete bug — see the Graphify sub-section).
                   REQUIRES a model/API key to build its graph — heavier than
                   the keyless indexes above; declining the group skips this cost.
  ```

  The prompt copy above must always disclose Graphify's model/API-key
  requirement (issue #1135) — CodeGraph and Repowise are keyless, Graphify is
  not, and the operator is accepting all three as one decision.

- On **yes**: install **every** tool in the missing set by running its
  sub-section below (CodeGraph, Repowise, Graphify), recording each tool's
  accept in `.claude/init-state.json`.
  - **Partial failure is surfaced, never hidden.** If one tool's install
    errors after another already succeeded, print the failing tool's error,
    record per-tool success/failure in `.claude/init-state.json`, and report
    the group as *partially installed* — do not claim all three succeeded.
- On **no** (or empty): install nothing, record the group decline for each
  missing tool in `.claude/init-state.json`, and print a terminal-visible
  confirmation so the operator knows the choice was durable and reversible:
  `Code-lookup tools: skipped — agents fall back to Read/Grep/Glob (re-run /project-init to be offered again).`

The per-tool mechanics below are unchanged; the all-or-none group only decides
*whether* they run. Each remains user-scoped/gitignored exactly as before.

#### CodeGraph — strictly personal, never committed

CodeGraph (<https://github.com/colbymchenry/codegraph>) is a third-party
SQLite knowledge graph of every symbol, edge, and file in the workspace.
**It is user-level tooling only** — nothing it produces or registers is
ever written into a repo-tracked file. `.codegraph/codegraph.db` stays
gitignored and machine-local, exactly as it already does.

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
| any       | true        | Print "CodeGraph: initialized ✓" and continue. State file untouched. |
| true      | false       | **Init prompt branch** (below). |
| false     | false       | **Install prompt branch** (below). |

**Stale-state override.** Before consulting the recorded state, apply these
rules: `install_declined` is ignored when `installed=true` (the user has
since installed CodeGraph); `init_declined` is ignored when
`initialized=true` (the project got initialized by other means). The live
filesystem/PATH check supersedes the recorded preference.

**Install prompt branch** (installed=false, initialized=false):

- If `.codegraph.install_declined == true`: print
  `CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)`
  and continue.
- Otherwise prompt: `Install CodeGraph for code intelligence? (y/N)`
  - On `y`/`Y`: install the CodeGraph CLI (machine-level, keyless — nothing is
    committed to the repo):

    ```bash
    npm install -g @colbymchenry/codegraph
    ```

    - On success: merge `{"codegraph": {"install_accepted": true}}` into
      `.claude/init-state.json` and **fall through to the init step below**
      (`codegraph init .`) so the index is built in this same run — this is
      what issue #1134 requires (install *and* build, not just instructions).
    - **Non-fatal on failure** (npm missing, or the install errors): print
      `CodeGraph install failed — install it manually: https://github.com/colbymchenry/codegraph#installation`,
      merge `{"codegraph": {"install_failed": true}}`, and continue. Per the
      group's partial-failure rule, report the tool as failed rather than
      aborting the rest of setup.
  - On any other response (including empty): merge
    `{"codegraph": {"install_declined": true}}` and continue silently.

**Init prompt branch** (installed=true, initialized=false):

- If `.codegraph.init_declined == true`: print
  `CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)`
  and continue.
- Otherwise prompt:
  `CodeGraph is installed but not initialized in this project. Initialize now? (y/N)`
  - On `y`/`Y`:
    1. Print: `Running 'codegraph init .' in this project...`
    2. Execute `codegraph init .` — **non-interactive** (no `-i`; issue #1134),
       targeting the current working directory. Surface its stdout/stderr to
       the user.
    3. On exit 0: print `CodeGraph: initialized ✓`, merge
       `{"codegraph": {"init_accepted": true}}` into
       `.claude/init-state.json`, then register the MCP server (below).
    4. On non-zero exit N: print
       `CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph.`
       Do NOT modify `.claude/init-state.json`.
  - On any other response: merge `{"codegraph": {"init_declined": true}}`
    and continue silently.

**Register the MCP server at user scope (never a repo file).** After a
successful init, CodeGraph must be registered the same way any personal MCP
server is added for this Claude Code installation — **not** written into a
project's `.mcp.json`, and no `.codegraph/` directory is ever committed.
Print the manual command for the user to run themselves at user scope:

```
claude mcp add codegraph -- codegraph serve --mcp
```

Note the exact CLI flag for user-scope registration may vary by Claude Code
version — point the user at `claude mcp add --help` if the command above is
rejected. Do not attempt to write `.mcp.json` in the project root, and do
not run `git add`/`git commit` for anything under `.codegraph/`.

`.claude/init-state.json` uses a top-level `codegraph` key so future plugins
can claim sibling keys without collision. Always merge into existing JSON
rather than overwriting it.

#### Repowise — keyless local index, MCP server

Repowise (`repowise` on PyPI) is a codebase-documentation engine that indexes
the repo and exposes it as an MCP server
(`mcp__plugin_repowise_repowise__{get_context,get_symbol,search_codebase,get_risk,get_why}`).
It installs and indexes **without any LLM API key** and stores its index under
`.repowise/`.

Run this tool's install/index through the `repowise-setup` skill (or the
`index-codebase` skill), which handles the install (`uv`/`pipx`/`pip`), adds
`.repowise/` to git's **global** ignore so the index never clutters the repo,
and runs a **keyless** index (`--index-only`, no provider key requested).

**Install steps (executed only when the all-or-none group is accepted):**

1. Install: prefer `uv tool install repowise`, else `pipx install repowise`,
   else `python3 -m pip install --user repowise`.
2. Index keyless: run the repowise index in `--index-only` mode so no API key
   is requested; the index lands under `.repowise/` (gitignored).
3. Register the MCP server for this Claude Code installation (user scope), the
   same way any personal MCP server is added — point the user at
   `claude mcp add --help` for the exact invocation. **Server-name caveat:**
   the agents' grants assume the server name `plugin_repowise_repowise`; if a
   different name is used the grants are inert and agents fall back to
   `Read`/`Grep`/`Glob`.
4. On success, merge `{"repowise": {"install_accepted": true}}` into
   `.claude/init-state.json`. On failure, surface the error and merge
   `{"repowise": {"install_failed": true}}` — do not claim the group fully
   installed (see the partial-failure rule above).

**Detection probe** (used by the group's "already present" check and re-runs):

```bash
command -v repowise > /dev/null 2>&1 && echo "installed" || echo "not-installed"
[ -d "${PWD}/.repowise" ] && echo "indexed" || echo "not-indexed"
```

#### Graphify — native integration, opt-in, with a CLAUDE.md guard

Graphify (`graphifyy` on PyPI) is a multi-modal knowledge graph tool
(code + docs + schemas + infra + images/video). Unlike CodeGraph it is a
**repo-level native integration** — its installer writes a `/graphify`
skill, PreToolUse nudge hooks into `.claude/settings.json`, and a
`## graphify` section into the project's own `CLAUDE.md`.

Prompt: `Install graphify for architecture/onboarding-level code intelligence? (y/N)`
On any response other than `y`/`Y`, skip silently.

**Install (fallback chain):**

```bash
command -v uv > /dev/null 2>&1 && uv tool install graphifyy \
  || command -v pipx > /dev/null 2>&1 && pipx install graphifyy \
  || python3 -m pip install --user graphifyy
```

**Native integration, with the CLAUDE.md corruption guard.** Graphify's
`install --project` updater matches the literal `## graphify` header and
replaces everything between it and the next `##` heading — a known bug can
over-delete, taking unrelated pre-existing content with it. Guard every run:

1. **Snapshot** the project's `CLAUDE.md` before installing — a plain file
   copy (e.g. `cp CLAUDE.md /tmp/claude-md-pre-graphify.bak`, or a
   project-local temp path), regardless of whether the repo is git-tracked.
   `git stash` is unsafe mid-flow and must not be used.
2. Run the installer:

   ```bash
   graphify install --project
   graphify hook install
   ```

3. **Diff** the snapshot against the post-install `CLAUDE.md`. If any line
   present in the snapshot is missing from the new file, treat it as the
   known corruption bug. (`scripts/lib/claude_md_guard.py` implements this
   snapshot/diff/restore logic in isolation and is unit-tested at
   `tests/scripts/test_claude_md_guard.py` — reuse its
   `run_install_with_guard` function rather than re-deriving the diff by
   hand.)
4. **On detected corruption:** restore the snapshot, then append the
   canonical `## graphify` section text at EOF yourself. Source the
   canonical text either by capturing graphify's own generated section from
   a clean scratch-dir install first, or by reusing the fixed template that
   matches this repo's own root `CLAUDE.md` `## graphify` section (see
   `/home/user/agentic-dev-team/CLAUDE.md` for the canonical section this
   repo already carries).
5. **On no corruption detected:** leave the installer's output as-is —
   nothing further to do.

**Build the graph (requires a model/API key — issue #1135).** Unlike the
keyless CodeGraph/Repowise indexes, graphify's extraction is LLM-driven and
needs a model/API key — this is the cost the group prompt discloses.

- **Idempotent:** if `graphify-out/graph.json` already exists, skip extraction
  and offer the incremental, no-key refresh instead:

  ```bash
  graphify update .
  ```

- **Otherwise build it:**

  ```bash
  graphify extract .
  ```

  This writes `graphify-out/graph.json` (gitignored) plus `GRAPH_REPORT.md`.
- **Non-fatal:** if extraction fails (e.g. no model/API key is configured),
  print the error, merge `{"graphify": {"build_failed": true}}` into
  `.claude/init-state.json`, and continue — never abort the rest of setup, and
  never claim the group fully installed (the partial-failure rule). Agents that
  consume graphify fall back to `Read`/`Grep`/`Glob` when `graphify-out/` is
  absent (see `knowledge/codegraph-vs-graphify.md`).

**Gitignore advice.** `graphify hook install` creates machine-specific
generated git hooks. Tell the user to gitignore them the same way this
repo's own root `.gitignore` does for its own graphify hooks:

```gitignore
graphify-out/
.husky/post-commit
.husky/post-checkout
```

(Or `.git/hooks/post-*` if the target repo does not use husky.)

### Step 5: Verify — post-install probes

Run each configured lane's detection probe exactly as the lane registry
defines it, and report per-lane status — including which provider each
slot bound — so the user knows `/build`'s self-heal pass will find the
tools:

| Lane | Probe |
|---|---|
| Python | `command -v ruff`, `command -v mypy` |
| JS/TS | `npx --no-install oxlint --version` (bound alternatives verify the same way: `npx --no-install biome --version`, `npx --no-install eslint --version`) |
| C# | `command -v dotnet` |
| Java | `.pmd/pmd-bin-*/bin/pmd` launcher first, then `command -v pmd` |

Then probe every capability tool that Step 4b installed, using its verify
command from `references/capability-tools.md`:

| Capability | Probe |
|---|---|
| semgrep | `semgrep --version` |
| Playwright | `npx --no-install playwright --version` |
| adr | `adr help` |
| gh | `gh --version` |
| docker scanners | `hadolint --version`, `trivy --version`, `grype --version` |
| codegraph | `command -v codegraph`, `.codegraph/` present |
| graphify | `graphify --version` |

A capability tool that was offered but not confirmed, or whose signal never
fired, is simply not probed — it is not a failure.

### Step 6: Summary

After every configured lane probes green, give the user:

- Per lane, per slot: the bound provider — kept (column 1) or newly
  installed (column 2).
- Configs and tools found and left alone (columns 1 and 3 double as this
  report).
- Any **found but can't participate** entry, with its reason and the
  default offered alongside.
- **Capability tools** (Step 4b): which were offered, which were installed,
  and which were skipped (signal didn't fire, or the user declined) — noting
  Playwright is repo-level and the rest are user/system-level CLIs.
- **Graph tools** (Step 4c): CodeGraph state (installed/initialized, MCP
  registration command printed or skipped) and graphify state (installed,
  native integration applied, whether the CLAUDE.md corruption guard fired
  and repaired anything) — noting CodeGraph is strictly user-level/personal
  and graphify is the repo-level native integration.
- Files created (greenfield only).

## Greenfield JS/TS scaffold

Scaffold a new JavaScript project with opinionated defaults for ES modules,
functional development, and modern tooling. Goal: zero to
working/linted/tested in under a minute, with every config file explained
and customizable.

Defaults:
- **Package manager**: npm
- **Module system**: ES Modules (`"type": "module"`)
- **Style**: functional — no classes, prefer `const`, no mutation
- **Formatter**: Prettier (2-space indent, single quotes, trailing commas, 100-char width)
- **Linter**: oxlint — fast (Rust-based, ESLint-compatible) per-step linter for day-to-day `lint`/`lint:fix`; ESLint flat config with functional rules stays available as the deep pass (`lint:deep`) for plugin-only rules
- **Editor**: EditorConfig (2-space, UTF-8, LF, trim trailing whitespace, final newline)
- **Tests**: Vitest
- **E2E** (frontend only): Playwright
- **Git hooks**: Husky pre-commit (lint-staged auto-fix of staged files) + pre-push (test)
- **`.gitignore`**: node_modules, dist, build, coverage, .env, .env.*, OS files

This scaffold is the **base tooling layer**. It does not replace
framework-specific CLIs (`npx sv create`, `ng new`, `npm create
vite@latest`). For a full framework scaffold, run the framework CLI first,
then layer on these configs.

### Scaffold step 1: Present defaults and confirm

Present the defaults above as the three-column plan's **missing and will
add** column and ask: "Want to change anything, or should I go ahead?"
Include Playwright in the summary only if the user mentions a frontend
project (React, Svelte, Angular, Vue, Next.js, Nuxt, SvelteKit, Astro, UI,
web app, dashboard). Wait for confirmation before writing files.

### Scaffold step 2: Initialize package.json

```bash
npm init -y
```

Read the generated `package.json`, then edit to:
- Add `"type": "module"`
- Add the scripts block below
- Remove fields that don't apply (e.g., `"main"` for non-libraries)

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "lint": "oxlint .",
    "lint:fix": "oxlint --fix .",
    "lint:deep": "eslint .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "prepare": "husky"
  },
  "lint-staged": {
    "*.{js,mjs,cjs}": ["prettier --write", "oxlint --fix"],
    "*.{json,md,yaml,yml}": ["prettier --write"]
  }
}
```

`lint-staged` runs Prettier (and oxlint `--fix` on JS) against only the staged
files on each commit, so formatting/lint drift is corrected automatically before
it lands — without scanning the whole tree. `lint:deep` runs the full ESLint
pass for the framework-plugin rules oxlint lacks.

Frontend projects also add: `"test:e2e": "playwright test"`.

### Scaffold step 3: Install dependencies

```bash
npm install -D eslint prettier vitest @eslint/js eslint-config-prettier husky lint-staged oxlint
```

If this (or the Playwright install below) fails with `npm error code
ERESOLVE`, the peer conflict is pre-existing in the repo's tree, not with the
tooling being added — retry the failing command once with `--legacy-peer-deps`
and note to the user that you did so, rather than aborting.

`eslint-config-prettier` disables ESLint rules that conflict with Prettier. Do NOT install `eslint-plugin-prettier` — run Prettier as a separate step (`npm run format:check`), not through ESLint.

Frontend projects also:

```bash
npm install -D @playwright/test
npx playwright install
```

### Scaffold step 4: Create config files

Templates: `references/configs.md`. Required files:

1. `eslint.config.js` — flat config with functional rules (no classes, prefer const, no var, no param reassign)
2. `prettier.config.js` — 2-space, single quotes, trailing commas, 100-char width
3. `.editorconfig` — 2-space, UTF-8, LF, trim trailing whitespace, final newline
4. `.gitignore` — node_modules, dist, build, coverage, .env, .env.*, OS files (DS_Store, Thumbs.db)
5. `vitest.config.js` — minimal config pointing at test files
6. (frontend) `playwright.config.js` — chromium, sensible defaults

### Scaffold step 5: Create starter files

```
src/index.js        — single exported pure function with JSDoc (e.g., greet or add)
src/index.test.js   — one passing vitest test for the starter function
```

Frontend projects also create `e2e/example.spec.js` — one Playwright placeholder.

### Scaffold step 6: Git hooks

```bash
git init  # skip if already a git repo
npx husky init
```

Create both hooks (templates in `references/configs.md`):

```bash
echo 'npx lint-staged' > .husky/pre-commit
echo 'npm test' > .husky/pre-push
```

`npx husky init` writes a default `pre-commit`; the command above overwrites it.

Frontend projects also run the e2e suite on push:

```bash
echo 'npm test
npm run test:e2e' > .husky/pre-push
```

The pre-commit hook auto-fixes only the staged files (`prettier --write` +
`oxlint --fix`) so the commit loop stays fast and clean; the pre-push hook runs
the test suite to gate what goes upstream. Because lint-staged formats and lints
on commit, the redundant `npm run format:check` and `npm run lint` steps are no
longer needed on pre-push.

### Scaffold step 7: Verify

```bash
npm run lint
npm run format:check
npm test
```

If any command fails, fix it before reporting success. Show the user the test
output, then finish with the shared Step 5 probes and Step 6 summary above.

## Customization handling

If the user changes the scaffold defaults:

| Request | Update |
|---|---|
| Different indent size | prettier config, editorconfig, eslint indent rule |
| Tabs instead of spaces | prettier (`useTabs: true`), editorconfig (`indent_style = tab`) |
| Double quotes | prettier (`singleQuote: false`) |
| Different print width | prettier config |
| Semicolons | prettier (`semi: true/false`) |
| Yarn / pnpm | substitute the package manager in all install commands; adjust scripts if needed |
| TypeScript | the scaffold's starter files are JS-only — run the framework/TS CLI first, then re-run this skill for the toolchain layer |
| Additional ESLint plugins | install and add to the flat config array |
