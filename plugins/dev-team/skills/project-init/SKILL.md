---
name: project-init
description: Get a repository ready for the dev-team toolchain in one command — detect the tech stack (JS/TS, Python, C#, Java), inventory the static-analysis tools the project already has, confirm a plan, and install only what's missing, repo-level. This is the canonical source of truth for tech-stack detection and toolchain installation — NOT dev-team-specific config (CLAUDE.md generation, agent template activation, PostToolUse hooks, the generated `/pr` command all live in `/setup`, which invokes this skill first for the stack signal). Also installs the detection-gated capability tools other skills depend on — semgrep, Playwright + Chromium, adr, gh, and the docker scanners (hadolint/trivy/grype). For JavaScript it scaffolds a new project with ES modules, functional style, prettier, oxlint, editorconfig, vitest, and gitignore. Use this skill whenever the user wants to start a new JS project, scaffold a Node.js app, create a new package, bootstrap a JavaScript repo, or says things like "init a new project", "set up a JS project", "create a new node app", "start a new frontend project", or "bootstrap a new package". Also trigger when the user says "set up my project's toolchain", "install the linters for this repo", "get this repo ready for the plugin", or asks to add standard tooling (linting, formatting, testing) to a new or existing project in any supported language.
role: worker
user-invocable: true
argument-hint: "[--yes]"
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

## Arguments

Arguments: $ARGUMENTS

- `--yes`: Run unattended — auto-confirm each gate below with its **safe**
  default and never wait for input. `/setup --yes` passes this through.

### `--yes` semantics

**Affirmative** (auto-confirm, no prompt):

- **Step 3 three-column plan** — proceed: install the "missing and will add"
  column's defaults, repo-level. Existing configs are still never overwritten
  (that is already the plan's contract, not a prompt).
- **Step 4b capability tools** — install every tool whose detection signal
  fired and that is still missing. Tools whose signal did not fire are still
  not installed.
- **Step 4c keyless pair (CodeGraph + Repowise)** — install the missing
  members (their recommended default is already yes). Repowise's own write
  to the tracked `.claude/CLAUDE.md` (see its sub-section below) lands under
  `--yes` the same as it would interactively — it is intended, not a
  surprise mutation, so it does not move Repowise into the Conservative
  bucket below. Whether that same reasoning should also cover Graphify's
  repo-level writes is a separate policy question, tracked in #1690.

**Conservative** (skip with a printed note — never mutate the repo by
surprise):

- **Step 4c Graphify** — skipped for this run, because `graphify install
  --project` writes PreToolUse hook entries embedding this machine's
  absolute binary path into the shared, git-tracked `.claude/settings.json`
  (see the settings.json absolute-path guard, #1367, in the Graphify
  sub-section below) — a write that file cannot simply be gitignored out of
  (unlike the generated git hooks themselves, which are). Repowise's own
  `.mcp.json` write carries a comparable machine-specific path, but that
  file IS gitignored by the standing check below, so it doesn't force the
  same choice; #1690 tracks whether Graphify's own CLAUDE.md write (as
  opposed to its settings.json write) should also move to this bucket.
  Print
  `Graphify: skipped under --yes (repo-writing; run /project-init without --yes to add it)`
  and do **not** record a durable decline in `.claude/init-state.json`, so a
  later interactive run still offers it.
- **Step 1 zero/ambiguous stack** — never guess. Report the supported stacks
  and exit gracefully without writing files or installing anything, exactly as
  the interactive path's "something else" branch.
- **Greenfield JS/TS scaffold** — the confirm step proceeds with the documented
  defaults (no customization prompt); it only writes into an empty/near-empty
  directory, so nothing existing is overwritten.

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
  files written, nothing installed. **Under `--yes`, do not prompt** — never
  guess a stack: report the supported stacks and exit gracefully, exactly as
  the "something else" branch.

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
**before any file is written or any install runs** (**under `--yes`, print the
plan and proceed without waiting** — see the Arguments section):

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
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/install-java-static-analysis.py"
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
and **confirm before installing**, same gate as the lanes. **Under `--yes`,
install every warranted-and-missing tool without prompting** (see the
Arguments section). Install only the
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

### Step 4c: Offer the code-lookup tools (keyless group + keyless Graphify build)

Three optional, complementary code-intelligence tools — **CodeGraph**,
**Repowise**, and **Graphify** — let the review and analysis agents read
verified skeletons, resolved call graphs, modification risk, and decision
rationale instead of re-reading whole files. None is required.

They are offered by **cost profile**, so the operator never has to accept a
model/API-key cost to get the keyless tools (issue #1141, which relaxes the
single all-or-none group of #1108):

- **Keyless pair — CodeGraph + Repowise.** Both build a purely structural
  index with **no model/API key** and are safe to build unattended. They are
  offered as **one all-or-none group** — a single decision that gives the
  agents a consistent, predictable lookup set (issue #1108). Accepting the
  group both **installs and builds** every missing tool's index in this same
  run — it is not a "print instructions and leave it to the user" step (issues
  #1134, #1135). CodeGraph installs its CLI (`npm install -g
  @colbymchenry/codegraph`) and runs `codegraph init .`; Repowise installs and
  runs `repowise init . --no-prose -y` for a keyless index.
- **Graphify — full extraction is the target; `--code-only` is a degraded
  fallback, not the goal.** `graphify extract .` is Graphify's documented
  headless full extraction (**AST + semantic LLM pass**) — it is what indexes
  this plugin's multi-modal target (code + docs + schemas + infra) into the
  `graph.json` that `graphify query`/`path`/`explain` traverse. Only the
  **AST pass** builds with **no model/API key**; the **semantic pass** is what
  pulls docs and images into the graph at all — with no working backend, that
  pass is skipped and `--code-only` must be used explicitly, which excludes
  docs and images. Two further add-ons sit on top of a successful full
  extraction and are also key-gated: inferred edges (`extract --mode deep`)
  and human-readable community names (`graphify label`; without them
  communities stay `Community N` placeholders). Graphify is offered as
  **its own opt-in prompt after the keyless pair** — separate not because of a
  key, but because its integration is **repo-level** (it writes PreToolUse
  hook entries into this repo's tracked `.claude/settings.json` and a
  `## graphify` CLAUDE.md section; the generated git hooks it also installs
  are gitignored — see the sub-section below). On accept: with a
  working backend, run full extraction, repairing the backend's dependencies
  first if needed and never discarding a completed AST pass if the semantic
  pass then fails; without one, build the **code-only** graph and say so
  plainly — it is a degraded index, not the full one. When Graphify is absent
  the agents that use it fall back gracefully (see
  `knowledge/codegraph-vs-graphify.md`).

**Detect which are already present** (so re-runs are idempotent and each offer
scopes to the *missing* set):

- CodeGraph — `command -v codegraph` succeeds **and** `.codegraph/` exists.
- Repowise — the Repowise MCP server is registered / `.repowise/` exists.
- Graphify — `command -v graphify` succeeds, `graphify-out/graph.json` exists,
  **and** it is not a degraded build waiting on a key that has since shown up:
  if `.claude/init-state.json` has `graphify.code_only_build == true` **and** a
  provider key is now present, treat Graphify as still in the missing set (so
  the opt-in re-offers full extraction) rather than as already present — a
  `--code-only` graph must not permanently block ever reaching the full index
  (issue #1483). Otherwise, present.

Also read `.claude/init-state.json`: honor any prior **explicit decline**
(e.g. `codegraph.install_declined == true`) — a declined tool is excluded from
the "missing" set rather than silently re-offered, and the existing unstick
instruction still applies (`remove the <tool> key from .claude/init-state.json
to re-prompt`).

**The keyless group prompt.** Compute the *missing* set = the keyless tools
(CodeGraph, Repowise) that are neither already present nor previously declined.

- If the missing set is **empty**: print
  `Code-lookup tools: keyless pair present (or previously declined) — nothing to install.`
  and continue. No prompt.
- Otherwise, first show the user the "When to use which" section of
  `${CLAUDE_PLUGIN_ROOT}/knowledge/codegraph-vs-graphify.md`, then prompt
  **once**, listing the missing tools by name (this is an explicit `y`/`n`, and
  the recommended default is **yes** when anything is missing):

  ```
  Install the code-lookup tools <missing list> to enable faster, verified
  code navigation for the review and analysis agents? [Y/n]
    - CodeGraph  — personal, user-level MCP; nothing committed to the repo.
                   Keyless: `npm install -g @colbymchenry/codegraph` + `codegraph init .`.
    - Repowise   — local keyless index under .repowise/ (gitignored); MCP server.
                   Keyless: `init . --no-prose -y`, no API key requested. Also
                   adds a `## Codebase Intelligence for <project> (Repowise)`
                   section to the tracked .claude/CLAUDE.md documenting the
                   codebase — intended (confirmed by the repo owner, #1670
                   item 3), and committed along with the rest of this run's
                   changes, not reverted.
  ```

**Under `--yes`, treat the keyless-pair prompt as yes** and install the whole
missing set without waiting (its recommended default is already yes).

- On **yes**: install **every** tool in the missing set by running its
  sub-section below (CodeGraph, Repowise), recording each tool's accept in
  `.claude/init-state.json`.
  - **Partial failure is surfaced, never hidden.** If one tool's install
    errors after another already succeeded, print the failing tool's error,
    record per-tool success/failure in `.claude/init-state.json`, and report
    the group as *partially installed* — do not claim both succeeded.
- On **no** (or empty): install nothing, record the group decline for each
  missing tool in `.claude/init-state.json`, and print a terminal-visible
  confirmation so the operator knows the choice was durable and reversible:
  `Code-lookup tools: skipped — agents fall back to Read/Grep/Glob (re-run /project-init to be offered again).`

**The Graphify opt-in.** After the keyless pair, offer Graphify whenever it is
in the missing set (regardless of key presence — its AST graph builds keyless):

0. **Under `--yes`, skip Graphify for this run** — `graphify install
   --project` writes a machine-specific absolute path into the tracked
   `.claude/settings.json`, so it stays opt-in even unattended (see the
   Arguments section's `--yes` semantics). Print the skip note from the
   Arguments section and do not record a durable decline. Do not run the
   prompt below.
1. **Skip if already present or previously declined** — same missing-set rule
   as above.
2. **Prompt once** (recommended default **no**, because — unlike the keyless
   pair — Graphify writes a machine-specific path into this repo's tracked
   `.claude/settings.json`):

   ```
   Also install Graphify for architecture/onboarding-level code intelligence? (y/N)
     - Graphify — repo-level: writes PreToolUse hook entries with this
                  machine's graphify path into the tracked
                  `.claude/settings.json` (relocated to settings.local.json
                  by the #1367 guard) and a `## graphify` section into this
                  repo's CLAUDE.md (guarded against the known over-delete
                  bug — see the Graphify sub-section). Also installs git
                  hooks, which are gitignored.
                  Its AST structural graph builds WITHOUT an API key; indexing
                  docs and images needs a working backend (see below).
   ```

3. **On yes:** run the Graphify sub-section below (install + guarded native
   integration + build the graph — full extraction when a working backend is
   available, `--code-only` fallback otherwise), recording the accept in
   `.claude/init-state.json`.
4. **Full extraction vs. `--code-only` fallback.** Detect a provider key —
   `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `MOONSHOT_API_KEY`,
   `OPENAI_API_KEY` (`GEMINI_API_KEY` and `GOOGLE_API_KEY` both select the
   same backend — `.claude/skills/graphify/SKILL.md`'s own detection checks
   either):
   - **Key present:** run full extraction (`graphify extract .`), first
     verifying/repairing the selected backend's dependency (the Graphify
     sub-section's backend-repair step) so the semantic pass does not fail on
     a missing extra. On success, merge `{"graphify": {"code_only_build":
     false}}` — explicitly `false`, not omitted, so it overrides a `true` left
     by an earlier degraded run. If the semantic pass still fails after the
     AST pass succeeds, re-run `--code-only` to keep the completed AST work,
     report the result as **degraded** — never as a full success — and merge
     `{"graphify": {"code_only_build": true}}` so the next `/project-init` run
     re-offers full extraction instead of treating this graph as done (issue
     #1483; see the "Detect which are already present" rule above).
   - **No key:** run `graphify extract . --code-only` directly and say so
     plainly: `Graphify: no provider key — code-only graph built (docs/images
     not indexed). Set a provider key (e.g. ANTHROPIC_API_KEY) and re-run
     /project-init for the full index.` Merge
     `{"graphify": {"enrichment_skipped_no_key": true, "code_only_build":
     true}}` into `.claude/init-state.json` — the latter is what keeps this
     run from being mistaken for a completed build once a key shows up.
5. **Semantic enrichment (key-gated add-on, on top of a successful full
   extraction).** `graphify label` (community naming) and
   `extract . --mode deep` (inferred edges) are additional passes over an
   already-fully-extracted graph — they do not gate whether docs/images are in
   the graph at all (full extraction in step 4 does). Offer both when a
   provider key is present and full extraction succeeded; both stay non-fatal
   (partial-failure rule) if the key is rejected at build time. Skip entirely
   when step 4 took the `--code-only` path.
6. **On no:** install nothing, record `{"graphify": {"install_declined": true}}`.

The per-tool mechanics below are unchanged; Step 4c only decides *whether* each
runs. Each remains user-scoped/gitignored exactly as before, except Graphify's
documented repo-level native integration — which is written on any Graphify
accept (it does not require a key) — and the `.mcp.json` machine-specific-path
hygiene standing check (#1416, filed under Repowise's sub-section below),
which touches this repo's own `.gitignore`.

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
and runs a **keyless** index (`repowise init . --no-prose -y`, no provider key
requested). There is no `--index-only` flag — `--no-prose` renders the whole
wiki from structure with no model/key, and `-y` skips the cost-confirmation
prompt so an unattended `--yes` run does not block on it. Budget for it: on a
~1600-file repo this took ~5.5 minutes.

The install steps below run only when Step 4c's keyless-group opt-in accepts
and Repowise is in the missing set. **The one exception is the `.mcp.json`
standing check at the end of this sub-section (#1416)**, which runs on every
`/project-init` pass regardless of the group's outcome — accept, decline, or
already-present — the same carve-out the Graphify sub-section's own Standing
check (#1367) makes below.

**Install steps (executed only when the all-or-none group is accepted):**

1. Install: prefer `uv tool install repowise`, else `pipx install repowise`,
   else `python3 -m pip install --user repowise`.
2. Index keyless: run `repowise init . --no-prose -y` so no API key is
   requested; the index lands under `.repowise/` (gitignored). This step
   (or an equivalent `repowise init` invocation) is known to write a
   project-root `.mcp.json` registering the repowise MCP server, with an
   `args` array baking in this machine's absolute filesystem path — the
   **standing check below** (not gated behind this install branch) covers it
   regardless of whether `.mcp.json` existed before this run. It also appends
   a `## Codebase Intelligence for <project> (Repowise)` section to the
   tracked `.claude/CLAUDE.md` — intended, expected behavior (confirmed by
   the repo owner, issue #1670 item 3), not a bug to guard against: the
   section documents the codebase for readers of `CLAUDE.md` and is
   committed along with the rest of this run's changes, not reverted. It is
   derived structurally (`--no-prose`, no model/key involved — see the
   Repowise sub-section above), not free-form model-generated prose — a
   lower-risk profile than fully model-authored text, though it is still
   third-party-tool-generated content landing in an agent-loaded file, so
   the normal PR review before merge is what actually vets it, not this
   note alone.
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

**Standing check — `.mcp.json` machine-specific-path hygiene, runs every pass
(issues #1376, #1416).** Unlike the install steps above, this check is **not**
gated behind the all-or-none group's accept/decline branch or the
"already present" skip — a repo can carry an ungitignored `.mcp.json` from a
Repowise install that predates this guard, and once Repowise shows as
already-present the accept-gated install steps above never re-run (the same
shape issue #1367's Graphify settings.json standing check, below, already
solves for a different pollution class). It is filed under the Repowise
sub-section because that install is the more common source of a project's
`.mcp.json`, but the check itself is repo-wide — it also covers a `.mcp.json`
written by `index-codebase` or a hand-registered MCP server. So run this scan
unconditionally, once per `/project-init` (and therefore `/setup`) run,
idempotently appending the same `.gitignore` marker block `/setup` applies
for its own downstream backstop check, so the two never duplicate an entry
regardless of which one runs first. The marker prefix (everything up to and
including `machine-specific MCP config`) must stay byte-identical between
the two blocks — `grep -qF` matches that prefix only, so the trailing
issue-number suffix may differ, but changing the prefix itself in only one
place breaks idempotency (`tests/skills/test_project_init_mcp_json_hygiene.py`
pins both copies):

```bash
MCP_MARKER="# dev-team hygiene — machine-specific MCP config"
if ! grep -qF "$MCP_MARKER" .gitignore 2>/dev/null; then
  printf '\n%s\n%s\n' \
    "$MCP_MARKER (absolute-path pollution — issues #1376, #1416)" \
    ".mcp.json" >> .gitignore
  echo "mcp-json-gitignore-updated"
else
  echo "mcp-json-gitignore-already-covered"
fi
```

This check is intentionally **not** scoped to the downstream-only, Step 2
`in-repo`-skip case the way `/setup`'s own backstop check is — a
machine-specific path in `.mcp.json` breaks every clone or teammate
regardless of whether the repo is this plugin's own checkout or a downstream
project, so this standing check applies in both. If `.mcp.json` is already
tracked by git (`git ls-files --error-unmatch .mcp.json` exits 0), do not
untrack it automatically — tell the operator to run `git rm --cached
.mcp.json` themselves, same posture as #1376, and record that outcome too.
Merge one of `{"mcp_hygiene": {"gitignore": "added"}}`,
`{"mcp_hygiene": {"gitignore": "already-covered"}}`, or (when the
already-tracked case above fires) `{"mcp_hygiene": {"gitignore":
"added-but-tracked"}}` into `.claude/init-state.json` — a top-level key
rather than nested under `repowise`, since this check runs independently of
Repowise's own install state. Report the outcome as its own line in Step 6's
summary below (and the caller's own report, when `/setup` is the caller).

#### Graphify — native integration, opt-in, with corruption/pollution guards

Graphify (`graphifyy` on PyPI) is a multi-modal knowledge graph tool
(code + docs + schemas + infra + images/video). Unlike CodeGraph it is a
**repo-level native integration** — its installer writes a `/graphify`
skill, PreToolUse nudge hooks into `.claude/settings.json`, and a
`## graphify` section into the project's own `CLAUDE.md`.

This sub-section runs **only after the Graphify opt-in in Step 4c accepts** —
that is, the user said yes. Its integration is repo-level, so none of the file
writes below happen unless that opt-in was accepted; no model/API key is
required to reach or complete this sub-section — the AST build is keyless.
The one exception is the **Standing check** at the end of this sub-section
(#1367), which runs on every `/project-init` pass regardless of the opt-in
outcome — it audits `.claude/settings.json` for pollution left by a past
install, not this run's.

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

**Native integration, with the settings.json absolute-path guard (#1367).**
The same `graphify install --project` call also writes PreToolUse hook
entries into the target repo's shared, git-tracked `.claude/settings.json`,
using the **absolute path to the graphify binary on this machine** (e.g.
`/Users/alice/.local/bin/graphify`, or `uv tool`/`pipx`/`--user pip`
equivalents that resolve differently per machine). If that file is
committed as-is, it bakes one developer's path into the repo and silently
breaks for every other clone/teammate whose graphify binary lives
elsewhere. Immediately after running the installer:

1. **Scan** `.claude/settings.json`'s `hooks.PreToolUse` array for any entry
   whose command invokes graphify via an absolute filesystem path (POSIX or
   Windows) instead of a bare, PATH-resolved `graphify` — that is the known
   pollution, regardless of whether it was just written by this install or
   left over from a previous one. (`scripts/lib/settings_hook_guard.py`
   implements this scan/relocate logic in isolation and is unit-tested at
   `tests/scripts/test_settings_hook_guard.py` — reuse its
   `run_install_with_guard` function, which runs the installer then applies
   the scan, rather than re-deriving the check by hand.)
2. **On detected pollution:** relocate the polluting entry out of
   `.claude/settings.json` into `.claude/settings.local.json` (already
   gitignored, personal-machine scope — the same treatment already given to
   the `.husky/post-commit`/`post-checkout` hooks below). The shared file
   keeps everything else untouched. If the repo is git-tracked, check
   `git log --all -- .claude/settings.json` — if any prior commit already
   carries the polluting path, relocating it fixes the working tree but not
   history; tell the operator the path may still be recoverable from history
   and that scrubbing it (e.g. `git filter-repo`) is their call, not
   something this guard does automatically.
3. **On no pollution detected:** leave the installer's output as-is —
   nothing further to do.

**Standing check — run even when Graphify install is skipped.** The scan
above only fires right after a fresh install; it does nothing for a repo
that was graphify-installed *before* this guard existed (Graphify already
present means it drops out of Step 4c's "missing set" and the installer
never runs — see the idempotency rule above). So run this scan
**unconditionally, once per `/project-init` (and therefore `/setup`) run
whenever `.claude/settings.json` exists** — not gated behind the Graphify
opt-in/install branch:

```python
from pathlib import Path
from settings_hook_guard import fix_settings

fix_settings(Path(".claude/settings.json"), Path(".claude/settings.local.json"))
```

This is what makes `/setup` self-healing for repos that already carry the
baked-in path: no re-install, no opt-in prompt, just a scan-and-relocate.

**Build the graph — full extraction is the target (issue #1224, revised by
#1483).** `graphify extract .` is documented in its own `--help` as headless
full extraction (**AST + semantic LLM**) and is the invocation to run: it is
what indexes this plugin's multi-modal target (code + docs + schemas + infra)
into `graph.json`, the graph the agents actually traverse (`graphify
query`/`path`/`explain`). Whether the semantic pass actually runs is gated on
**backend health, not just key presence** — `extract` dispatches the semantic
pass whenever a backend is configured, and discards the completed AST work if
that pass then fails outright, so a naive `graphify extract .` can silently
produce no `graph.json` at all despite a clean AST run.

- **Idempotent:** if `graphify-out/graph.json` already exists, skip extraction
  and offer the incremental, keyless refresh instead:

  ```bash
  graphify update .
  ```

- **Before extracting, repair the selected backend if a provider key is
  present.** Graphify auto-selects a backend from whichever key it finds
  (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY` — either selects the
  same backend, `MOONSHOT_API_KEY`, `OPENAI_API_KEY`). At least one of these
  backends routes through an OpenAI-compatible client and needs an extra a
  plain `uv tool install graphifyy` does not provide. If the semantic pass
  fails citing a missing package for the selected backend, install the matching
  extra from the **fixed, hardcoded mapping** in `scripts/dev-setup.sh`'s
  `GRAPHIFY_SPEC` selection (keyed off the same detected provider key) —
  never a package/extra name copied out of the failing tool's own error text,
  which is untrusted third-party output, not a safe source for a command to
  run. `ANTHROPIC_API_KEY` and `MOONSHOT_API_KEY` need no extra.

  ```bash
  uv tool install "graphifyy[<extra from dev-setup.sh's GRAPHIFY_SPEC>]" --force   # or the pipx/pip equivalent
  ```

  If the extra install fails, or the failing backend has no entry in that
  mapping, prefer selecting a backend whose deps are already present instead
  — e.g. `graphify extract . --backend claude` when `ANTHROPIC_API_KEY` is
  set, since that backend needs no extra.

- **Run full extraction:**

  ```bash
  graphify extract .
  ```

  This writes `graphify-out/graph.json` (gitignored) plus `GRAPH_REPORT.md`,
  indexing code, docs, schemas, and infra. Without a provider key it
  structurally clusters communities but leaves them unlabeled (`Community N`)
  and skips inferred edges — the structure is intact.
- **If the semantic pass fails after the AST pass already completed:** never
  discard that finished work. Re-run `graphify extract . --code-only` to land
  a graph from what already succeeded, and report the result as **degraded**
  — e.g. `Graphify: semantic pass failed (<reason>) — code-only graph built,
  docs/images not indexed. See error above.` Never report this as a full
  success.
- **`--code-only` is the fallback, never the default when a key is
  present.** Use it directly only when no key is present or no backend can be
  made to work, and say so plainly rather than reporting a successful full
  build:
  `Graphify: no usable backend — code-only graph built, docs/images not
  indexed.`
- **Non-fatal:** if extraction fails outright (the AST pass itself errors),
  print the error, merge `{"graphify": {"build_failed": true}}` into
  `.claude/init-state.json`, and continue — never abort the rest of setup,
  and never claim the group fully installed (the partial-failure rule).
  Agents that consume graphify fall back to `Read`/`Grep`/`Glob` when
  `graphify-out/` is absent (see `knowledge/codegraph-vs-graphify.md`).

**Semantic enrichment (key-gated add-on, on top of a successful full
extraction).** Only when a provider key is present (per Step 4c step 4) and
full extraction above succeeded (not the `--code-only` fallback), further
enrich the graph: `graphify label` names the structural communities, and
`graphify extract . --mode deep` adds INFERRED semantic edges. Both stay
non-fatal — if the key is rejected at build time the existing graph stands
as-is. With no key, or when the graph is `--code-only`, skip this step
entirely.

**Gitignore advice.** `graphify hook install` creates machine-specific
generated git hooks. Tell the user to gitignore them the same way this
repo's own root `.gitignore` does for its own graphify hooks:

```gitignore
graphify-out/
.husky/post-commit
.husky/post-checkout
```

(Or `.git/hooks/post-*` if the target repo does not use husky.)

This covers the generated **git hooks** only. The machine-specific path
`graphify install --project` writes into the *shared* `.claude/settings.json`
itself is handled separately by the settings.json absolute-path guard
above (#1367) — that file is not gitignored, so the fix there is to relocate
the polluting entry, not to gitignore the whole file.

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
- **Graph tools** (Step 4c): the keyless pair — CodeGraph state
  (installed/initialized, MCP registration command printed or skipped) and
  Repowise state, including whether it wrote its `## Codebase Intelligence
  for <project> (Repowise)` section to `.claude/CLAUDE.md` this run (#1670
  item 3) — plus Graphify state: installed with native integration
  applied (and whether the CLAUDE.md corruption guard fired and repaired
  anything) and whether the graph it built was **full extraction** (docs and
  images indexed) or the **`--code-only` fallback** (degraded — no provider
  key or no working backend), **whether semantic enrichment ran or was
  skipped because no provider key was detected or the graph was
  `--code-only`**, or declined. Note CodeGraph is strictly user-level/personal
  and Graphify is the repo-level native integration; only its AST pass is
  keyless — full extraction (docs + images) needs a working backend, and
  semantic enrichment is a further key-gated add-on on top of that.
- **`.mcp.json` machine-specific-path hygiene** (issue #1416, runs
  independently of Repowise's own install/decline state): added the block,
  found it already covered, or flagged that `.mcp.json` is still git-tracked
  and needs `git rm --cached`.
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
web app, dashboard). Wait for confirmation before writing files. **Under
`--yes`, proceed with these defaults without the customization prompt** — the
scaffold only writes into an empty/near-empty directory, so nothing existing
is overwritten.

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
