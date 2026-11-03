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

### Before dispatch

Run `acceptance_examination.py status --plan <plan>`.

| `status` result | Action |
|---|---|
| exit 0 | The record is current and `met`, or the plan declares `Examination: not-applicable`. Skip dispatch. For a `met` record, run `render` and continue to Step 7.5. For the exemption, do not run `render` (there is no record) and continue to Step 7.5. |
| exit 1 for any reason → dispatch once | The record is absent, stale, or failing. Run the clean-tree check, print the progress line, and dispatch the examiner once with the template above. |

### After dispatch

Run `acceptance_examination.py status --wait 15 --plan <plan>`. The wait
covers the delay between the examiner stopping and the hook writing the
record. Do not dispatch again.

| `status --wait 15` result | Action |
|---|---|
| exit 0 | Run `render` and continue to Step 7.5. |
| exit 1 with a readable record | Run `render`, print the status message, and stop. |
| exit 1, record unreadable or for another plan | Do not run `render`. Print the status message and stop. |
| exit 1, no record (absent) | Print the absent-after-dispatch text below, verbatim, and stop. |

If `render` exits non-zero, print its stderr and stop.

Absent-after-dispatch text:

> No examination record was written after the examiner stopped. Likely causes: the SubagentStop recorder is not installed (reinstall the plugin), or the dispatch prompt lacked the marker line (see .claude/metrics/boundary-events.jsonl, rule missing-plan-marker). Fix the cause, then run: /build <plan>.

## Hard stop

Every stop above leaves the plan's **Status** line unchanged. Step 8 is not
reached. The status message names the remedy for each case.

- `not-met`: a criterion failed its run command. Fix the delivered behavior, commit, then run `/build <plan>`. Do not proceed to /pr. In short, do not proceed to /pr.
- `indeterminate`: the examiner could not observe a criterion, or its result was incomplete. Make the criterion observable in the plan, then run `/build <plan>`. In short, do not proceed to /pr.
- `tainted`: the examiner ran a command it must not. Detection is by pattern and can be a false positive. Name a run command for each criterion, then run `/build <plan>`. In short, do not proceed to /pr.
- `missing`: no record exists for this plan. Fix the cause the status message names, then run `/build <plan>`. In short, do not proceed to /pr.
