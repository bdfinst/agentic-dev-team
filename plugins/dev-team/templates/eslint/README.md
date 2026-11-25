# Dev-team ESLint template

Lint rules for checks that the `esm-enforcer` and `js-fp-review` agents otherwise decide by reading code.

## Layout

- `payload/` is the only tree that is scaffolded into user projects. It holds `eslint.devteam.config.js`.
- `rule-ids.json` is read at runtime by the plugin's own scripts and by `/agent-audit`. It is not scaffolded.
- `dev/` holds fixtures, tests, the comparison corpus, and measurements. It is never scaffolded.

## Use

Import the array from your own flat config. ESLint 9 and 10 are supported.

```js
import devteam from "./eslint.devteam.config.js";
export default [...devteam, ...yourConfig];
```

Put the dev-team config first. In a flat config, a later entry overrides an earlier one for the same file and rule, so options in `yourConfig` (for example `no-plusplus` without `allowForLoopAfterthoughts`) replace the dev-team options. With the order reversed, the dev-team options replace yours.

Every rule is `warn`, so a plain `eslint` run exits 0 on a finding. The config does not set a parser. For TypeScript, your own config supplies one.

To turn these findings into feedback after each edit, enable the opt-in [post-edit lint hook](../../docs/post-edit-lint-hook.md). Read its Security section first.

A rule that is not imported does nothing. The agents treat the config as *wired* only when your ESLint config imports it or `.claude/settings*.json` sets `DEVTEAM_POST_LINT`.

"Wired" assumes ESLint warnings are actually produced for the files under review. The config only warns, so a missing or skipped lint run looks the same as a clean one. When a bullet is narrowed because the config is wired and the lint run did not happen, nothing judges the cases the rule would have caught.

## Rule-to-bullet table

| Rule | Agent bullet | Verdict on the corpus |
| --- | --- | --- |
| `no-var` | `js-fp-review`: `var` | not convertible: the rule flags the `mut` prefix the agent exempts |
| `prefer-const` | `js-fp-review`: `let` never reassigned | not convertible: the rule flags `mut`, `mutable`, and `_` names the agent exempts |
| `no-plusplus` (loop afterthoughts allowed) | `js-fp-review`: `++`/`--` outside loop counters | not convertible: the rule flags a `while` loop counter the agent exempts |
| `no-param-reassign` (`props: true`) | `js-fp-review`: `param.prop = value`, `param[key] = value`, `delete param.prop`, functions modifying parameters | convertible |
| `no-restricted-globals` | `esm-enforcer`: `__dirname`, `__filename` | not convertible: no agent evidence |
| `no-restricted-syntax` | `esm-enforcer`: `require()` calls, `module.exports` and `exports.` assignments | not convertible: no agent evidence |

`functional/immutable-data` (typed mode only, see below) is enabled and maps to the `js-fp-review` array-mutator bullets. It is not convertible: no agent evidence has been collected for it, so those bullets keep full agent coverage.

Every other Detect bullet is `no rule`. The ids `max-depth` and `no-magic-numbers` are `planned`: bullets may map to them, but no shipped rule enables them yet.

## Array mutation (typed mode)

`functional/immutable-data` needs type information to tell an array from a `Set` or a class with its own `push`. It runs only on files your own `tsconfig.json` covers. The config reads that file; it never creates or edits one.

Requirements:

- `tsconfig.json` in the same directory as `eslint.devteam.config.js`. Its `include`, `files`, `exclude`, and `extends` decide which files are covered. A solution-style tsconfig that only lists `references` covers no files, so typed rules do not run.
- `eslint.devteam.config.js` beside your own `eslint.config.*` and `tsconfig.json`, with ESLint run from that directory. The config lists covered files as paths relative to its own directory, and ESLint resolves those against the directory it runs from. From any other directory (a monorepo root, an editor that starts ESLint elsewhere) no path matches, and the typed rules do not run, with no notice.
- `allowJs` or `checkJs` (which implies `allowJs`) in that tsconfig to cover JavaScript with JSDoc types. Without it, JavaScript files are not covered and are linted untyped, with no notice.
- `eslint-plugin-functional`, `@typescript-eslint/parser`, and `typescript` installed in your project. Tested with `eslint-plugin-functional` 10.0.1 (ESLint 9 and 10), `@typescript-eslint/parser` 8.60.1, `typescript` 5.9.3.

