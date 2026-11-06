# Correctness trap rules

Rules for statements that run without error and return or change the wrong
rows. For safe change practice, see
[`database-change-management.md`](../database-change-management.md).

### sql.correctness.null-equality

- **Family:** correctness
- **Dialect:** ansi
- **Owner:** script
- **Severity:** error

Bad:

    SELECT id FROM t WHERE deleted_at = NULL;

Good:

    SELECT id FROM t WHERE deleted_at IS NULL;

Rationale: any comparison with `NULL` through `=`, `<>`, `!=`, `<=`, or `>=`
evaluates to unknown, so the predicate never matches. `SET col = NULL`,
`DEFAULT NULL`, `VALUES (NULL)`, T-SQL `DECLARE @v int = NULL`, and the
null-safe `<=>` are not comparisons and are not reported.

### sql.correctness.unbounded-write

- **Family:** correctness
- **Dialect:** ansi
- **Owner:** script
- **Severity:** error

Bad:

    DELETE FROM sessions;
    UPDATE users SET active = 0;

Good:

    DELETE FROM sessions WHERE expires_at < now();
    UPDATE users SET active = 0 WHERE id = 1;

Rationale: an `UPDATE` or `DELETE` with no `WHERE` changes every row. Only a
`WHERE` at the statement's own level bounds it: a `WHERE` inside a subquery
does not. `UPDATE ... ON CONFLICT DO UPDATE`, `MERGE ... THEN UPDATE`,
`SELECT ... FOR UPDATE`, `ON DELETE`/`ON UPDATE` actions, and `GRANT` lists
are not writes. `TOP` (T-SQL) and `LIMIT` (MySQL) count as a bound, for batch
deletes. For an intended full-table change, use `TRUNCATE` or suppress the rule
with a reason.

### sql.correctness.implicit-cross-join

- **Family:** correctness
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT a.x FROM a, b;

Good:

    SELECT a.x FROM a JOIN b ON a.id = b.a_id;

Rationale: a comma-separated `FROM` list with no `WHERE` pairs every row of
one table with every row of the other, so the row count multiplies. A missing
join condition usually causes it. The rule skips a query with a `WHERE`,
commas in the select list, and correlated sources such as `LATERAL` or
`unnest(a.xs)`. Write `CROSS JOIN` when the product is intended.

### sql.correctness.not-in-subquery

- **Family:** correctness
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u);

Good:

    SELECT id FROM t WHERE NOT EXISTS (SELECT 1 FROM u WHERE u.t_id = t.id);

Rationale: when the subquery returns one `NULL`, `NOT IN` evaluates to unknown
for every row and the query returns nothing. The detector cannot see column
nullability, so `sql-review` triages each hit against the `CREATE TABLE` in
the changeset. It keeps the finding when the subquery column is nullable
(`t_id int NULL`) or its definition is not in the changeset. It dismisses the
finding when the column is `NOT NULL` or the subquery filters with
`IS NOT NULL`. A literal list such as `NOT IN (1, 2, 3)` is not reported.

### sql.correctness.distinct-masks-join

- **Family:** correctness
- **Dialect:** ansi
- **Owner:** agent
- **Severity:** warning

Bad:

    SELECT DISTINCT o.id
    FROM orders o JOIN order_items i ON i.order_id = o.id;

Good:

    SELECT o.id
    FROM orders o
    WHERE EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.id);

Rationale: a join to a "many" table repeats each parent row. `DISTINCT` hides
the repeats instead of fixing the join, and it hides wrong joins that should
fail a review. Report `DISTINCT` only when the query joins at least one other
table and the selected columns do not make the rows unique by themselves.
`SELECT DISTINCT country FROM customers` has no join and is not reported.
