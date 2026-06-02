---
name: js-project-init
description: Initialize a new JavaScript project with ES modules, functional style, prettier, eslint, editorconfig, vitest, and gitignore. Use this skill whenever the user wants to start a new JS project, scaffold a Node.js app, create a new package, bootstrap a JavaScript repo, or says things like "init a new project", "set up a JS project", "create a new node app", "start a new frontend project", or "bootstrap a new package". Also trigger when the user asks to add standard JS tooling (linting, formatting, testing) to an empty or near-empty directory.
user-invocable: true
---

# JavaScript Project Initializer

Scaffold a new JavaScript project with opinionated defaults for ES modules, functional development, and modern tooling. Goal: zero to working/linted/tested in under a minute, with every config file explained and customizable.

Defaults:
- **Package manager**: npm
- **Module system**: ES Modules (`"type": "module"`)
- **Style**: functional — no classes, prefer `const`, no mutation
- **Formatter**: Prettier (2-space indent, single quotes, trailing commas, 100-char width)
- **Linter**: ESLint flat config with functional rules
- **Editor**: EditorConfig (2-space, UTF-8, LF, trim trailing whitespace, final newline)
- **Tests**: Vitest
- **E2E** (frontend only): Playwright
- **Git hooks**: Husky pre-push (lint + format check + test)
- **`.gitignore`**: node_modules, dist, build, coverage, .env, .env.*, OS files

This skill scaffolds the **base tooling layer**. It does not replace framework-specific CLIs (`npx sv create`, `ng new`, `npm create vite@latest`). For a full framework scaffold, run the framework CLI first, then layer on these configs.

## Workflow

### Step 1: Present defaults and confirm

Present the defaults above to the user and ask: "Want to change anything, or should I go ahead?" Include Playwright in the summary only if the user mentions a frontend project (React, Svelte, Angular, Vue, Next.js, Nuxt, SvelteKit, Astro, UI, web app, dashboard). Wait for confirmation before writing files.

### Step 2: Initialize package.json

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
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "prepare": "husky"
  }
}
```

Frontend projects also add: `"test:e2e": "playwright test"`.

### Step 3: Install dependencies

```bash
npm install -D eslint prettier vitest @eslint/js eslint-config-prettier husky
```

`eslint-config-prettier` disables ESLint rules that conflict with Prettier. Do NOT install `eslint-plugin-prettier` — run Prettier as a separate step (`npm run format:check`), not through ESLint.

Frontend projects also:

```bash
npm install -D @playwright/test
npx playwright install
```

### Step 4: Create config files

Templates: `references/configs.md`. Required files:

1. `eslint.config.js` — flat config with functional rules (no classes, prefer const, no var, no param reassign)
2. `prettier.config.js` — 2-space, single quotes, trailing commas, 100-char width
3. `.editorconfig` — 2-space, UTF-8, LF, trim trailing whitespace, final newline
4. `.gitignore` — node_modules, dist, build, coverage, .env, .env.*, OS files (DS_Store, Thumbs.db)
5. `vitest.config.js` — minimal config pointing at test files
6. (frontend) `playwright.config.js` — chromium, sensible defaults

### Step 5: Create starter files

```
src/index.js        — single exported pure function with JSDoc (e.g., greet or add)
src/index.test.js   — one passing vitest test for the starter function
```

Frontend projects also create `e2e/example.spec.js` — one Playwright placeholder.

### Step 6: Git hooks

```bash
git init  # skip if already a git repo
npx husky init
```

Create the pre-push hook (template in `references/configs.md`):

```bash
echo 'npm run lint
npm run format:check
npm test' > .husky/pre-push
```

Remove Husky's default pre-commit hook (we use pre-push instead):

```bash
rm .husky/pre-commit
```

Frontend projects append e2e:

```bash
echo 'npm run test:e2e' >> .husky/pre-push
```

Pre-push gates what goes upstream while keeping the local commit loop fast.

### Step 7: Verify

```bash
npm run lint
npm run format:check
npm test
```

If any command fails, fix it before reporting success. Show the user the test output.

### Step 8: Summary

After everything passes, give the user:
- List of files created
- Available npm scripts
- One-line next-step suggestion (e.g., `npm run test:watch` to develop with live tests)

## Customization handling

If the user changes Step 1 defaults:

| Request | Update |
|---|---|
| Different indent size | prettier config, editorconfig, eslint indent rule |
| Tabs instead of spaces | prettier (`useTabs: true`), editorconfig (`indent_style = tab`) |
| Double quotes | prettier (`singleQuote: false`) |
| Different print width | prettier config |
| Semicolons | prettier (`semi: true/false`) |
| Yarn / pnpm | substitute the package manager in all install commands; adjust scripts if needed |
| TypeScript | This skill is JS-only — suggest a TS-specific scaffold |
| Additional ESLint plugins | install and add to the flat config array |
