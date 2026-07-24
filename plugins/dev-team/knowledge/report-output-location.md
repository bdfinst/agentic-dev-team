# Report Output Location

`DEV_TEAM_REPORTS/` is the shared location convention for dev-team's
human-invoked report-writing skills — `/review-agent`, `/code-review`
(interactive mode), and `/triage`. It is a **literal, hardcoded directory
name** — despite the SCREAMING_SNAKE_CASE styling it is not an environment
variable, and it is not currently overridable.

This file defines *where* reports go. `knowledge/report-template.md` defines
*what's inside* them (shared header/footer/empty-section contract) — the two
concerns compose independently.

## Write-scope rule

Only a **top-level human invocation** writes to `DEV_TEAM_REPORTS/`:

- `/review-agent <agent>` writes `DEV_TEAM_REPORTS/<agent>.md` — **unless**
  `--internal` is passed (the orchestrator-internal dispatch signal; `/build`
  is the only sanctioned caller today).
- `/code-review` (interactive, no `--json`) writes
  `DEV_TEAM_REPORTS/code-review.md` — **unless** `--internal` is passed (the
  sanctioned callers today are `/build`'s Step 6 backstop review and
  `/test-improve`'s Phase 5/7 end-of-phase review loop — see below for
  `/ship`'s Step 5, a deliberate, documented exception that keeps writing
  the report) or `--json` is passed (CI/`/pr` callers — `--json` never
  writes a file, full stop).
- `/triage` writes `DEV_TEAM_REPORTS/triage/<slug>.md` unconditionally — it
  has no orchestrator-internal caller today.

`--internal` and `--json` are orthogonal flags on `/code-review`: `--json`
governs output format and bypasses the review-fix loop; `--internal` only
suppresses the `DEV_TEAM_REPORTS/` write and has no effect on the fix loop
or output format.

## Report exception: /ship

`/ship`'s Step 5 ("Review") dispatches `/code-review` with neither
`--internal` nor `--json` — so it writes `DEV_TEAM_REPORTS/code-review.md`
by default, unlike `/build`'s Step 6 and `/test-improve`'s Phase 5/7 review
loop above. This is a **deliberate, stated exception** to the "only a
top-level human invocation writes" rule, not an unaudited gap (issue #982):

`/ship` is itself `user-invocable: true` and is only ever entered by a
human directly typing `/ship` — but so is `/build`, whose own internal
Step 6 dispatch is suppressed, so being human-typed at the top isn't by
itself what earns the exception. The stronger distinguishing factor is
**frequency and scope, not surfacing**: `/build`'s Step 7.5 evidence bundle
does surface the Step 6 `/code-review` *status* back to the human at
completion (a pass/fail line, not the artifact itself), and `/test-improve`
similarly surfaces its review outcome in each phase's evidence file — so
"no human-facing surfacing at all" is not the real dividing line. What
actually differs: `/build`'s Step 6 and `/test-improve`'s per-phase loop
each run **multiple times across a session** (once per build, once per
`/test-improve` phase) against a **diff-scoped** slice of the total change —
a `DEV_TEAM_REPORTS/code-review.md` write from either would represent only
one slice's worth of review, repeatedly overwritten, not "the latest state
for this repo." `/ship`'s Step 5 runs **once**, at the end of the whole
shipped feature, over the **full accumulated diff** — the one point in the
pipeline where a durable, complete review artifact is both meaningful and
non-redundant. Reinforcing this: `/code-review`'s own step-6 "exception (b)"
(which skips the interactive fix-or-report prompt for callers "running
inside `/build` or `/pr`") does not name `/ship` either — `/ship`'s dispatch
is genuinely interactive today, consistent with a human being present for
this one-time gate rather than an orchestrator-internal backstop.

## Fixed filenames: overwrite vs. never-overwrite

`/review-agent` and `/code-review` write a **fixed, per-workflow filename**
that is **overwritten on every run** (`DEV_TEAM_REPORTS/<agent>.md`,
`DEV_TEAM_REPORTS/code-review.md`) — safe to overwrite because each file
represents "the latest state for this repo," not a history. Both skills
print a confirmation line noting the overwrite (`Report written:
DEV_TEAM_REPORTS/<name>.md (replaced previous run)`) so this is visible at
the point of use, not only here.

`/triage` is the deliberate exception: `DEV_TEAM_REPORTS/triage/<slug>.md`
is **never overwritten** — a same-slug collision appends `-2`, `-3`, … up to
`-99`. This is safe and necessary because, unlike a single repo's "latest
review state," multiple distinct bugs can be triaged concurrently and each
deserves its own durable record.

## Write failures are always non-fatal

A `DEV_TEAM_REPORTS/` write failure (permission/read-only) is reported to
chat but never blocks or alters the skill's existing primary output — the
JSON result and chat summary for `/review-agent`, the prose summary for
`/code-review`, and the temp-file/chat fallback for `/triage`. The file
write is strictly additive.

## Gitignored by default

`DEV_TEAM_REPORTS/` is gitignored by default — both in this repo's own
`.gitignore` and in `/project-init`'s JS-scaffold `.gitignore` template for
newly-provisioned target repos — matching the existing treatment of
`reports/` and the prior `.triage/` convention it replaces.

## Related

- `knowledge/report-template.md` — the shared header/footer/empty-section
  content contract for what goes *inside* a report written to this location.
