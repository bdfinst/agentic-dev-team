# Measurements: pilot ESLint config vs the agents

Recorded 2026-11-25. Informational, except that the comparison decides which bullets are converted. The verdicts are provisional: see "Evidence limits".

## Method

- **Agent found** is not a live `/agent-eval` run. It is `corpus/agent-found.json`:
  - For `evals/fixtures/fp-*.ts`, the cases the fixtures plant (their `// mutation:` and `should be const` comments). The committed `evals/expected/fp-*.json` carry only issue-count ranges, so a Node test checks each fixture's planted count against that range.
  - For `corpus/fp-detect-text.ts`, cases written from `js-fp-review`'s Detect text. Agreement on positive cases there holds by construction. The file's value is its exception cases, where the agent reports nothing and a rule that reports is a false positive.
  - There is no `esm-enforcer` eval fixture, so the esm rules have no agent cases at all.
- **Rule found** is `corpus/rule-found.json`, produced by `node lib/corpus.js` with the TypeScript parser from `@typescript-eslint/parser` for `.ts` files.
- A **false positive** is a rule finding on a line where the agent reported nothing. `convertible` also needs at least one agent case as evidence.
- `convertible` in `rule-ids.json` is the output of `lint_corpus_compare.py` on these two files. A Python test fails when they differ.

## Comparison on the full corpus

| Rule | Agent found | Rule found | False positives | Residual | Convertible |
| --- | --- | --- | --- | --- | --- |
| `no-param-reassign` | 6 | 6 | 0 | 0 | yes |
| `no-plusplus` | 3 | 4 | 1 | 0 | no |
| `no-var` | 1 | 2 | 1 | 0 | no |
| `prefer-const` | 3 | 5 | 2 | 0 | no |
| `no-restricted-globals` | 0 | 0 | 0 | 0 | no (no evidence) |
| `no-restricted-syntax` | 0 | 0 | 0 | 0 | no (no evidence) |

False positives, all in `corpus/fp-detect-text.ts`:

- `no-plusplus`: line 38, `spin++` in a `while` body. The agent treats a loop counter as exempt; the rule allows only `for` afterthoughts.
- `no-var`: line 35, `var mutLegacy`. The agent exempts the `mut` prefix; the rule does not.
- `prefer-const`: lines 5 and 6, `let mutScratch` and `let _cache`, the same prefix exemption.

## Comparison on the eval fixtures alone

| Rule | Agent found | Rule found | False positives | Convertible |
| --- | --- | --- | --- | --- |
| `no-param-reassign` | 5 | 5 | 0 | yes |
| `no-plusplus` | 2 | 2 | 0 | yes |
| `prefer-const` | 2 | 2 | 0 | yes |
| `no-restricted-globals`, `no-restricted-syntax`, `no-var` | 0 | 0 | 0 | no (no evidence) |

The eval fixtures alone would also pass `no-plusplus` and `prefer-const`. Their documented exceptions are not exercised there, so the corpus adds them.

The `delete profile.legacyField` case (`evals/fixtures/fp-object-mutations.ts` line 35) is one of the five `no-param-reassign` cases above: with `props: true` the rule reports it.

All other corpus files produced zero findings, including the clean fixtures and `jest.config.cjs`.

## Evidence limits

- The agent-found baseline is derived from planted cases and Detect text. It is not a live agent run, so every verdict above is provisional until a live `/agent-eval` run confirms it.
- `no-var`, `no-plusplus`, `no-restricted-globals`, and `no-restricted-syntax` are non-convertible pending independent agent evidence. The esm rules have none; `no-var` has only a self-written case; `no-plusplus` passes on the eval fixtures but has a false positive the corpus now tests.
- Known false positives the corpus does not test: a local `require` from `createRequire` is flagged by `no-restricted-syntax`.

## Gate

One rule is convertible, so the batch continues with it. Four bullets are converted, all in `js-fp-review` and all to `no-param-reassign`: `param.prop = value`, `param[key] = value`, `delete param.prop`, and "functions modifying parameters". No `esm-enforcer` bullet is converted.

## ESLint versions

| ESLint | Where it resolved | `node --test` | Corpus output vs committed |
| --- | --- | --- | --- |
| 9.39.4 | `dev/node_modules` (pinned in `dev/package.json`) | 28 pass, 1 skipped | identical |
| 10.15.0 | scratch install, selected with `DEVTEAM_ESLINT_ROOT` | 28 pass, 1 skipped | identical |

The skipped test is the mis-cased import, which needs a case-sensitive file system; it passes on a case-sensitive APFS volume. Typed linting used `eslint-plugin-functional` 10.0.1, `@typescript-eslint/parser` 8.60.1, and `typescript` 5.9.3 in both runs.

## Tokens (informational)

`scripts/measure_tokens.py`, byte-count heuristic (`tiktoken` was not installed):

| File | Before the pilot | After |
| --- | --- | --- |
| `templates/agents/esm-enforcer.md` | 476 | 476 |
| `agents/js-fp-review.md` | 2158 | 2393 |
| Total | 2634 | 2869 |

Conversion adds tokens. "Otherwise judge fully" keeps each original bullet, and the file gains one note defining "wired". Any saving comes from the agent judging less, not from a shorter prompt. Cost figures wait on the cost-meter fix.

## Agent pass criterion

Every case the agent found before is still found by agent-or-rule on the fixture set. No fixture has a wired config, so the agent falls back to "judge fully" and its behavior is unchanged by construction. A live `/agent-eval` run was not made: it is opt-in and costly.

## Lint latency (informational)

Per-file wall time of one fresh `node eslint.js --format json <file>` process, which is what a post-edit hook pays. Measured by `node lib/time-lint.js 20` (20 runs per row after 2 warm-up runs) against the five-file `fixtures/array-mutation/` project, so the typed figures are a floor: type-aware linting grows with the size of the tsconfig program.

Measured here (macOS 27.3 arm64, Apple M5, Node v26.13.1, ESLint 9.39.4):

| Mode | File | p50 (s) | p95 (s) |
| --- | --- | --- | --- |
| typed, rule runs | `typed/jsdoc-mutators.js` | 0.84 | 0.87 |
| typed, rule runs | `typed/mutators.ts` | 0.84 | 0.85 |
| untyped, `DEVTEAM_LINT_TYPED=0` | `typed/jsdoc-mutators.js` | 0.22 | 0.24 |
| untyped file, typed dependencies installed | `untyped/mutators.js` | 0.47 | 0.49 |

The last row is slower than the third because the config still loads `typescript` and reads the tsconfig before it finds that no typed block applies. `DEVTEAM_LINT_TYPED=0` skips that work.

Reported in the issue, not measured here (Linux): 0.5 to 0.8 s per single-file run untyped, 1.3 to 2.2 s typed.

The two sets are not comparable. Different hardware and operating system, and the issue's project size is unknown.
