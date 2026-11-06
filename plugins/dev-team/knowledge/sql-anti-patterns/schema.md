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

### sql.schema.insert-select-star

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    INSERT INTO archive SELECT * FROM orders;

Good:

    INSERT INTO archive (id, name, status)
    SELECT id, name, status FROM orders;

Rationale: `INSERT ... SELECT *` ties the target to the column count and order
of the source. When a migration changes either table, the statement fails or
loads values into the wrong columns. This is the one finding for the
statement: [`sql.schema.select-star`](#sqlschemaselect-star) does not also
report the same `SELECT`. An `INSERT` with a column list from a named select
list is not reported.

### sql.schema.select-star

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT * FROM orders;

Good:

    SELECT id, name, status FROM orders;

Rationale: `SELECT *` and `SELECT t.*` return whatever columns the table has
today. The caller breaks when a migration adds, drops, or reorders a column and
the caller reads the rows by position. The detector reports every such select
list; `sql-review` triages each hit. It keeps a hit whose rows are read by
index, and dismisses a hit whose consumer reads named columns only, naming the
reason in `summary`. `COUNT(*)`, `EXISTS (SELECT * ...)`, and
`INSERT ... SELECT *` (see
[`sql.schema.insert-select-star`](#sqlschemainsert-select-star)) are not
reported.

### sql.schema.ordinal-reference

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT a, b FROM t ORDER BY 2;
    SELECT a, COUNT(*) FROM t GROUP BY 1;

Good:

    SELECT a, b FROM t ORDER BY b;
    SELECT a, COUNT(*) FROM t GROUP BY a;

Rationale: `ORDER BY 2` and `GROUP BY 1` name a select-list position. Someone
who adds or reorders a select-list column changes the sort or grouping with no
error. The rule skips `ORDER BY` inside `OVER (...)`, `WITHIN GROUP (...)`, and
aggregate calls, which sort a function's input, and skips named columns and
expressions.
