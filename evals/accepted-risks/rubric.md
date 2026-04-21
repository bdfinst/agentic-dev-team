# accepted-risks eval rubric

Grades `/code-review` and `/review-agent` behavior when an `ACCEPTED-RISKS.md` is present at the repo root.

## Fixtures

- `fixtures/matched/` — repo with `ACCEPTED-RISKS.md` declaring two rules:
  - Rule A matches one finding present in the seeded findings list → suppressed
  - Rule B matches nothing (targets a `rule_id` that no finding carries) → no-op, no suppression, no error
- `fixtures/init/` — repo without `ACCEPTED-RISKS.md`. Exercises the `--init-risks` scaffold flag.

## Hard gates

### `matched` fixture

1. Exactly ONE finding is suppressed (the one Rule A matches).
2. The suppression is logged to the audit trail with format `SUPPRESSED: <file>:<line> [<rule_id>] by ACCEPTED-RISKS rule <rule.id>`.
3. All other seeded findings flow through to the report unchanged.
4. Rule B's presence does not error; it is simply a no-op.
5. The review summary counts "1 finding suppressed by ACCEPTED-RISKS (rule a-known-false-positive-in-tests)".

### `init` fixture

1. Running `/code-review --init-risks` in this fixture copies `templates/ACCEPTED-RISKS.md.tmpl` to the repo root as `ACCEPTED-RISKS.md`.
2. Exit code 0.
3. Running `/code-review --init-risks` a second time (now that the file exists) exits non-zero without overwriting.
4. The scaffolded file validates against `knowledge/accepted-risks-schema.md` frontmatter rules.

## Soft gates

- Suppression entries appear together at the end of the report, not interleaved with real findings.
- If any rule in `ACCEPTED-RISKS.md` has `expires` in the past, the review run emits a WARN naming the rule and its owner.
- If any rule has `broad: true`, the review run emits an informational notice listing broad rules for auditor attention.

## Negative cases (must not happen)

- A rule with a bad date (non-ISO-8601) → review run MUST fail with a specific parse error naming the rule id. Do NOT silently ignore the rule.
- A rule with empty `rationale` → review run MUST fail.
- Wildcard `rule_id` without `broad: true` → review run MUST fail.

## Grading aggregation

Per fixture: all hard gates pass → pass; one hard gate fails → fail; soft gates ignored in pass/fail but reported.

Negative cases each run as their own mini-fixture; each MUST produce the expected failure.
