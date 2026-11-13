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
    INSERT INTO archive SELECT id, name FROM orders;

Good:

    INSERT INTO orders (id, name) VALUES (1, 'a');
    INSERT INTO archive (id, name) SELECT id, name FROM orders;

Rationale: an `INSERT` with no column list maps values to columns by position,
whether the rows come from `VALUES` or from a `SELECT`. When a migration adds,
drops, or reorders a column, the statement fails with a column-count error or
loads a value into the wrong column. The `SELECT` source can be plain,
parenthesized, after a `WITH` clause or an `OUTPUT` clause, or a `UNION` of
selects. The target name can hold template placeholders written on one line,
such as `{0}`, `{0:N2}`, or `{tableName}`, as in
`INSERT INTO FDTEMP_{0} VALUES (...)`. The `INSERT` branch of a `MERGE`
(`WHEN NOT MATCHED THEN INSERT VALUES (...)`) is reported the same way.
`INSERT ... DEFAULT VALUES` and an `INSERT` with a column list are not
reported. An `INSERT ... SELECT *` is reported only as
[`sql.schema.insert-select-star`](#sqlschemainsert-select-star).

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
report the same `SELECT`, and
[`sql.schema.positional-insert`](#sqlschemapositional-insert) does not also
report a missing column list. An `INSERT` with a named select list is not
reported here; without a target column list, it is a
[`sql.schema.positional-insert`](#sqlschemapositional-insert) finding.

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
