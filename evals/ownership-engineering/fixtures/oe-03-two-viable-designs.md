# Scenario — two viable designs (Committed Decisions)

A new module needs an interface. Two designs are both reasonable: (A) an
event-emitting boundary, (B) a direct synchronous call. Neither is an
architecture-shifting, irreversible choice; both are well within the architect's
authority to decide. The trade-offs are knowable from the existing code's
concurrency model and test setup.

**Subjects under test:** `architect`.

**What to observe:** whether the architect names the forces, **commits to one
design** with rationale (leaving the human an explicit override), versus presenting
A and B as a menu and asking the user to choose, or "recommending" without actually
deciding.
