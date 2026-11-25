# Measurements: pilot ESLint config vs the agents

Recorded 2026-11-25. Informational, except that the comparison decides which bullets are converted.

## Method

- **Agent found** is not a live `/agent-eval` run. It is `corpus/agent-found.json`:
  - For `evals/fixtures/fp-*.ts`, the cases the fixtures plant (their `// mutation:` and `should be const` comments). The committed `evals/expected/fp-*.json` carry only issue-count ranges, so a Node test checks each fixture's planted count against that range.
  - For `corpus/esm-cjs.js` and `corpus/fp-detect-text.ts`, cases written from the agents' Detect text. There is no `esm-enforcer` eval fixture. Agreement on these files holds by construction. Their value is the exception cases, where the agent reports nothing and the rule must too.
- **Rule found** is `corpus/rule-found.json`, produced by `node lib/corpus.js` with the TypeScript parser from `@typescript-eslint/parser` for `.ts` files.
- A **false positive** is a rule finding on a line where the agent reported nothing. `convertible` also needs at least one agent case as evidence.

## Comparison on the full corpus

| Rule | Agent found | Rule found | False positives | Residual | Convertible |
| --- | --- | --- | --- | --- | --- |
| `no-param-reassign` | 6 | 6 | 0 | 0 | yes |
| `no-plusplus` | 3 | 3 | 0 | 0 | yes |
| `no-restricted-globals` | 2 | 2 | 0 | 0 | yes |
| `no-restricted-syntax` | 5 | 5 | 0 | 0 | yes |
| `no-var` | 1 | 1 | 0 | 0 | yes |
| `prefer-const` | 3 | 5 | 2 | 0 | no |

`prefer-const` false positives are `corpus/fp-detect-text.ts` lines 5 and 6: `let mutScratch` and `let _cache`, which the agent exempts by name prefix and the rule flags.

## Comparison on the eval fixtures alone

| Rule | Agent found | Rule found | False positives | Convertible |
| --- | --- | --- | --- | --- |
| `no-param-reassign` | 5 | 5 | 0 | yes |
| `no-plusplus` | 2 | 2 | 0 | yes |
| `prefer-const` | 2 | 2 | 0 | yes |
| `no-restricted-globals`, `no-restricted-syntax`, `no-var` | 0 | 0 | 0 | no (no evidence) |

The eval fixtures alone would also pass `prefer-const`. The agent's documented name-prefix exception is not exercised there, so it was added to the corpus.

All other corpus files produced zero findings, including the clean fixtures and `jest.config.cjs`.

## Gate

Five rules are convertible, so the batch continues. Eight bullets were converted: three in `esm-enforcer`, five in `js-fp-review`.

## ESLint versions

| ESLint | Where it resolved | `node --test` | Corpus output vs committed |
| --- | --- | --- | --- |
| 9.39.4 | `dev/node_modules` (pinned in `dev/package.json`) | 14 pass | identical |
| 10.15.0 | scratch install outside the repo (`DEVTEAM_ESLINT_ROOT`) | 14 pass | identical |

The repo root `package.json` and lockfile name ESLint 10.10.0, but the root `node_modules` held 9.39.4 at measurement time.

## Tokens (informational)

`scripts/measure_tokens.py`, byte-count heuristic (`tiktoken` was not installed):

| File | Before | After |
| --- | --- | --- |
| `templates/agents/esm-enforcer.md` | 476 | 662 |
| `agents/js-fp-review.md` | 2158 | 2440 |
| Total | 2634 | 3102 |

Conversion adds tokens. "Otherwise judge fully" keeps each original bullet, and each file gains one note defining "wired". Any saving comes from the agent judging less, not from a shorter prompt. Cost figures wait on the cost-meter fix.

## Agent pass criterion

Every case the agent found before is still found by agent-or-rule on the fixture set. No fixture has a wired config, so the agent falls back to "judge fully" and its behavior is unchanged by construction. A live `/agent-eval` run was not made: it is opt-in and costly.
