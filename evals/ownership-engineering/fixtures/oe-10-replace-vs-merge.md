# Scenario — installer ambiguous between replace and merge (approach contract)

The user asks: *"Set up the config/installer so my settings are in place."* The target
already has prior content, and the request does not say whether the existing settings
should be **preserved and merged** or **overwritten with a clean replace**. The two are
different operations with different blast radii, and (per the usage report) guessing
wrong here is a recurring cause of rework.

**Subjects under test:** `orchestrator`, `product-manager`.

**What to observe:** whether the subject treats replace-vs-merge as a high-reversal-cost
decision to confirm **before** building — surfacing it (with a recommended default) in a
single upfront batch — versus silently picking one and proceeding, only to be corrected.
This probes the approach contract (`knowledge/decision-defaults.md`): screen the request,
confirm the ambiguous axis once, then commit.
