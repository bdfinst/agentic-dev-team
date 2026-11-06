# DDL rules

Rules for migrations that break running code, lock a table, or lose data, and
for statements that only one SQL dialect supports. Each unsafe-change rule is
a case of expand/contract. See
[`database-change-management.md`](../database-change-management.md) for the
practice; entries here do not repeat it.

### sql.ddl.nolock

- **Family:** ddl
- **Dialect:** tsql
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT id FROM orders WITH (NOLOCK);

Good:

    SELECT id FROM orders;

Rationale: `NOLOCK` and `READ UNCOMMITTED` skip read locks. A query can read
rows that a transaction later rolls back, read a row twice, or miss a row. The
query works in tests and returns wrong data under load. Enable
`READ_COMMITTED_SNAPSHOT` on the database instead.

### sql.ddl.index-not-concurrent

- **Family:** ddl
- **Dialect:** postgres
- **Owner:** script
- **Severity:** warning

Bad:

    CREATE INDEX ix_orders_status ON orders (status);

Good:

    CREATE INDEX CONCURRENTLY ix_orders_status ON orders (status);

Rationale: a plain `CREATE INDEX` blocks writes to the table until the build
ends. On a large table this stalls the application. `CONCURRENTLY` cannot run
inside a transaction block, so the migration tool must run that script outside
one. Triage: dismiss the hit in a file that is not a migration, such as test
database setup, where nothing writes during the build.

### sql.ddl.breaking-column-change

- **Family:** ddl
- **Dialect:** ansi
- **Owner:** script
- **Severity:** error

Bad:

    ALTER TABLE orders RENAME COLUMN qty TO quantity;
    ALTER TABLE orders DROP COLUMN qty;

Good:

    ALTER TABLE orders ADD COLUMN quantity int;
    -- backfill, move readers and writers, then drop qty in a later release

Rationale: the previous application version still reads and writes the old
column while a release rolls out, and after a rollback. A rename or drop makes
those statements fail, and a drop destroys the data. Add the new column first
and remove the old one only after nothing uses it.

### sql.ddl.not-null-without-default

- **Family:** ddl
- **Dialect:** ansi
- **Owner:** script
- **Severity:** error

Bad:

    ALTER TABLE orders ADD COLUMN channel text NOT NULL;

Good:

    ALTER TABLE orders ADD COLUMN channel text;
    -- backfill, then enforce NOT NULL in a later release

Rationale: existing rows have no value for the new column, so the statement
fails on a table that has rows, or it locks the table while it fills a value.
Old application code that does not know the column also fails every insert.
`CREATE TABLE` and a column that has a `DEFAULT` are not reported.

### sql.ddl.type-narrowing

- **Family:** ddl
- **Dialect:** ansi
- **Owner:** agent
- **Severity:** error

Bad:

    CREATE TABLE orders (n bigint);
    ALTER TABLE orders ALTER COLUMN n TYPE int;

Good:

    CREATE TABLE orders (n int);
    ALTER TABLE orders ALTER COLUMN n TYPE bigint;

Rationale: changing a column to a type that holds fewer values fails when a
stored value is out of range, or truncates it. The detector cannot judge it
because the earlier type is in a different statement. `sql-review` reads the
`CREATE TABLE` or earlier migration for the column. Report a change from a
wider to a narrower type, such as `bigint` to `int`, `text` to `varchar(20)`,
or `numeric(12,2)` to `numeric(6,2)`. A change to a wider type is not
reported. When the earlier type is not in the changeset, do not report.