When a dependency is missing, the typed rules are skipped and one line goes to stderr (`devteam-lint: typed rules skipped, not installed: ...`). stdout stays clean for `--format json`. Set `DEVTEAM_LINT_TYPED=0` to skip the typed rules with no notice. Both cases leave every other rule running.

The config registers the plugin as `functional`. Your own config may register the same plugin object under that name. A different plugin object registered as `functional` for the same files fails with a redefinition error.

What is a finding (`warn`): `push`, `pop`, `shift`, `unshift`, `splice`, `sort`, `reverse`, and `fill` on an array that is a parameter, a captured outer variable, a module-level variable, or a local accumulator (`const out = []; out.push(x)`).

What is not: `this.*` (the config ignores the pattern `this.**` in every function, not only class methods, because the rule has no option that limits it to classes without also ignoring local accumulators in class methods), copies (`[...a].sort()`, `a.slice().reverse()`), `toSorted`, `toSpliced`, `toReversed`, a `Set` or `Map`, and a custom class with its own `push` or `sort`. The rule also reports property writes, `delete`, and `Object.assign`; a processor in the config drops those messages, so the rule id reports array mutators only.

## Untyped JavaScript limits

JavaScript that no `tsconfig.json` covers gets no array-mutation rule. Without types, a rule cannot tell `xs.push(1)` on an array from `push` on a `Set`-like object or a class with its own `push`, so the config reports nothing rather than guess. That keeps false positives at zero and accepts these false negatives. Each is committed as a case in `dev/fixtures/array-mutation/untyped/expected-misses.json`:

- `parameter`: a mutator called on a parameter (`xs.push(1)`).
- `captured`: a mutator called on an array captured from an enclosing scope.
- `module-level`: a mutator called on a module-level array.
- `accumulator`: a mutator called on a local accumulator (`const out = []; out.push(x)`).

To close these gaps, cover the file with a `tsconfig.json` that sets `allowJs` and add JSDoc types.

Future work, not built: a `no-restricted-syntax` selector for mutator calls on parameters, and a small custom rule that tracks `const x = []` bindings. Either would give untyped JavaScript coverage at the cost of more false positives than typed mode.

## Known limits

- The `no-restricted-syntax` selectors are scope-blind. A call to a local binding named `require` is flagged, for example `const require = createRequire(import.meta.url); require("./data.json")`. A local named `module` or `exports` that is assigned to is flagged the same way.
- `.cjs` and `.cts` files are exempt from the ESM rules, matching the agent's `jest.config.cjs` exception.
- `no-param-reassign` does not see a write through an alias of the parameter.
- The typed rule lists every covered file as a glob when the config loads. A very large tsconfig pays for that on each lint run.
- The processor that filters the typed rule's messages occupies the processor slot for the covered files. A config that attaches its own processor to the same files conflicts with it.
- The same processor drops every `functional/immutable-data` message that is not an array message, including those from your own setting of that rule, on covered files. Property writes, `delete`, and `Object.assign` reported by your own `functional/immutable-data` entry do not appear there.

## Converted bullets

A bullet is converted to a pointer only when its rule is listed in `convertible` in `rule-ids.json`. The pointer keeps the original bullet and adds: "If `eslint.devteam.config.js` enables `<id>` and it is wired, judge only `<residual>`; otherwise judge fully."

`rule-ids.json` holds four lists:

- `enabled`: the rule ids the config enables. A Node test fails when it drifts from the config. The Node tests run manually (`cd dev && npm ci && node --test`); a CI gate for them is planned and not yet in place.
- `planned`: valid `rule:` targets that no shipped rule enables yet. Never valid for a pointer.
- `convertible`: the rules `lint_corpus_compare.py` reports as convertible on `dev/corpus/`. A Python test fails when it drifts from the comparison.
- `conditional`: enabled rules that run only when extra dependencies are installed (`functional/immutable-data`). A Node test fails when it drifts from the typed block of the config.

`scripts/check_detect_tags.py` reads this file. It rejects an unknown rule id, any pointer whose rule is not convertible, and any pointer whose rule is conditional. A `rule:` mapping to a conditional rule is accepted.

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

After a change, update `convertible` in `rule-ids.json` to match the comparison. Measurements are in `dev/MEASUREMENTS.md`.
