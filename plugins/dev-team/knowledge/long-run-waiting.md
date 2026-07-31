# Waiting on Long-Running Work

Read before arming any timer, monitor, or self-re-arming check-in for a job
that outlives a single turn: mutation runs, long evals, CI jobs, full test
suites, watched PRs. Skills that reference this file: `/long-eval`,
`/mutation-testing`, `/stryker-xunit-v2-shim`, `/ci-debugging`, `/ship`.

## Pick the waiting mechanism first

| Situation | Mechanism |
| --- | --- |
| The job emits a stream (log file, command output) and you want the event the moment it appears | A monitor on that stream, with an exit condition — never an unbounded `tail -f` |
| The job's progress is only readable by re-running a status command | A scheduled wake-up whose body re-runs that status command |
| A wake could be missed (container recycle, dropped notification) | A scheduled wake-up as a **backstop**, in addition to the primary signal |
| Anything | **Never** a foreground `sleep`/`while true` in Bash — it burns the turn and cannot survive a recycle |

The tool that arms a scheduled wake-up is **surface-specific** — a session may
expose a wake-up scheduler, a `send_later`-style reminder, a cron-style
Routine, or none of them. Use whichever the session actually exposes; if none
does, say so and fall back to reporting status when the operator next asks.
Do not synthesize a wait out of `sleep`.

## The scheduled wake-up calling contract

Every scheduler in this family takes the **work to do on wake** as a required
argument. There is no "just wait, no instructions" call shape. Concretely, on
the Remote runtime's `ScheduleWakeup`:

- `prompt` (**required**) — the instruction re-issued when the timer fires.
  This is the whole point of the call: the wake-up replays the prompt, it does
  not resume some remembered intent.
- `reason` (**required**) — one short sentence on what is being waited for.
- `delaySeconds` — clamped to `[60, 3600]`.
- `stop: true` — ends the loop. This is the **only** shape that may omit
  `prompt`, and it takes **no other fields**.

**The failure this prevents:** calling the scheduler with only a delay (or
only a reason) fails with

```
Error: `prompt` is required when `stop` is not true.
```

and — the part that actually costs you — **no timer is armed**. A backstop that
errored is a backstop that never fires, so a missed wake is never recovered and
the run looks stalled with nothing scheduled to notice. Two call shapes, both
complete:

- **Arm / re-arm:** `delaySeconds` + `prompt` + `reason`.
- **Stand down:** `stop: true` alone.

Ending a check-in loop means the second shape. Passing a `reason` that explains
why you are stopping — with no `stop: true` — is the same malformed call as
above, not a stop.

## Re-arming loops

A check-in that is supposed to repeat must carry its own continuation: the
`prompt` you pass has to re-issue the same status-check-and-re-arm instruction,
because the next firing starts from that prompt and nothing else.

State the terminal condition inside the prompt, so the loop can end itself —
"stop re-arming once `status` reports `DONE`, or if the operator said stop"
— and end it with a `stop: true` call, not by silently letting the last wake
pass. A loop with no terminal condition in its own prompt runs until the
operator kills it.
