# Release Strategies

Reference for releasing changes with low risk and zero downtime. Source:
*Continuous Delivery* (Humble & Farley) Ch.10, plus the version-control
techniques from Ch.14 that keep mainline releasable. This file is advisory — the
plugin recommends and plans for these patterns; it does not execute deployments.

The governing distinction: **deploy ≠ release.** Deploying puts code on a server;
releasing exposes behavior to users. Keep them separate so you can deploy
continuously and release on a business decision.

## Decouple deployment from release

| Technique | What it does | Use when |
|-----------|--------------|----------|
| **Feature toggle / flag** | Ship code dark; turn behavior on at runtime without a deploy | Incremental delivery of an unfinished feature; instant kill-switch |
| **Branch by abstraction** | Introduce an abstraction over the thing being replaced, migrate callers behind it on mainline, then delete the old path | Large changes that would otherwise need a long-lived branch |
| **Dark launching** | Run new code paths in production against real traffic without showing results to users | Validate capacity/behavior before exposure |
| **Keep mainline releasable** | Every commit leaves trunk shippable; hide incomplete work behind toggles/abstractions rather than branching | Always — this is what makes continuous delivery possible |

Toggles are **inventory**: remove each one once the feature is permanent. Stale
flags are a liability (untested combinations, dead branches).

## Deployment patterns

| Pattern | How it works | Rollback | Trade-off |
|---------|--------------|----------|-----------|
| **Blue-green** | Two identical production environments; release by switching the router to the idle one | Switch the router back | Needs double the capacity (or shared data tier handled carefully) |
| **Canary** | Roll the new version to a small subset of servers/users first; widen as confidence grows | Stop and route back to the old version | Requires routing control + per-cohort metrics; A/B and capacity testing for free |
| **Rolling** | Replace instances in batches behind a load balancer | Roll the batches back | Both versions run at once — needs backward-compatible data + contracts |
| **Recreate** | Stop old, start new | Redeploy previous version | Incurs downtime; only where an outage window is acceptable |

Keep **as few versions in production as possible** — ideally two (old + new)
during a transition. Every concurrent version multiplies the compatibility matrix.

## Rollback is a practiced capability, not a hope

- **Always be able to roll back.** Back up production state before a release and
  *rehearse* the rollback before every release — an untested rollback is not a
  rollback.
- The simplest reliable rollback is **redeploying the last known-good version**
  from scratch through the same pipeline.
- Data makes rollback hard: pair this with expand/contract migrations
  (`database-change-management.md`) so the schema is compatible with the version
  you roll back to.
- Prefer **rolling back over hot-fixing** a bad release. Emergency fixes still go
  through the standard pipeline — never hand-patch production.

## Keeping mainline releasable (Ch.14)

- **Develop on trunk; commit at least daily.** Long-lived feature branches are
  opposed to continuous integration — they cause merge hell and hide integration
  risk until late.
- Make large changes as **small incremental steps on mainline** using feature
  hiding, componentization, or branch by abstraction — not a branch.
- **Branch only for release, for a spike, or in extremis.** A release branch
  takes only critical fixes, merged back to mainline immediately; it replaces the
  anti-pattern of a code freeze.

## Planning hook

When `/plan` decomposes a feature, prefer slices that keep trunk releasable at
every step: land the change behind a toggle or behind an abstraction, sequence
data changes as expand-before-contract, and avoid a slice that is only shippable
once the whole feature is done.

## How this connects to the rest of the toolkit

- **`database-change-management.md`** — the data-tier half of every pattern here;
  rolling, blue-green, and canary all require a schema compatible across versions.
- **`deployment-pipeline.md`** — these patterns ride on a pipeline that builds the
  artifact once and promotes it; the deploy mechanism is identical per environment.
- **`cd-maturity-model.md`** — decoupling deploy from release and practiced
  rollback are what move the "environments & deployment" practice area up the model.
