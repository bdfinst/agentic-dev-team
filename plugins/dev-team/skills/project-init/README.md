# project-init

A Claude Code skill that gets a repository ready for the dev-team toolchain
in one command: it detects the project's tech stack (JS/TS, Python, C#,
Java), inventories the static-analysis tools the project already has,
confirms a three-column plan, and installs only what's missing — repo-level,
never user-level or global. For greenfield JavaScript it scaffolds a full
project with opinionated defaults for ES modules, functional development,
and modern tooling.

## Usage

In any Claude Code session, say:

```
/project-init
```

Or describe what you need:

- "set up my project's toolchain"
- "install the linters for this repo"
- "get this repo ready for the plugin"
- "init a new project"
- "set up a JS project"
- "create a new node app"
- "start a new frontend project"
- "bootstrap a new package"

The skill always presents its plan and asks for confirmation before writing
or installing anything.

## How it works

1. **Detect the stack** — cheap filesystem signals (`package.json`,
   `pyproject.toml`, `*.csproj`, `pom.xml`, source extensions). Multiple
   stacks set up every matched language; an empty or ambiguous directory
   prompts you to pick a stack (or "something else", which exits without
   writes).
2. **Inventory the toolchain** — per capability slot, find recognized
   providers already present via config files, dependency declarations, and
   executable probes. Existing, configured tools are bound, never replaced.
3. **Confirm a three-column plan** — *found and keeping* / *missing and
   will add* (the only column that installs) / *found but can't
   participate* (reason stated, default offered alongside).
4. **Install repo-level** — per language, into the project itself.
5. **Verify** — run each lane's detection probe and report which provider
   each slot bound, so `/build`'s static self-heal pass finds the tools.

## Per-language installs

| Stack | What lands | Where |
|---|---|---|
| JS/TS | oxlint (existing repo) or the full greenfield scaffold below | `package.json` devDependencies |
| Python | ruff + mypy (+ pytest if no test runner) | `pyproject.toml` dev group or `requirements-dev.txt` |
| C# | nothing — verifies the .NET SDK (honoring `global.json`) and `dotnet format` | — |
| Java | pinned PMD via the plugin's installer script | gitignored `.pmd/` |

The manual commands stay documented in the static-analysis-integration
skill's per-language setup guide
(`${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/references/language-setup.md`);
this skill automates them.

## Greenfield JavaScript scaffold

| Tool | Purpose | Config File |
|---|---|---|
| **ES Modules** | `"type": "module"` in package.json | `package.json` |
| **oxlint** | Fast day-to-day linting (`lint`, `lint:fix`) | `.oxlintrc.json` (optional) |
| **ESLint** | Deep pass (`lint:deep`) — flat config with functional rules (no classes, prefer const, no mutation) | `eslint.config.js` |
| **Prettier** | 2-space indent, single quotes, no semicolons, trailing commas | `prettier.config.js` |
| **EditorConfig** | Consistent whitespace across editors | `.editorconfig` |
| **Vitest** | Fast ESM-native test runner | `vitest.config.js` |
| **Husky** | Pre-commit (lint-staged auto-fix) + pre-push (tests) | `.husky/` |
| **Playwright** | E2E browser testing (frontend projects only) | `playwright.config.js` |

What gets created:

```
your-project/
  package.json              ES module, scripts for test/lint/format
  eslint.config.js          Flat config, functional rules, prettier integration
  prettier.config.js        Opinionated formatting
  vitest.config.js          Test runner config
  .editorconfig             Cross-editor whitespace consistency
  .gitignore                Standard ignores for JS projects
  .husky/
    pre-commit              lint-staged auto-fix of the staged files
    pre-push                Runs the test suite before every push
  src/
    index.js                Starter pure function
    index.test.js           Passing test to prove the toolchain works
```

Frontend projects also get:

```
  playwright.config.js      Browser testing config
  e2e/
    example.spec.js         Placeholder E2E test
```

### npm scripts

| Script | Command | Purpose |
|---|---|---|
| `npm test` | `vitest run` | Run tests once |
| `npm run test:watch` | `vitest` | Run tests in watch mode |
| `npm run test:coverage` | `vitest run --coverage` | Run with coverage report |
| `npm run lint` | `oxlint .` | Fast lint check |
| `npm run lint:fix` | `oxlint --fix .` | Auto-fix lint errors |
| `npm run lint:deep` | `eslint .` | Full ESLint pass (plugin-only rules) |
| `npm run format` | `prettier --write .` | Format all files |
| `npm run format:check` | `prettier --check .` | Check formatting without writing |
| `npm run test:e2e` | `playwright test` | Run E2E tests (frontend only) |

### Git hooks

[Husky](https://typicode.github.io/husky/) runs
[lint-staged](https://github.com/lint-staged/lint-staged) on every commit —
Prettier plus `oxlint --fix` against only the staged files — and the test
suite on every push. After a clone, `npm install` sets the hooks up via the
`prepare` script; `git push --no-verify` bypasses them in an emergency.

### Customization

The scaffold supports these customizations when prompted:

- **Indent size** — updates Prettier, EditorConfig, and ESLint
- **Tabs vs spaces** — updates Prettier and EditorConfig
- **Quote style / semicolons / print width** — updates Prettier
- **Package manager** — npm, yarn, or pnpm
- **Additional ESLint plugins** — added to the flat config array

## Existing projects

On a repo that already has sources, the skill runs in tools-only mode: it
never overwrites existing configs (`eslint.config.js`, `pyproject.toml`
sections, `.editorconfig`, …) and never displaces a bound provider (black +
flake8, biome, a demoted ESLint, checkstyle) with the plugin's default. The
plan's *found and keeping* column reports exactly what was left alone.
