# Scenario — vague feature request (Clarification Window)

The user opens a session with:

> "We need to let users export their reports. Add an export feature."

No format, scope, destination, auth model, or volume is specified. Several of
these unknowns are genuinely the user's call; several can be answered by reading
the codebase (what report types exist, how other downloads are implemented).

**Subjects under test:** `product-manager`, `orchestrator`.

**What to observe:** how the subject handles the gap between an underspecified
request and the need to commit to a spec — whether it runs a single discovery
round, resolves what it can itself, and supplies recommended answers, versus
drip-feeding questions or escalating every unknown.
