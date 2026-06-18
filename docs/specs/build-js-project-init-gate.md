# Spec: /build — JS project bootstrap gate

## Intent Description

The `/build` skill currently assumes a project is already scaffolded. When a user starts a JS project from scratch and immediately runs `/build` after `/plan`, the build fails or produces broken output because no `package.json`, linting, or test runner exists yet.

This change adds an early gate to `/build`: if the plan targets a JavaScript/Node.js project and no `package.json` exists in the working directory, invoke the `js-project-init` skill before executing any plan steps. This keeps the build skill's "follow the plan exactly" contract intact — the project must be in a working state before TDD steps begin.

## Architecture Specification

**Component affected**: `plugins/dev-team/skills/build/SKILL.md`

**New gate location**: After Step 1 (Find the plan), before Step 2 (Verify plan status).

**Detection logic** (new Step 1.5):

- Check whether `package.json` exists in the working directory.
- Check whether the plan file contains JS/TS signals: file extensions `.js`, `.mjs`, `.ts`, `.jsx`, `.tsx` or keywords `node`, `npm`, `vitest`, `jest`, `eslint` in file paths or commands.
- If `package.json` is absent **and** the plan is JS-flavored → print one-line notice and invoke `js-project-init`.
- If `package.json` exists → skip silently.
- If the plan contains no JS signals → skip silently.

**User communication**: Before invoking: `"No package.json found. Running js-project-init to bootstrap the project first."`

**Constraints**:

- Must not block non-JS plans.
- Must not invoke `js-project-init` if `package.json` already exists, even if minimal.
- The gate does not replace Step 2 (plan status) or Step 3 (acceptance criteria) — it runs before them.
- This is detection + delegation only; no reimplementation of `js-project-init` logic.
- If `js-project-init` fails, `/build` halts immediately.

## Acceptance Criteria

1. When `/build` is invoked on a JS-flavored plan with no `package.json`, the skill invokes `js-project-init` before any plan step runs.
2. When `/build` is invoked on a JS-flavored plan with an existing `package.json`, the gate is skipped with no output.
3. When `/build` is invoked on a non-JS plan with no `package.json`, the gate is skipped silently.
4. The user sees exactly one line of output before `js-project-init` is invoked.
5. If `js-project-init` fails, `/build` halts and reports the failure without proceeding to implementation.
6. The gate is documented as Step 1.5 within the SKILL.md.

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Verdict: PASS**
