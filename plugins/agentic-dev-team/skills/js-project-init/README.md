# js-project-init

A Claude Code skill that scaffolds JavaScript projects with opinionated defaults for ES modules, functional development, and modern tooling.

## What It Sets Up

| Tool | Purpose | Config File |
|---|---|---|
| **ES Modules** | `"type": "module"` in package.json | `package.json` |
| **ESLint** | Flat config with functional rules (no classes, prefer const, no mutation) | `eslint.config.js` |
| **Prettier** | 2-space indent, single quotes, no semicolons, trailing commas | `prettier.config.js` |
| **EditorConfig** | Consistent whitespace across editors | `.editorconfig` |
| **Vitest** | Fast ESM-native test runner | `vitest.config.js` |
| **Husky** | Pre-push git hook (lint + format check + tests) | `.husky/pre-push` |
| **Playwright** | E2E browser testing (frontend projects only) | `playwright.config.js` |

## Usage

In any Claude Code session, say:

```
/js-project-init
```

Or describe what you need:

- "init a new project"
- "set up a JS project"
- "create a new node app"
- "start a new frontend project"
- "bootstrap a new package"

The skill will present its defaults and ask for confirmation before generating any files.

## What Gets Created

```
your-project/
  package.json              ES module, scripts for test/lint/format
  eslint.config.js          Flat config, functional rules, prettier integration
  prettier.config.js        Opinionated formatting
  vitest.config.js          Test runner config
  .editorconfig             Cross-editor whitespace consistency
  .gitignore                Standard ignores for JS projects
  .husky/
    pre-push                Runs lint + format:check + test before every push
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

## npm Scripts

| Script | Command | Purpose |
|---|---|---|
| `npm test` | `vitest run` | Run tests once |
| `npm run test:watch` | `vitest` | Run tests in watch mode |
| `npm run test:coverage` | `vitest run --coverage` | Run with coverage report |
| `npm run lint` | `eslint .` | Check for lint errors |
| `npm run lint:fix` | `eslint . --fix` | Auto-fix lint errors |
| `npm run format` | `prettier --write .` | Format all files |
| `npm run format:check` | `prettier --check .` | Check formatting without writing |
| `npm run test:e2e` | `playwright test` | Run E2E tests (frontend only) |

## Git Hooks (Pre-Push)

The project uses [Husky](https://typicode.github.io/husky/) to run quality checks before every `git push`:

1. `npm run lint` -- ESLint must pass
2. `npm run format:check` -- Prettier formatting must be correct
3. `npm test` -- All tests must pass

If any step fails, the push is blocked. This keeps the remote branch clean without slowing down local commits.

### Setup After Clone

When a collaborator clones the repo, they just need:

```bash
npm install
```

The `prepare` script in package.json automatically runs `husky` during install, which sets up the git hooks. No manual hook configuration needed.

### Bypassing Hooks (Emergency)

If you need to push without running hooks (use sparingly):

```bash
git push --no-verify
```

## Customization

The skill supports these customizations when prompted:

- **Indent size** -- updates Prettier, EditorConfig, and ESLint
- **Tabs vs spaces** -- updates Prettier and EditorConfig
- **Quote style** -- updates Prettier
- **Semicolons** -- updates Prettier
- **Print width** -- updates Prettier
- **Package manager** -- npm, yarn, or pnpm
- **Additional ESLint plugins** -- added to flat config array

TypeScript projects are not covered by this skill -- use a TS-specific scaffold instead.

## ESLint Rules

The functional style rules enforce:

- **No classes** -- use functions and closures instead
- **No `this`** -- use closures and explicit parameters
- **`prefer-const`** -- immutable by default
- **`no-var`** -- use `const` or `let`
- **`no-param-reassign`** -- don't mutate function parameters
- **`eqeqeq`** -- always use `===`
- **`no-console`** -- warning (not error) to catch leftover debug logs

## Why Pre-Push Instead of Pre-Commit?

Pre-commit hooks run on every commit, which can slow down the "save and commit" flow during active development. Pre-push hooks run less frequently (only when pushing to remote) while still gating what reaches shared branches. This keeps the local dev loop fast.

If you prefer pre-commit hooks, move `.husky/pre-push` to `.husky/pre-commit`.
