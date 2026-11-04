---
name: doctor
description: >-
  Diagnose the dev-team plugin install and this repo's dev-team configuration, and create missing runtime directories with --fix.
argument-hint: "[--json] [--fix]"
user-invocable: true
allowed-tools: Bash
---

# Doctor

Role: worker. This command runs one script that checks the plugin install and
this repo's dev-team configuration. It is a purely mechanical lookup. You do
not interpret the checks.

You have been invoked with the `/doctor` command.

Arguments: $ARGUMENTS

## Steps

Run the script and report its output verbatim:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/scripts/doctor.py" $ARGUMENTS
```

Pass only these tokens through `$ARGUMENTS`: `--json`, `--fix`, and `--project <DIR>`.
Wrap DIR in single quotes, and replace each `'` inside DIR with `'\''`.
If any other token appears, refuse the whole invocation and run nothing.
Also refuse if a shell metacharacter appears outside the quoted DIR: `;`, `|`, `&`, `$`, a backtick, `(`, `)`, `<`, `>`, or a newline.

`hooks/py.sh` resolves a real Python 3 interpreter on every OS, or exits 2.

## Exit codes

- Exit 0: print stdout verbatim, then stderr if it is not empty.
- Exit 1: a diagnosis, not a tool error: print stdout verbatim, then stderr if it is not empty, and do not retry.
- Exit 2: print stderr verbatim.

Exit 1 also follows a failed `--fix` action; stderr carries the errors in both modes, and the text report also lists them in an `errors:` block.
Exit 0 means no row failed, and warn rows do not fail the run.

## Flags

- `--json` prints the report as JSON instead of text.
- `--fix` creates the missing `.claude/metrics` and `.claude/memory` directories, and their `.claude` parent if that is also missing. It changes no other file. With `--fix`, the text report also lists the `fixed:` directories (or `fixed: none`), plus an `errors:` block if an action failed, before the `overall:` line.
- `--project DIR` diagnoses the project containing DIR instead of the current directory.

## Checks

The script runs these nine checks, in this order:

1. `plugin-version`
2. `hook-registration`
3. `interpreter`
4. `python-floor`
5. `required-tools`
6. `optional-tools`
7. `metrics-writable`
8. `project-settings`
9. `managed-sections`

Each row shows a status (`ok`, `warn`, or `fail`), the check id, and a summary.
A `warn` or `fail` row can add a `fix:` line: a command to run, or a sentence
to follow. The script sets the `overall:` line and the exit code.

## Example

```text
plugin: /home/user/.claude/plugins/cache/bfinster/dev-team/14.0.1
project: /home/user/my-repo
ok    plugin-version  14.0.1 installed (catalog 14.0.1)
ok    hook-registration  51 hook commands, every script present
ok    interpreter  py.sh resolved /usr/bin/python3
fail  python-floor  /usr/bin/python3 is 3.9.7; floor is 3.10
      fix: install Python 3.10+ (ADR 0031)
ok    required-tools  jq on PATH
ok    optional-tools  present: gh, uv; absent: semgrep, adr, shellcheck
warn  metrics-writable  /home/user/my-repo/.claude/metrics missing
      fix: /doctor --fix
ok    project-settings  env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is '40'
ok    managed-sections  not opted in
overall: fail
```

Do not add commentary beyond the script's output.
