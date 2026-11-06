# Schema coupling rules

Rules for queries that depend on column count or order instead of column
names. Such a query works today and breaks after a harmless schema change. See
[`database-change-management.md`](../database-change-management.md).

### sql.schema.positional-insert

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    INSERT INTO orders VALUES (1, 'a');

Good:

    INSERT INTO orders (id, name) VALUES (1, 'a');

Rationale: an `INSERT ... VALUES` with no column list maps values to columns
by position. When a migration adds, drops, or reorders a column, the statement
fails with a column-count error or loads a value into the wrong column.
`INSERT ... DEFAULT VALUES` and an `INSERT` with a column list are not reported.
