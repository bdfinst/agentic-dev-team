---
name: project-init
description: Get a repository ready for the dev-team toolchain in one command — detect the tech stack (JS/TS, Python, C#, Java), inventory the static-analysis tools the project already has, confirm a plan, and install only what's missing, repo-level. For JavaScript it scaffolds a new project with ES modules, functional style, prettier, oxlint, editorconfig, vitest, and gitignore. Use this skill whenever the user wants to start a new JS project, scaffold a Node.js app, create a new package, bootstrap a JavaScript repo, or says things like "init a new project", "set up a JS project", "create a new node app", "start a new frontend project", or "bootstrap a new package". Also trigger when the user says "set up my project's toolchain", "install the linters for this repo", "get this repo ready for the plugin", or asks to add standard tooling (linting, formatting, testing) to a new or existing project in any supported language.
role: worker
user-invocable: true
---

# Project Initializer

One command to get a repository ready for the dev-team toolchain, whatever
the stack. Detect the project's language(s), inventory the static-analysis
tools already present, confirm a three-column plan, then install only the
missing tools — always repo-level, never user-level or global.

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

### Step 6: Summary

After every configured lane probes green, give the user:

- Per lane, per slot: the bound provider — kept (column 1) or newly
  installed (column 2).
- Configs and tools found and left alone (columns 1 and 3 double as this
  report).
- Any **found but can't participate** entry, with its reason and the
  default offered alongside.
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
