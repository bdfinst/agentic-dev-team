# Report Output Location

`.dev-team-reports/` is the shared location convention for dev-team's
human-invoked report-writing skills — `/review-agent`, `/code-review`
(interactive mode), `/triage`, and `/session-review`. It is a **literal,
hardcoded directory name** — it is not an environment variable, and it is
not currently overridable.

**Boundary: dated human-invoked reports vs. skill-internal scratch state.**
A skill lands here when a human directly invokes it to produce a durable,
readable deliverable (a review, a triage record, a session digest). Skills
that write bare `metrics/`/`memory/` scratch data for their *own* internal
bookkeeping — not a human-facing report — stay outside this convention even
when the word "report" appears in their name or output; see each such
skill's own path documentation for its rationale.

This file defines *where* reports go. `knowledge/report-template.md` defines
*what's inside* them (shared header/footer/empty-section contract) — the two
concerns compose independently.

## Write-scope rule

Only a **top-level human invocation** writes to `.dev-team-reports/`:

- `/review-agent <agent>` writes `.dev-team-reports/<agent>.md` — **unless**
  `--internal` is passed (the orchestrator-internal dispatch signal; `/build`
  is the only sanctioned caller today).
- `/code-review` (interactive, no `--json`) writes
  `.dev-team-reports/code-review.md` — **unless** `--internal` is passed (the
  sanctioned callers today are `/build`'s Step 6 backstop review and
  `/test-improve`'s Phase 5/7 end-of-phase review loop — see below for
  `/ship`'s Step 5, a deliberate, documented exception that keeps writing
  the report) or `--json` is passed (CI/`/pr` callers — `--json` never
  writes a file, full stop).
- `/triage` writes `.dev-team-reports/triage/<slug>.md` unconditionally — it
  has no orchestrator-internal caller today.
- `/session-review` writes `.dev-team-reports/session-review-<date>.md` (or
  `--out`) unconditionally — it has no orchestrator-internal caller today.

`--internal` and `--json` are orthogonal flags on `/code-review`: `--json`
governs output format and bypasses the review-fix loop; `--internal` only
suppresses the `.dev-team-reports/` write and has no effect on the fix loop
or output format.

## Report exception: /ship

`/ship`'s Step 5 ("Review") dispatches `/code-review` with neither
`--internal` nor `--json` — so it writes `.dev-team-reports/code-review.md`
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
a `.dev-team-reports/code-review.md` write from either would represent only
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
that is **overwritten on every run** (`.dev-team-reports/<agent>.md`,
`.dev-team-reports/code-review.md`) — safe to overwrite because each file
represents "the latest state for this repo," not a history. Both skills
print a confirmation line noting the overwrite (`Report written:
.dev-team-reports/<name>.md (replaced previous run)`) so this is visible at
the point of use, not only here.

`/triage` is the deliberate exception: `.dev-team-reports/triage/<slug>.md`
is **never overwritten** — a same-slug collision appends `-2`, `-3`, … up to
`-99`. This is safe and necessary because, unlike a single repo's "latest
review state," multiple distinct bugs can be triaged concurrently and each
deserves its own durable record.

## Write failures are always non-fatal

A `.dev-team-reports/` write failure (permission/read-only) is reported to
chat but never blocks or alters the skill's existing primary output — the
JSON result and chat summary for `/review-agent`, the prose summary for
`/code-review`, and the temp-file/chat fallback for `/triage`. The file
write is strictly additive.

## Gitignored by default, with a tracked exception for report data

`.dev-team-reports/` is gitignored by default — both in this repo's own
`.gitignore` and in `/project-init`'s JS-scaffold `.gitignore` template for
newly-provisioned target repos — matching the existing treatment of
`reports/` and the prior `.triage/` convention it replaces. Both use the
same anchored deny-all + re-included tracked-exception shape (`/.dev-team-reports/*`
followed by `!/.dev-team-reports/test-improve/`), not a blanket directory
ignore — `/test-improve`'s `<slug>/data/` sibling directory (issue #1412) is
git-tracked, and each artifact under it is written there directly, atomically,
at the point of capture (never copied there later from a separate working
location), so its report is a pure function of tracked data and regeneratable
from a fresh checkout.

## Related

- `knowledge/report-template.md` — the shared header/footer/empty-section
  content contract for what goes *inside* a report written to this location.
