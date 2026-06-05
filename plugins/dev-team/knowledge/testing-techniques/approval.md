# Approval testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior produces a large or structured **text artifact** — rendered HTML/Markdown, JSON/CSV export, generated code, a report, a log — and asserting field-by-field would be unreadable.

**What it is.** Capture the output once, have a human approve it as the *approved* (golden) file; the test then diffs current output against approved. A change surfaces as a diff to re-approve, not a rewritten assertion.

**When to use.** Output is wide, stable, and a diff is more legible than N equality asserts. Excellent for characterizing legacy output before refactoring.

**Trade-offs / cost.** Approved files must be reviewed on every intended change — rubber-stamping defeats the test. Non-deterministic fields (timestamps, ids, ordering) must be scrubbed/normalized first or the test flaps. Store approved files in VCS.

**Minimal shape.** `approve("invoice-html", renderInvoice(order))` → first run writes `invoice-html.approved`; later runs diff against it.

**Complements.** A verification *style* at unit/component/integration — not a new pyramid layer. For **visual/CSS** fidelity use `screenshot.md` instead; for **text** correctness, approval is cheaper. Tools: ApprovalTests, Verify, jest snapshots (treat snapshots as approval — review them).
