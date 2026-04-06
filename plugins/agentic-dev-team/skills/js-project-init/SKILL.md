---
name: js-project-init
description: Initialize a new JavaScript project with ES modules, functional style, prettier, eslint, editorconfig, vitest, and gitignore. Use this skill whenever the user wants to start a new JS project, scaffold a Node.js app, create a new package, bootstrap a JavaScript repo, or says things like "init a new project", "set up a JS project", "create a new node app", "start a new frontend project", or "bootstrap a new package". Also trigger when the user asks to add standard JS tooling (linting, formatting, testing) to an empty or near-empty directory.
user-invocable: true
---

# JavaScript Project Initializer

Scaffold a new JavaScript project with opinionated defaults for ES modules, functional development, and modern tooling. The goal is to get from zero to a working, linted, tested project in under a minute — with every config file explained and customizable.

## Why These Defaults

- **ES Modules** — the standard module system for JavaScript. CommonJS (`require`) is legacy; ESM (`import/export`) works everywhere now and enables tree-shaking, static analysis, and better tooling.
- **Functional style** — pure functions, immutable data, no classes. Produces code that's easier to test, reason about, and compose. ESLint rules enforce this by default.
- **Prettier** — removes formatting debates entirely. One config, zero arguments.
- **ESLint flat config** — the modern config format (`eslint.config.js`). Simpler, composable, no more `.eslintrc` cascade confusion.
- **EditorConfig** — ensures consistent whitespace across editors and contributors, regardless of individual editor settings.
- **Vitest** — fast, ESM-native test runner with a Jest-compatible API. No transpilation gymnastics.
- **Playwright** (frontend projects) — reliable cross-browser end-to-end testing.

## Workflow

### Step 1: Present Defaults and Ask for Customization

Before generating any files, present the defaults to the user and ask if they want to change anything. This is important — don't just start writing files.

Present this summary:

```
Here's what I'll set up for your project:

  Package manager:  npm
  Module system:    ES Modules ("type": "module")
  Style:            Functional (no classes, prefer const, no mutation)
  Formatter:        Prettier (2-space indent, single quotes, trailing commas)
  Linter:           ESLint flat config with functional rules
  Editor config:    EditorConfig (2-space indent, UTF-8, LF line endings)
  Testing:          Vitest
  E2E testing:      [Playwright — only if frontend project]
  Git hooks:        Husky pre-push (lint + format check + test)
  .gitignore:       node_modules, dist, coverage, .env, OS files

Want to change anything, or should I go ahead?
```

If the user asks for a frontend project (mentions React, Svelte, Angular, Vue, Next.js, Nuxt, SvelteKit, Astro, a UI, a web app, a dashboard, etc.), include Playwright in the summary. Otherwise omit it but mention it's available.

Note: this skill scaffolds the **base tooling layer** (module system, linting, formatting, testing, editor config). It does not replace framework-specific CLIs (`npx sv create`, `ng new`, `npm create vite@latest`). If the user needs a full framework scaffold, suggest they run the framework CLI first, then use this skill to layer on the opinionated configs.

Wait for the user to confirm or request changes before proceeding.

### Step 2: Initialize the Project

Run these commands to create the foundation:

```bash
npm init -y
```

Then update `package.json` to set ES modules and add scripts. Read the generated `package.json` first, then edit it to add/modify:

- `"type": "module"`
- `"scripts"` section with test, lint, and format commands
- Remove any fields that don't apply (e.g., `"main"` if not a library)

The scripts section should include:

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

For frontend projects, add:

```json
{
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

### Step 3: Install Dependencies

Install all dev dependencies in one command:

```bash
npm install -D eslint prettier vitest @eslint/js eslint-config-prettier husky
```

Note: `eslint-config-prettier` disables ESLint rules that conflict with Prettier. We do NOT install `eslint-plugin-prettier` — the modern practice is to run Prettier as a separate step (`npm run format:check`), not through ESLint. This keeps concerns separated and avoids double-reporting.

For frontend projects, also install Playwright:

```bash
npm install -D @playwright/test
npx playwright install
```

### Step 4: Create Configuration Files

Create each config file using the templates in `references/configs.md`. Read that file for the exact contents. The key files are:

1. **`eslint.config.js`** — flat config with functional rules (no classes, prefer const, no var, no param reassign)
2. **`prettier.config.js`** — 2-space indent, single quotes, trailing commas, 100 char print width
3. **`.editorconfig`** — 2-space indent, UTF-8, LF, trim trailing whitespace, final newline
4. **`.gitignore`** — node_modules, dist, build, coverage, .env, .env.*, OS files (DS_Store, Thumbs.db)
5. **`vitest.config.js`** — minimal config pointing at test files

For frontend projects, also create:
6. **`playwright.config.js`** — basic config with chromium, sensible defaults

### Step 5: Create Starter Files

Create a minimal starter structure so the project is immediately runnable:

```
src/
  index.js          — single exported function with a JSDoc comment
src/
  index.test.js     — one passing vitest test for the starter function
```

The starter function should be a simple pure function (e.g., `greet` or `add`) — just enough to prove the toolchain works. The test should import it and assert the expected output.

For frontend projects, also create:
```
e2e/
  example.spec.js   — one Playwright test placeholder
```

### Step 6: Set Up Git Hooks

Initialize Husky and create the pre-push hook:

```bash
git init  # skip if already a git repo
npx husky init
```

Then create the pre-push hook using the template in `references/configs.md`. The hook runs lint, format check, and tests before every push:

```bash
echo 'npm run lint
npm run format:check
npm test' > .husky/pre-push
```

Remove the default pre-commit hook that Husky creates (we use pre-push instead):

```bash
rm .husky/pre-commit
```

For frontend projects, append the e2e test to the pre-push hook:

```bash
echo 'npm run test:e2e' >> .husky/pre-push
```

This ensures broken code never reaches the remote — lint, formatting, and tests must all pass before `git push` succeeds. The hook runs on push (not commit) to keep the local development loop fast while still gating what goes upstream.

### Step 7: Verify Everything Works

Run the following commands and confirm they succeed:

```bash
npm run lint
npm run format:check
npm test
```

If any command fails, fix the issue before reporting success. Show the user the test output as proof that the scaffold is working.

### Step 8: Summary

After everything passes, give the user a brief summary of what was created:

- List the files created
- Show the available npm scripts
- Mention any next steps (e.g., "run `npm test:watch` to start developing with live tests")

## Customization Handling

If the user requests changes to the defaults in Step 1:

- **Different indent size** — update prettier config, editorconfig, and eslint indent rule
- **Tabs instead of spaces** — update prettier (`useTabs: true`), editorconfig (`indent_style = tab`)
- **Double quotes** — update prettier (`singleQuote: false`)
- **Different print width** — update prettier config
- **Semicolons** — update prettier (`semi: true/false`)
- **Yarn/pnpm** — substitute the package manager in all install commands and update scripts if needed
- **TypeScript** — this skill covers JS only; suggest the user look into a TS-specific scaffold
- **Additional ESLint plugins** — install and add to the flat config array
