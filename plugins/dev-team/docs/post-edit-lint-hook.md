# Post-edit lint hook

The post-edit lint hook runs the project's own ESLint on a file right after Claude edits it. It reports dev-team rule findings back to Claude so they are fixed in the same turn. The hook is off by default.

## Terms

- **Finding**: one ESLint message from a dev-team rule.
- **Rule id**: the ESLint rule name, for example `no-var`.
- **Advisory**: the rule has severity `warn`, so a plain `eslint` run exits 0.
- **Block**: the hook returns `decision: block` with the findings as the reason.

The shipped rules are advisory. The hook still blocks on them. It runs ESLint with `--format json` and ignores the exit code.

## Security

When enabled, the hook runs the project's own ESLint and its `eslint.devteam.config.js` after every edit, with no prompt. ESLint loads that config as JavaScript, so a config or a dependency under `node_modules` runs with your user rights. Enable the hook per project, not globally, and only in repositories you trust. Do not enable it for a repository you have just cloned and not read.

## Enable and disable

Set `DEVTEAM_POST_LINT=1` to enable the hook. For one project, set it in `.claude/settings.local.json`, which is yours alone. Set it in `.claude/settings.json` only when the whole team agrees, because that file enables the hook for every contributor and every fresh clone:

```json
{ "env": { "DEVTEAM_POST_LINT": "1" } }
```

Do not set it in your user-level settings, because that enables the hook in every project (see Security).

Set `DEVTEAM_POST_LINT=0`, or remove the variable, to disable it. With the variable unset, the hook exits at once. It does not read stdin, run ESLint, or write metrics.

## Requirements

The hook lints a file only when all of these are true:

- `eslint.devteam.config.js` is in the project root. `/setup` scaffolds it.
- `node_modules/eslint/bin/eslint.js` exists in the project root. ESLint 9 and 10 are supported.
- `node` is on `PATH`.

The project root is the git top level of the hook's working directory. The hook runs `node node_modules/eslint/bin/eslint.js --config eslint.devteam.config.js --format json <file>` from the project root. It does not use the `.bin` shim, which is a `.cmd` wrapper on Windows. It does not pass `--fix`.

Only `eslint.devteam.config.js` applies. Your own `eslint.config.js` is not loaded. The dev-team config sets no parser, so a TypeScript file that uses type syntax fails to parse and the hook fails open (see Notices). The `parse-error` notice appears once per session. After it, other TypeScript files that use type syntax are skipped with no further notice, so a project that is mostly typed TypeScript gets little from the hook.

## What the hook lints

The hook lints the whole edited file, not only the changed lines. A finding that was already in the file before the edit also blocks.

The hook lints files with these extensions: `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, `.cts`. It skips these files silently, with no notice:

- Files of any other extension, such as `.py`.
- Tools other than `Edit`, `Write`, and `MultiEdit`. The hook is registered on all three.
- Files that do not exist after the edit.
- Files outside the project, including a symlink that resolves outside it.
- Anything under `node_modules` inside the project root.

## Block output

The block reason starts with `dev-team post-edit lint (set DEVTEAM_POST_LINT=0 to disable):`. Each finding follows on its own line as `path:line rule-id message`, with the path relative to the project root.

The hook drops ESLint messages that have no rule id and messages of the form `Definition for rule 'X' was not found`. ESLint reports the second kind for an `eslint-disable` comment that names a rule that is not loaded, for example `functional/immutable-data` while typed rules are off. It is not a finding.

The reason lists at most 10 findings, then `+N more`. The whole reason is at most 4000 characters. A longer reason ends with `... [truncated]`.

## Cap on consecutive blocks

The hook blocks at most 3 times in a row in one session. The fourth violating edit is not blocked, and the hook prints `cap 3 reached; set DEVTEAM_POST_LINT=0 to disable`. A clean lint resets the count. Each session has its own count.

The count lives in `$TMPDIR/dev-team-post-lint-<uid>/`, keyed by a hash of the session id. The directory is private to your user (mode `0700`). The hook does not use a directory that is a symlink or that another user owns. It deletes state files not used for 4 hours when it writes, with their orphaned lock files.

When the hook cannot read or write that directory, it cannot count blocks, so it never blocks. It says `cannot save session state; lint skipped` (reason key `no-state`) once per session.

## Notices (fail-open)

When the hook cannot lint, it never blocks. It says why in one line through the hook JSON `systemMessage` field, once per session for each reason.

| Reason | Notice |
| --- | --- |
| No config | `eslint.devteam.config.js not found in project; lint skipped` |
| No ESLint | `ESLint not found in project; lint skipped` |
| No node | `node not found on PATH; lint skipped` |
| Timeout | `ESLint timed out after Ns; lint skipped` |
| ESLint exit with no JSON | `ESLint exited with code N and no JSON; lint skipped` |
| Invalid JSON output | `ESLint output was not valid JSON; lint skipped` |
| Invalid hook input | `hook input was not valid JSON; lint skipped` |
| Parse error in the edited file | `edited file has a parse error; lint skipped` |
| Session state not usable (`no-state`) | `cannot save session state; lint skipped` |

The timeout is 10 seconds. Set `DEVTEAM_POST_LINT_TIMEOUT` to a number of seconds between 0 and 600 to change it. A value that is not a number, not finite, zero, negative, or above 600 gives the 10-second default. On a timeout the hook kills the whole ESLint process group.

## Typed rules

The hook sets `DEVTEAM_LINT_TYPED=0` for its ESLint run, so type-aware rules (array mutation) do not run in the hook. They still run in your own `eslint` runs.

A typed run costs more per file and grows with the size of the project's tsconfig program. The only typed measurement is on the five-file fixture project: p95 0.87 s (see `plugins/dev-team/templates/eslint/dev/MEASUREMENTS.md`). No measurement exists on a project of realistic size, so the hook cannot show that a typed run stays under a 2 s per-file p95 budget. Until one is made, typed rules stay out of the hook.

Untyped hook latency, measured end to end on macOS with `py.sh`, Python start, and ESLint, over 20 runs per file after 2 warm-up runs:

| File | p50 | p95 |
| --- | --- | --- |
| `clean.js` (no findings) | 0.31 s | 0.33 s |
| `violating.js` (12 findings) | 0.32 s | 0.40 s |

## Metrics

Each run appends one line to `.claude/metrics/post-lint.jsonl`: `ts`, `session`, `ext`, `wall_ms`, and `outcome`. The outcome is `blocked`, `clean`, `skipped`, `failed-open`, or `capped`. The line holds no paths or findings. See [`telemetry-schema.md`](../knowledge/telemetry-schema.md).

A block, and the release at the cap, also append one line to `.claude/metrics/boundary-events.jsonl` (`hook` `post_lint`, `matched_rule` `lint-findings` or `block-cap`). It holds no paths or findings. The write fails open.

## Relationship to `js_fp_review.py`

`js_fp_review.py` is unchanged. It is a regex pre-check that always runs after JS and TS edits and only advises. This hook is a separate, opt-in, blocking check that uses ESLint. When both are active, one edit can draw feedback from both about the same line. The batch does not reconcile the two.

## Windows

The hook avoids the `.bin` shim and uses `node` plus the script path. It has not been run on Windows. Process-group termination on timeout uses `kill()` on the ESLint process there, which does not reach grandchildren. Treat Windows as unverified.

## Remove

Unset `DEVTEAM_POST_LINT`. To remove the rules too, delete `eslint.devteam.config.js`. `/upgrade` does not retract scaffolded files.
