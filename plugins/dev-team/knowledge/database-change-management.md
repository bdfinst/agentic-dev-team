# Database Change Management

Reference for evolving a schema while keeping every release candidate
deployable and every change reversible. Source: *Continuous Delivery* (Humble &
Farley) Ch.12. This file is about **changing** the database safely in a CD
pipeline; for **testing** against a database see `database-test-patterns.md`.

The governing rule: **a schema change must never block a deploy or a rollback.**
The application and the database evolve on independent clocks, so any single
change must work with both the old and the new application version.

## Everything is a versioned, scripted migration

- The database has a **version** (a row in a `schema_version` / `migrations`
  table). A migration tool (Flyway, Liquibase, `dbmate`, Rails/Alembic/EF
  migrations) computes which scripts to apply to move from the current version to
  the target and runs them at deploy time.
- Every change is a **script in version control** — initialization and each
  migration. No manual SQL against any environment, including production. The
  scripts provision any database in the pipeline from empty to current.
- Each forward (roll-forward) script has a matching **roll-back script**. Test
  both: applying then reverting a migration must return the schema to its prior
  shape.

## Expand / contract (the parallel-change pattern)

A change that would break the running application if applied in one step is split
into backward-compatible phases. This is the core technique for zero-downtime.

| Phase | What happens | Compatibility |
|-------|--------------|---------------|
| **Expand** | Add the new structure (new column/table/index) without removing the old. Backfill data. New and old code both work. | Deploy independently of the app |
| **Migrate** | Ship app code that writes to both old and new, reads new. Backfill completes. | Old code still works |
| **Contract** | Once no running app version references the old structure, drop it in a later release. | Only after the app no longer needs it |

Example — rename `qty` → `quantity`: add `quantity` (expand) → dual-write and
backfill → switch reads → drop `qty` in a subsequent release (contract). The
rename is never a single `ALTER ... RENAME` that breaks the deployed app.

## Make changes reversible without data loss

| Change | Reversible approach |
|--------|---------------------|
| Drop column/table | Copy data to a temp/archive table first (preserve keys + constraints); the roll-back restores from it. Never drop in the same release that stops using it. |
| Narrow a type / add NOT NULL | Add nullable, backfill, enforce in a later release once data is clean |
| Add a constraint | Validate existing data first; add as `NOT VALID` then validate, so the lock is short |
| Destructive data fix | Snapshot affected rows before the change so the roll-back script can replay them |

For zero-downtime where transactions are in flight, prefer **cache-and-replay**
or a blue-green database (backup/restore on the standby) over an in-place
destructive change.

## Decouple database change from application change

- Design the app so the database can migrate **independently** of the app upgrade
  — the schema is at a version the current *and* next app version both accept.
- Let the data owner (DBA or the owning team) evolve the schema incrementally;
  the app does not assume the two deploy atomically.
- For shared or orchestrated databases, rehearse the change in a production-like
  (SIT) environment before production.

## Detection — flag these in review

| Signal | Risk | Fix direction |
|--------|------|---------------|
| A migration that `DROP`s or `RENAME`s a column/table referenced by the same release's app code | Breaks running app during rollout; blocks rollback | Split into expand/contract across releases |
| A roll-forward script with no roll-back script | Cannot roll back the release | Author the paired reversal; test it |
| `NOT NULL` / new constraint added without a backfill step | Migration fails or locks on real data | Add nullable → backfill → enforce later |
| App code and schema assumed to deploy atomically (read of a column added in the same deploy) | Old app instances error mid-rollout | Make the change backward-compatible (expand first) |
| Manual SQL in a runbook instead of a versioned script | No audit trail, not reproducible, drifts across environments | Move into a migration script in version control |

## How this connects to the rest of the toolkit

- **`database-test-patterns.md`** — how to *test* against a database (isolation,
  teardown, real-vs-fake); this file is how to *change* one safely.
- **`release-strategies.md`** — expand/contract is the data-tier counterpart of
  decoupling deploy from release; blue-green and canary assume the schema is
  compatible across the versions running side by side.
- **`deployment-pipeline.md`** — migrations run as an automated, scripted step of
  the same deploy process in every environment.
