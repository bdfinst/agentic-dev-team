# Dev-team ESLint template

Lint rules for checks that the `esm-enforcer` and `js-fp-review` agents otherwise decide by reading code.

## Layout

- `payload/` is the only tree that is scaffolded into user projects. It holds `eslint.devteam.config.js`.
- `dev/` holds fixtures, tests, the comparison corpus, and measurements. It is never scaffolded.

## Use

Import the array from your own flat config. ESLint 9 and 10 are supported.

```js
import devteam from "./eslint.devteam.config.js";
export default [...yourConfig, ...devteam];
```

Every rule is `warn`, so a plain `eslint` run exits 0 on a finding. The config does not set a parser. For TypeScript, your own config supplies one.

A rule that is not imported does nothing. The agents treat the config as *wired* only when your ESLint config imports it or `.claude/settings*.json` sets `DEVTEAM_POST_LINT`.

## Rule-to-bullet table

| Rule | Agent bullet | Verdict on the corpus |
| --- | --- | --- |
| `no-var` | `js-fp-review`: `var` | convertible |
| `prefer-const` | `js-fp-review`: `let` never reassigned | not convertible: the rule flags `mut`, `mutable`, and `_` names the agent exempts |
| `no-plusplus` (loop afterthoughts allowed) | `js-fp-review`: `++`/`--` outside loop counters | convertible |
| `no-param-reassign` (`props: true`) | `js-fp-review`: `param.prop = value`, `param[key] = value`, functions modifying parameters | convertible |
| `no-restricted-globals` | `esm-enforcer`: `__dirname`, `__filename` | convertible |
| `no-restricted-syntax` | `esm-enforcer`: `require()` calls, `module.exports` and `exports.` assignments | convertible |

Every other Detect bullet is `no rule`. The ids `functional/immutable-data`, `max-depth`, and `no-magic-numbers` are `planned`: bullets may map to them, but no shipped rule enables them yet.

## Known limits

- A `require()` call through a local binding named `require` (for example `createRequire`) is flagged. A selector cannot see scope.
- `.cjs` and `.cts` files are exempt from the ESM rules, matching the agent's `jest.config.cjs` exception.
- `no-param-reassign` does not see a write through an alias of the parameter.

## Converted bullets

A bullet is converted to a pointer only when its rule is listed in `convertible` in `dev/rule-ids.json`. The pointer keeps the original bullet and adds: "If `eslint.devteam.config.js` enables `<id>` and it is wired, judge only `<residual>`; otherwise judge fully."

`dev/rule-ids.json` holds three lists:

- `enabled`: the rule ids the config enables. A Node test fails when it drifts from the config.
- `planned`: valid `rule:` targets that no shipped rule enables yet. Never valid for a pointer.
- `convertible`: the rules `lint_corpus_compare.py` reports as convertible on `dev/corpus/`. A Python test fails when it drifts from the comparison.

`scripts/check_detect_tags.py` reads this file. It rejects an unknown rule id and any pointer whose rule is not convertible.

## Develop

```bash
cd plugins/dev-team/templates/eslint/dev
npm ci
node --test "tests/**/*.test.js"                     # ESLint from this dir (9.x)
DEVTEAM_ESLINT_ROOT=/path/with/eslint10 node --test "tests/**/*.test.js"
node lib/corpus.js > corpus/rule-found.json          # refresh after a config change
python3 ../../../scripts/lint_corpus_compare.py \
  --agent-found corpus/agent-found.json --rule-found corpus/rule-found.json \
  --format text
```

After a change, update `convertible` in `dev/rule-ids.json` to match the comparison. Measurements are in `dev/MEASUREMENTS.md`.
