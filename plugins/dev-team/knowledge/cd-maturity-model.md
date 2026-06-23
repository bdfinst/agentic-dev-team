# Continuous Delivery Maturity Model

Reference for assessing and improving an organization's delivery capability.
Source: *Continuous Delivery* (Humble & Farley) Ch.15. Use it to locate where a
team is, pick the one area worth improving next, and define the outcome that
proves the improvement landed.

This measures **delivery capability** (can this team release small changes safely
and often?). It is a *different axis* from the agent-readiness scorecard
(`skills/agent-readiness/`), which measures how ready a repo is for AI-agent
work. A repo can score high on one and low on the other; assess them separately.

## The six practice areas

Maturity is read per area, not as a single number — a team is usually uneven.

| Practice area | What it covers |
|---------------|----------------|
| **Build management & CI** | Build automation, trunk-based CI, fast feedback, build discipline |
| **Environments & deployment** | Automated provisioning, identical deploy everywhere, release strategies, rollback |
| **Release management & compliance** | Change/approval flow, traceability, audit through the pipeline |
| **Testing** | Automated test strategy across the pyramid, deterministic gates |
| **Data management** | Scripted, versioned, reversible migrations; managed test data |
| **Configuration management** | Everything in version control; config per environment; secrets handling |

## The five levels

| Level | Name | Signal |
|-------|------|--------|
| **3** | Optimizing | Teams continuously improve the process; cycle time and stability are measured and trending down/up |
| **2** | Quantitatively managed | Process metrics gathered and used to make decisions; risk understood |
| **1** | Consistent | Automated processes applied across the whole lifecycle, used by everyone |
| **0** | Repeatable | Process documented and partly automated; results repeatable |
| **−1** | Regressive | Processes ad hoc, manual, unrepeatable; results unpredictable |

Score each of the six areas against the five levels to get a profile, not a grade.

## How to improve (the Deming cycle)

1. **Map the value stream** — commit to release — and find the most painful /
   slowest area. Improve *that*, not everything at once.
2. **Define acceptance criteria** for the improvement (a measurable outcome).
3. **Implement** the smallest change that moves the area up a level.
4. **Measure** against the criteria; **retrospect**; roll the change out
   incrementally. Repeat. Never try to jump all areas to the top level at once.

## The outcomes to target

The model is a means; these are the ends. Track them directly:

| Metric | What it tells you |
|--------|-------------------|
| **Cycle time** (commit → releasable) | The primary global signal; the Theory-of-Constraints lens for finding the bottleneck |
| **Deployment frequency** | How small and frequent changes are |
| **Change failure rate** | Quality of the gate; stability of releases |
| **Mean time to restore (MTTR)** | Strength of rollback / recovery |

The last three plus lead time are the DORA four key metrics; cycle time is the
internal lens that explains them.

## Guiding principles

- **Prefer automation over documentation.** An automated script is executable
  documentation that must work and stays current; a document proving you did
  something doesn't guarantee you did.
- **Compliance *through* the pipeline, not against it.** The pipeline is the best
  audit trail — lock down privileged environments, require approvals, and build
  authorization/auditing into the deploy path. Build binaries once and hash them
  to prove production matches source.
- **Release as often as possible** — at least every iteration, even with no users
  yet. "If it hurts, do it more frequently." Iterative, incremental delivery is
  the core of risk management.
- **Don't work in silos.** Favor cross-functional teams; treat change management
  as risk management with a remediation (back-out) plan and an acceptance test per
  change.

## How this connects to the rest of the toolkit

- **`deployment-pipeline.md`** / **`release-strategies.md`** / **`database-change-management.md`**
  — the practices that move the environments, deployment, and data areas up the model.
- **`cd-test-architecture.md`** — the testing area's gate.
- **`skills/agent-readiness/`** — the orthogonal axis (AI-agent readiness); cross-reference, don't conflate.
