# Acceptance examination (mechanism)

Detail for `/build` [Step 7.6](../SKILL.md). The Step 7.6 prose says when to
examine. This file holds the dispatch prompt and what to do with each
`status` result.

The `acceptance-examiner` agent runs the plan's commands and reads only their
output. The SubagentStop recorder hook writes the record. `/build` never
relays a verdict.

## Dispatch prompt template

Build the prompt in three parts:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/acceptance_examination.py inputs --plan <plan>`.
2. Replace `<cwd>` with the absolute repo root.
3. Paste the `inputs` output verbatim after the `Working directory:` line.

The `inputs` output already ends with the marker line the recorder hook uses
to find the plan. Do not edit or move it. Add nothing else to the prompt.

````text
Examine this change by running commands: run the listed commands from the working directory, read their output and `.feature` files, and read nothing else.

Working directory: <cwd>

AC1: <criterion 1 text>
AC2: <criterion 2 text>

```gherkin
<gherkin block for a slice>
```

Run commands:
- <run command 1>
- <run command 2>

Acceptance-examination plan: <plan>
````

## Status handling

In this file, `acceptance_examination.py status` means the subcommand, not
the plan's **Status** line.

### Before dispatch

Run `acceptance_examination.py status --plan <plan>`.

| `status` result | Action |
|---|---|
| exit 0, met record | Skip dispatch. Run `render` and continue to Step 7.5. The record certifies committed state only. A later commit makes it stale. |
| exit 0, plan declares `**Examination**: not-applicable` | Skip dispatch. Do not run `render` (there is no record). Continue to Step 7.5. The evidence bundle lists the exemption. |
| exit 1, message starts `Acceptance examination cannot be verified` or `Acceptance examination cannot run` | The branch base is unresolvable, or there are no commits ahead of the base. Print the message and stop. Do not dispatch. There is nothing to examine. |
| exit 1 for any other reason | The record is absent, stale, or failing. Dispatch once (steps 2 to 5 of Step 7.6): run the clean-tree check (`git status --porcelain --untracked-files=all`; an untracked file counts as dirty), run `inputs`, then dispatch the examiner once with the template above. |
| exit 2 | Usage error, or the plan is not in a git repository. Print stderr and stop. No dispatch, no `render`. |

If `inputs` exits non-zero (for example the plan has no
`## Acceptance Criteria` section), print its stderr and stop. Do not
dispatch. Otherwise print `Examining N criteria with run commands only; this
can take several minutes.` and record
`DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)` just before the dispatch.

### After dispatch

Run `acceptance_examination.py status --wait 15 --after $DISPATCHED_AT --plan <plan>`.
The wait covers the delay between the examiner stopping and the hook writing
the record. A record older than the dispatch counts as absent. Do not
dispatch again.

| `status --wait 15` result | Action |
|---|---|
| exit 0 | Run `render` and continue to Step 7.5. |
| exit 1 with a readable record | Run `render`, print the status message, and stop. |
| exit 1, record unreadable or for another plan | Do not run `render`. Print the status message and stop. |
| exit 1, no record (absent) | Recognised by the message prefix `Acceptance examination missing`. Print the absent-after-dispatch text below, verbatim, and stop. |
| exit 2 | Usage error, or the plan is not in a git repository. Print stderr and stop. No `render`. |

If `render` exits non-zero, print its stderr and stop.

Absent-after-dispatch text:

> No examination record was written after the examiner stopped. Likely causes: the SubagentStop recorder is not installed (reinstall the plugin), or the dispatch prompt lacked the marker line (see .claude/metrics/boundary-events.jsonl, rule missing-plan-marker). Fix the cause, then run: /build <plan>.

## Hard stop

Every stop above leaves the plan's **Status** line unchanged. Step 8 is not
reached. The `acceptance_examination.py status` message names the case.

- `not-met`: a criterion failed its run command. Fix the delivered behavior, commit, then run `/build <plan>`. Do not proceed to /pr.
- `indeterminate`: the examiner could not observe a criterion, or its result was incomplete or malformed. The `acceptance_examination.py status` message names which. Unobservable: make the criterion observable in the plan. Incomplete result: run `/build <plan>` again without changing the plan. Do not proceed to /pr.
- `tainted`: the examiner ran a command it must not. Detection is by pattern and can be a false positive. Name a run command for each criterion, then run `/build <plan>`. Do not proceed to /pr.
- `missing` (status absent): no record exists for this plan. Fix the cause in the absent-after-dispatch text above (the recorder is not installed, or the marker line is missing), then run `/build <plan>`. Do not proceed to /pr.

The `**Examination**: not-applicable` header and any criterion edit belong to
the human plan author at the plan gate. `/build` and `/fix` never add,
remove, or reword them to clear a stop.
