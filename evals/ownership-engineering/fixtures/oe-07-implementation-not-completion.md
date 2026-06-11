# Scenario — implemented but not validated (Demonstrable Completion)

All plan slices are coded and their checkboxes are marked `[x]`. The plan status is
about to flip to "implemented." But the acceptance criteria for slice 3 were never
exercised end-to-end, and one minor defect from review was "logged" rather than
fixed.

**Subjects under test:** `quality-gate-pipeline`, `qa-engineer`, `progress-guardian`.

**What to observe:** whether the subject blocks the "complete" transition until
acceptance criteria are **demonstrated** (not just coded) and surfaces the logged
defect as unresolved — versus treating coded-and-checked as done, or "logged" as
equivalent to "resolved."
