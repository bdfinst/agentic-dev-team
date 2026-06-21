# Scenario — a test fails for an unexpected reason (Debug, Don't Stop)

During GREEN, a test the engineer expected to pass fails with an assertion about a
date being off by one. The cause is not obvious from the message alone, but it is
fully investigable (timezone handling in a shared helper). This is the first
failure on this test.

**Subjects under test:** `systematic-debugging`, `build`.

**What to observe:** whether the subject treats the failure as a **debugging task**
— reproduce, investigate, state root cause, then fix — versus halting after the
first failure and handing the problem back, or thrashing "try a few things"
without finding root cause.
