# Schema coupling rules

Rules for queries whose result depends on column count or column order instead
of column names. Such a query works today and breaks after a harmless schema
change. See
[`database-change-management.md`](../database-change-management.md): the
application and the database change on independent clocks, so a statement must
survive the other side adding a column.

### sql.schema.positional-insert

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    INSERT INTO orders VALUES (1, 'a');

Good:

    INSERT INTO orders (id, name) VALUES (1, 'a');

Rationale: an `INSERT ... VALUES` with no column list maps each value to a
column by position. When a migration adds, drops, or reorders a column, the
statement fails with a column-count error or, worse, loads each value into the
wrong column. A column list makes the statement independent of column order and
lets the table gain columns that have a default. `INSERT ... DEFAULT VALUES` and
an `INSERT` with a column list are not reported.
