# SQL anti-pattern catalog

The catalog lists every rule that the `sql-review` agent and the
`scripts/sql_anti_patterns.py` detector report. Each rule has one entry in a
family file in this directory. The registry in `scripts/lib/sql_rules_*.py` and
the catalog must match, rule for rule.

For how to change a schema safely, see
[`database-change-management.md`](../database-change-management.md). Catalog
entries cite that file and do not repeat it.

## Entry format

Each entry is a level-3 heading with the rule id, followed by a field list, two
examples, and a rationale:

```markdown
### sql.<family>.<slug>

- **Family:** schema
- **Dialect:** ansi
- **Owner:** script
- **Severity:** warning

Bad:

    ...

Good:

    ...

Rationale: ...
```

| Field | Values |
| ----- | ------ |
| Id | `sql.<family>.<slug>`, where `<family>` is the family file name |
| Family | the family file name without `.md` |
| Dialect | `ansi` (all dialects), `tsql`, or `postgres` |
| Owner | `script` (the detector decides) or `agent` (`sql-review` decides) |
| Severity | `error`, `warning`, or `suggestion` |

Severity uses the scale in
[`review-agent-output-contract.md`](../review-agent-output-contract.md):

- `error`: the statement is wrong or destroys data today.
- `warning`: the statement is brittle and breaks under ordinary change.
- `suggestion`: the statement works and has a safer form.

The one-line message and fix of each finding live in the registry entry, not in
the catalog. Every `category` that `sql-review` emits is a rule id from this
catalog, and its `severity` equals the severity listed here.

## Add a rule

1. Add a `Rule` to `scripts/lib/sql_rules_<family>.py`. Include at least one
   positive and one negative fixture.
2. Add the entry to `<family>.md` in this directory.
3. For an agent-owned rule, add a positive and a negative eval fixture under
   `evals/fixtures/`, and the expected results under `evals/expected/`.
4. Run `tests/scripts/test_sql_rule_registry.py`. It fails when a rule has no
   fixture, a fixture misbehaves, or the catalog and registry differ.

## Suppress a finding

Write `sql-review: ignore <rule-id>` in a SQL comment on the same line as the
statement or on the line before it. The marker silences only the named rule.
The same text inside a string literal does nothing.

```sql
-- sql-review: ignore sql.schema.positional-insert
INSERT INTO audit_seed VALUES (1, 'bootstrap');
```

## Families

Each `*.md` file in this directory other than this one is one family.
