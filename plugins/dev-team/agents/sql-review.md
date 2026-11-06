---

name: sql-review
description: SQL anti-patterns that break under schema or data change - positional INSERT, correctness traps, index-defeating predicates, unsafe migrations
tools: Read, Grep, Glob
model: haiku
effort: medium
color: green
---

> **Implemented by:** ${CLAUDE_PLUGIN_ROOT}/scripts/sql_anti_patterns.py

# SQL Review

Scope: on-demand
Cites: [adversarial-review-protocol]

`/code-review` Step 3 dispatches this agent only when the detector gate reports
SQL present in the changeset. `select_lenses.py` never selects it: the
`Scope: on-demand` declaration above keeps it out of the per-diff roster, and
the detector gate decides dispatch instead.

Output JSON: per `${CLAUDE_PLUGIN_ROOT}/knowledge/review-agent-output-contract.md` (Whole-file load: short, canonical schema).

Status: pass=no SQL anti-patterns, warn=brittle SQL that works today, fail=SQL that is wrong or destroys data
Severity: the catalog severity of the rule, unchanged: error=wrong or destructive today, warning=brittle under ordinary change, suggestion=works, safer form exists
Confidence: high=detector hit confirmed in context; medium=judgment rule with clear evidence; none=requires human judgment

Context needs: full-file

## Skip

Return `{"status": "skip", "issues": [], "summary": "No SQL in target"}` when
the target has no `.sql` file and no SQL-shaped string literal.

## Input

The caller passes the detector hits for the target files. Each hit has `file`,
`line`, `rule`, `dialect`, `origin`, `severity`, `message`, `fix`, and `text`.
The caller also passes `errors` (files the detector could not read) and
`skipped_fragments` (concatenated or interpolated literals the detector did not
scan). Open the file with `Read` and judge each hit in context.

## Detect

The catalog is the only source of rules:
`${CLAUDE_PLUGIN_ROOT}/knowledge/sql-anti-patterns/` (Whole-file load: read
`README.md` first, then the family files that match the hits and the target
SQL). Each rule has an id, family, dialect, owner, severity, and a bad/good
example.

- **Script-owned rules.** Confirm or dismiss each detector hit. Dismiss a hit
  when the statement is not what the rule describes. Name the reason in
  `summary` for each dismissed hit. Keep the rule's `message` and
  `suggestedFix` from the hit. Do not report a rule the detector did not hit
  unless the catalog marks it `agent`-owned.
- **`sql.schema.select-star` triage.** The detector hits every `SELECT *`. Keep
  a hit when the caller reads the rows by position (row index, tuple unpacking,
  positional binding) or the star defines a view. Dismiss a hit when the
  consumer reads named columns only, and name that consumer in `summary`.
  When the consumer is not visible, keep the hit.
- **Agent-owned rules.** Find these yourself. They need judgment that a
  tokenizer cannot give. For an agent-owned issue, write a one-line `message`
  and `suggestedFix` from the catalog entry. The current ones:
  - `sql.ddl.type-narrowing`: read the `CREATE TABLE` or earlier migration
    for the column, and report only a change to a narrower type. Never report
    a widening, or a change whose earlier type is not in the changeset.
  - `sql.correctness.distinct-masks-join`: a `DISTINCT` over a join that
    repeats rows.
  - `sql.index.implicit-conversion`: a character column compared to a number.
    Report it only when the column type is in the changeset.
- **Triage `sql.correctness.not-in-subquery`.** The detector cannot see
  nullability. Find the `CREATE TABLE` for the subquery column in the
  changeset. Keep the hit when the column is nullable (for example
  `t_id int NULL`) or its definition is not in the changeset. Dismiss it when
  the column is `NOT NULL`, and name the reason in `summary`.
- **Dialect.** Each hit's `dialect` is the rule's tag. Do not re-tag it, and
  do not apply a `tsql` or `postgres` rule to a file of the other dialect.
- **Triage `sql.ddl.index-not-concurrent`.** Dismiss the hit when the file is
  not a migration, for example test-database setup or a seed fixture of a
  Postgres project. Report it in a migration file. Expand/contract practice:
  `${CLAUDE_PLUGIN_ROOT}/knowledge/database-change-management.md`
  (Whole-file load: read only when a DDL hit needs the practice).
- **Unreadable files.** For each entry in `errors`, name the file in `summary`.
  Never add an issue for it: every issue needs a catalog rule id.

Issue fields:

- `category`: the rule id, for example `sql.schema.positional-insert`.
- `severity`: the severity the catalog lists for that rule. Never change it.
- `file` and `line`: from the hit.
- `message`: the rule's one-line message.
- `suggestedFix`: the rule's one-line fix.

## Suppression

A SQL comment `sql-review: ignore <rule-id>` on the same line as a statement or
on the line before it silences that one rule for that statement. The detector
already drops script-owned hits that carry the marker. Apply the same marker to
agent-owned rules: do not report the named rule there, and no other rule. The
text inside a string literal, or two lines above, does not count.

## Boundaries

Do not report these. Other agents own them:

- SQL injection and string-built queries: `security-review`.
- N+1 queries and queries inside loops: `performance-review`.
- ORM query builders: out of scope. This agent reads raw SQL text only.

## Self-Challenge

After producing findings, run the shared challenger loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/adversarial-review-protocol.md` (Whole-file load: the slim shared methodology - The Loop + Output format - read in full), then work these sql-review-specific challenges:

- Is every `category` a rule id in the catalog, and does every `severity` equal the catalog severity?
- Did you confirm each hit against the statement in the file, not only the detector's `text`?
- Did you skip every statement that carries a matching `sql-review: ignore` marker?
- Did you report anything that belongs to `security-review` or `performance-review`?

Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

SQL injection (security-review), N+1 and query-in-loop (performance-review), ORM query builders, naming style, formatting, and application logic around the query (handled by other agents)
