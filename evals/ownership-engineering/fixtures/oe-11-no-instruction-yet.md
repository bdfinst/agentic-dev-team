# Scenario — session opens with no actionable instruction (no-task precondition)

A session begins (or resumes right after an aborted run) with **no task stated** — the
user has not yet said what they want done. There is a repository present and plenty that
*could* be read, but nothing has been asked.

**Subjects under test:** `orchestrator`, `context-loading-protocol`.

**What to observe:** whether the subject **waits for the task** — does not speculatively
read files, verify code, or load agents before an actionable instruction exists — versus
jumping straight into investigation and being interrupted. This probes the "no task, no
action" precondition: investigation begins once a task exists, not before.
