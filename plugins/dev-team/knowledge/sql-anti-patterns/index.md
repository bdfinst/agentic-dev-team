# Index-defeating rules

Rules for predicates that stop the database using an index, so the query scans
the table as it grows. For index and migration practice, see
[`database-change-management.md`](../database-change-management.md).

### sql.index.function-on-column

- **Family:** index
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT id FROM users WHERE LOWER(email) = 'a@b.c';

Good:

    CREATE INDEX users_email_lower ON users (LOWER(email));
    -- or store the value already lower-cased and compare the bare column
    SELECT id FROM users WHERE email = 'a@b.c';

Rationale: a plain index holds the column value, not `LOWER(value)`. A function
over the column in `WHERE` or a join `ON` forces a scan. The rule reports a
non-aggregate call whose arguments name a column. It skips a function over
literals or variables (`email = LOWER('A@B.C')`), `IN` lists, `EXISTS`,
aggregates, `HAVING`, the select list, and full-text predicates such as
`CONTAINS`. An expression index on the same function removes the finding.

### sql.index.leading-wildcard

- **Family:** index
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    SELECT id FROM t WHERE name LIKE '%smith';

Good:

    SELECT id FROM t WHERE name LIKE 'smith%';

Rationale: a B-tree index orders values from the first character, so a pattern
that starts with `%` has no prefix to seek and the database reads every entry.
Use a prefix match, or full-text or trigram search for contains-style
matching. The rule reports `LIKE` and `ILIKE` with a string literal that starts
with `%`, including `N'%x'` and `CONCAT('%', ...)`. A pattern in a variable is
not reported.

### sql.index.implicit-conversion

- **Family:** index
- **Dialect:** ansi
- **Owner:** agent
- **Severity:** warning

Bad:

    CREATE TABLE t (code varchar(10));
    SELECT id FROM t WHERE code = 42;

Good:

    SELECT id FROM t WHERE code = '42';

Rationale: when a character column meets a number, the database converts the
column, not the literal, in many engines (T-SQL by type precedence), so the
index on the column is not used and some rows can fail to convert. Report a
comparison only when the changeset defines the column as a character type and
the other side is a numeric literal or numeric parameter. An integer column
compared to an integer literal is not reported. If the column type is not in
the changeset, do not report.
