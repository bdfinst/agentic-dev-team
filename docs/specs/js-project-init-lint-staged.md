# Spec: js-project-init — lint-staged integration

## Intent Description

Currently `js-project-init` installs Husky with a **pre-push** hook that runs `lint`, `format:check`, and `test` in sequence. This means formatting and lint violations are only caught at push time, not at commit time — developers accumulate noise that must be cleaned up manually before pushing.

This change adds `lint-staged` to the scaffolded project so that **pre-commit**, only the files currently staged get auto-fixed by `prettier --write` and `eslint --fix`. The pre-push hook retains `npm test`. The redundant `npm run format:check` is removed from pre-push because lint-staged already fixes staged files on commit. Pre-push becomes: `npm test` only (plus `test:e2e` for frontend projects).

## Architecture Specification

**Component affected**: `plugins/dev-team/skills/js-project-init/SKILL.md`

**Changes required:**

- **Step 3** (Install dependencies): add `lint-staged` to the `npm install -D` command
- **Step 2** (package.json): add `"lint-staged"` key to `package.json` with per-extension command map:

```json
"lint-staged": {
  "*.{js,mjs,cjs}": ["prettier --write", "eslint --fix"],
  "*.{json,md,yaml,yml}": ["prettier --write"]
}
```

- **Step 6** (Git hooks): replace single pre-push with two hooks:
  - `pre-commit` → `npx lint-staged`
  - `pre-push` → `npm test` only (frontend: `npm test && npm run test:e2e`)
  - Remove `npm run format:check` and `npm run lint` from pre-push

- **Step 8** (Summary): list both hooks so the user understands what fires when

**Dependencies**: `lint-staged` is standalone; no new transitive dependencies.

**Constraints**:

- Must not remove pre-push `npm test` — auto-fix does not replace correctness testing
- Must not run full `npm run lint` on pre-commit (defeats the staged-files optimization)
- The existing `"lint"` and `"format:check"` scripts in `package.json` remain for manual/CI use

## Acceptance Criteria

1. After `js-project-init` runs, `package.json` contains a `"lint-staged"` key with per-extension fix commands: `.js/.mjs/.cjs` → prettier + eslint; `.json/.md/.yaml/.yml` → prettier only.
2. A `.husky/pre-commit` hook exists and contains `npx lint-staged`.
3. The `.husky/pre-push` hook contains `npm test` and does **not** contain `npm run format:check` or `npm run lint`.
4. `lint-staged` is present in `devDependencies` in `package.json`.
5. The Step 7 verify sequence (`npm run lint`, `npm run format:check`, `npm test`) still passes after scaffolding.
6. Frontend projects retain `npm run test:e2e` in the pre-push hook.
7. The Step 8 summary lists both the pre-commit hook (lint-staged auto-fix) and the pre-push hook (test only).

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Verdict: PASS**
