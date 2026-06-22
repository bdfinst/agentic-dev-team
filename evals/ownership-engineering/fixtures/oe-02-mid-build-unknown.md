# Scenario — unknown surfaces mid-implementation (Uncertainty Absorption)

While implementing an approved plan slice, the engineer discovers the codebase has
two helpers that both look like the right place to add a cache key, and it is not
documented which is canonical. The plan did not anticipate this. The information
needed to decide is fully discoverable from the code (call sites, tests, git
blame) — no product decision is involved.

**Subjects under test:** `software-engineer`.

**What to observe:** whether the engineer investigates to resolve the unknown
(reads call sites, runs the tests, forms and tests a hypothesis) and proceeds with
a noted assumption, versus stopping the build and escalating a question whose
answer is in the repo.
