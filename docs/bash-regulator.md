# Bash regulator

`hooks/bash_regulator.py` decides allow, ask, or deny for each Bash call. The
decision is per command segment and, for subagents, per agent role. It is off
by default.

**Minimum Claude Code version: 2.1.330.** That release's PreToolUse payload
carries `permission_mode`, and `agent_id`/`agent_type` inside subagents. The
hook returns `permissionDecision`.

## Turn it on

| Variable | Value | Effect |
| --- | --- | --- |
| `DEV_TEAM_REGULATOR` | `on` | Enables the hook. Unset or any other value: the hook does nothing. |
| `DEV_TEAM_REGULATOR_MODE` | `advisory` (default) | Logs each decision to `.claude/metrics/regulator-decisions.jsonl`. Changes no behavior. |
| | `enforce` | Emits `permissionDecision`. |

Run advisory first, read the log, then switch to `enforce`.

## How it decides

1. Split the command into segments on `;`, `&&`, `||`, `|`, `&`, and newlines. Lift out `$(...)`, backticks, and `( ... )` bodies. Skip heredoc bodies.
2. Strip wrappers: `time`, `env`, `nice`, `nohup`, `command`, `exec`, `builtin`, `timeout`, `xargs`, shell reserved words, and leading `VAR=value`. Recurse into `bash|sh|zsh|dash -c`. Fail closed: a segment whose command word is unknown (`$X`, `env -S`) asks; one whose arguments or environment can change what runs (`VAR=x cmd`, `env`/`xargs`/`exec`, unknown wrapper flags, `$`/brace/glob-free expansions in arguments, a path-qualified command, `git -c ...`) is never auto-allowed. Allow rules for `git`, `gh`, and test runners use an option allowlist (`opts_re`): an unlisted or abbreviated option, such as `--upload-pac`, is not allowed. `cd`, `git -C`, `git fetch`, `git grep`, `gh api`, and `sed` beyond a print or one safe `s///` are not auto-allowed.
3. Per segment, take the first matching rule in `hooks/regulator_rules.json`. Destructive patterns are checked first.
4. Merge: deny beats ask beats allow. A segment no rule matches falls through to normal permissions, so a call is allowed only when every segment is.

A segment whose command word is a variable (`$CMD arg`) asks. An unparseable command (unbalanced quote, `$(`, or backtick) is denied with a rewrite hint.

Allow rules never match a segment that redirects to a file other than `/dev/null`.

## Destructive patterns and `/careful`

The patterns in `hooks/destructive-commands.json` become `ask` rules, or `deny`
while `/careful` is active. `destructive_guard.py` stays registered: it owns the
default-branch escalations and the `DEV_TEAM_GUARD_OVERRIDE` bypass.

## `bypassPermissions`

The regulator emits only `deny` decisions there. The user chose to skip
prompts, so `allow` and `ask` have no meaning. Settings deny rules still apply.

## Agent roles

Rules with `applies_to` fire only when the payload's `agent_type` matches one
of the globs. A leading plugin prefix (`dev-team:`) is removed first. Rules with
`subagents_only` never fire in the main session.

| Role | Rule |
| --- | --- |
| Any subagent | `git push` denied. The `pr` and `ship` skills push from the main session. |
| `*-review`, `plan-review-*` | Deny file-changing commands, git mutations, and file redirects. |
| `software-engineer` | Test and lint commands allowed. |

Decided against: limiting `software-engineer` to the files a plan step
declares. The hook cannot see the plan, and a state file written by `/build`
would add a new failure mode.

**Observed payloads** (captured from a live session; `permission_mode` was
`auto`): the main session carries no `agent_id` or `agent_type` key. A
plugin-namespaced agent arrives as `agent_type: "dev-team:software-engineer"`
with its `agent_id`. A built-in agent arrives bare (`general-purpose`). The
regulator strips the plugin prefix, so one rule glob covers both forms. The
tests in `test_bash_regulator.py` replay these payload shapes.

Review agents (`dev-team:*-review`) have only Read, Grep, and Glob, so they
cannot call Bash. The `*-review` rules are defence in depth if one gains a shell.

## Debug

```bash
python3 plugins/dev-team/hooks/bash_regulator.py --explain 'git status && rm -rf x' [--agent-type NAME] [--careful]
```

Prints the deciding rule for each segment and the merged decision.

## Measured share

Replaying 547 Bash calls from the 40 most recent local main-session
transcripts through the rules: 211 allow (39%), 1 ask, 0 deny, 335 fall through.
Most fall-throughs are inline `python3 -`/`python3 -c` scripts, `git add`/`commit`,
`cp`, `mkdir`, and shell loops. This is an offline replay, not a live advisory
session; re-measure from `regulator-decisions.jsonl` after a real session.
