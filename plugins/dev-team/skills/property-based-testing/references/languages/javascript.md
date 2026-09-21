# Property-Based Testing — JavaScript / TypeScript (fast-check)

Tool: [fast-check](https://fast-check.dev/). Detection: `package.json`/`tsconfig.json` present — project-init's own JS/TS stack-detection signal (see [`SKILL.md` → Step 1](../../SKILL.md#step-1-detect-the-target-language-reuse-project-init-never-re-derive); this doc never re-derives it).

This is the JS/TS equivalent of [Step 4.1's Python scaffold](../../scripts/hypothesis_scaffold.py) (`hypothesis` → `fast-check`). Same narrow, explicit heuristic — do not extend without updating this doc:

1. **Round-trip** — the target module exports both a function literally named `encode` and one literally named `decode` (named exports, or both methods on the same exported class/object) and the requested function is one of that pair. Generates a test asserting `decode(encode(x)) === x`.
2. **Invariant** — the target function's JSDoc contains a recognized postcondition phrase (the same phrase list as the Python path — `returns sorted`, `is idempotent`) documented near a type signature (a `@param`/`@returns` JSDoc tag, or a TypeScript type annotation on the function). Generates a test asserting that invariant.
3. **Neither matches** — no file is written; report the exact same "No property derived" message [Step 4.1](../../scripts/hypothesis_scaffold.py) defines (`NO_PROPERTY_MESSAGE`), substituting the target function name — this doc does not define a second copy of that message.

This is deliberately narrow, matching the Python path's own stated scope — not a general contract-inference engine.

## Install / detect

Per [`SKILL.md` → Step 3](../../SKILL.md#step-3-install-the-property-testing-tool-if-missing): `npm install --save-dev fast-check`, mirroring project-init's existing `npm` devDependency install shape for `oxlint`/`@playwright/test` — never a global/user-level install. Confirm it resolved:

```bash
npm ls fast-check
```

## Generation approach

Emit a runnable `<name>.properties.test.js` using `fc.assert(fc.property(...))`, run via this repo's JS test runner convention (`npx vitest run`, per [project-init's own generated `vitest.config.js`](../../../project-init/SKILL.md) — see [`fixtures/js-roundtrip/`](../../fixtures/js-roundtrip/) for a working example project):

```js
import { describe, it } from 'vitest';
import fc from 'fast-check';

import { encode, decode } from './roundtrip.js';

describe('encode/decode round-trip property', () => {
  it('decode(encode(x)) === x for any string', () => {
    fc.assert(fc.property(fc.string(), (x) => decode(encode(x)) === x));
  });
});
```

An invariant test follows the same `fc.assert(fc.property(<arbitrary>, (value) => <assertion>))` shape, with the arbitrary chosen from the target's parameter type the same narrow way Step 4.1's `_STRATEGY_BY_ANNOTATION` map picks a Hypothesis strategy (e.g. a `number[]` parameter → `fc.array(fc.integer())`; no recognized annotation → `fc.string()`).

## Test determinism & the vendoring boundary

`fast-check` (and its own only dependency, `pure-rand`) is **vendored into this fixture's checked-in `node_modules`** rather than installed live during a test run — this repo's deterministic-tooling standard, the same posture `chk_python_ceiling` takes as `exempt`-but-still-treated-as-blocking in [`.github/required-status-checks.json`](../../../../../../.github/required-status-checks.json). Both packages are pure JS with no native/platform-specific binaries (~1.8M total), so the vendored copy is byte-identical on every dev machine and CI runner. See [`fixtures/js-roundtrip/README.md`](../../fixtures/js-roundtrip/README.md) for the exact `git add -f` mechanics (the repo-root `.gitignore`'s blanket `node_modules/` rule otherwise excludes it, and a nested `.gitignore` cannot un-ignore a directory a parent `.gitignore` already excludes).

`vitest` itself is **not** vendored — newer vitest pulls in platform-native binaries (`@rolldown/binding-<platform>`, `lightningcss-<platform>`) that would silently break on a different host OS/arch than whatever built the vendored copy (this repo's CI is `ubuntu-*`, but maintainers develop on macOS). Resolving `vitest` via `npx vitest run` is project-init's own normal live-install path for the project's test runner, unaffected by this skill's own vendoring requirement — that requirement is scoped to `fast-check`, the property library this skill is actually generating tests against.

## Fixture

[`fixtures/js-roundtrip/`](../../fixtures/js-roundtrip/) — a minimal project with `roundtrip.js` (an `encode`/`decode` pair, string reversal) and the fast-check test a scaffold targeting it would generate (`roundtrip.properties.test.js`). Runs green via:

```bash
cd fixtures/js-roundtrip
npm install   # fetches vitest; fast-check/pure-rand are already vendored
npx vitest run
```
