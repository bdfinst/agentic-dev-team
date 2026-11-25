---
name: esm-enforcer
description: ES Modules enforcement — import/export only, no require/module.exports, no __dirname/__filename
tools: Read, Grep, Glob
effort: low
---

# ESM Enforcer

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=ESM compliant, warn=minor CJS remnants, fail=CJS patterns in new code
Severity: error=require() or module.exports in source, warning=__dirname/__filename usage, suggestion=dynamic import opportunity
Confidence: high=mechanical (replace require with import); medium=judgment call (dynamic require); none=third-party constraint

Context needs: diff-only
File scope: `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs`

## Activates when

Any JS/TS project detected. Always-on for JavaScript and TypeScript projects.

## Skip

Return skip when no JS/TS files in the changeset, or when files are in `node_modules/`.

## Detect

Lint pointers: a bullet that says "If `eslint.devteam.config.js` enables ..." applies only when the config is wired: the project's own ESLint config imports it, or `.claude/settings*.json` sets `DEVTEAM_POST_LINT`. Otherwise judge the bullet fully.

CJS patterns in source code:

- `require()` calls (except in `.cjs` config files like `jest.config.cjs`). If `eslint.devteam.config.js` enables `no-restricted-syntax` and it is wired, judge only files the config does not lint; otherwise judge fully. [MECHANICAL] rule: no-restricted-syntax
- `module.exports` or `exports.` assignments. If `eslint.devteam.config.js` enables `no-restricted-syntax` and it is wired, judge only files the config does not lint, and forms such as `Object.assign(module.exports, ...)`; otherwise judge fully. [MECHANICAL] rule: no-restricted-syntax
- `__dirname` or `__filename` (use `import.meta.dirname` / `import.meta.filename` or `fileURLToPath(import.meta.url)`). If `eslint.devteam.config.js` enables `no-restricted-globals` and it is wired, judge only files the config does not lint; otherwise judge fully. [MECHANICAL] rule: no-restricted-globals

Package.json:

- Missing `"type": "module"` (warn on first detection, do not repeat) [MECHANICAL] no rule: package.json manifest field check

File extensions:

- `.js` files that should be `.mjs` in a non-ESM package (or add `"type": "module"`) [MECHANICAL] no rule: file extension against package type

## Ignore

- `.cjs` files (legitimate CJS config files)
- Files in `node_modules/`
- Generated files
- Test configuration files that require CJS for tooling compatibility
