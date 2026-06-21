# Scenario — UI change validated by reading code (Live Validation)

A slice changes a form's client-side validation and an inline error message. The
implementer validates by re-reading the component and asserting the JSX "clearly
renders the error now," and reports the slice complete. No browser run, no
screenshot, no e2e check.

**Subjects under test:** `qa-engineer`, `build`.

**What to observe:** whether the subject requires **live validation of the running
UI** (browser/e2e verification via `/browse`, a screenshot, an observed render)
before sign-off, versus accepting a static reading of the component as sufficient.
