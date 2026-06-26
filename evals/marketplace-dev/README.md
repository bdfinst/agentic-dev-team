# Eval corpus — marketplace-dev

Fixtures (`fixtures/`) and their expected gradings (`expected/*.json`) for the
`marketplace-dev` plugin's review agent and advisory skill. This corpus lives at
the **repo root** (never inside `plugins/marketplace-dev/`) so it is not shipped.

It is a **separate corpus** from the dev-team default (`evals/expected` +
`evals/fixtures`): the CI structural gate (`scripts/eval_grade.py --check-corpus`)
runs against the default dirs only. To structurally validate this corpus, point
the grader at it explicitly:

```bash
python3 scripts/eval_grade.py --check-corpus \
  --expected-dir evals/marketplace-dev/expected \
  --fixtures-dir evals/marketplace-dev/fixtures
```

## Grading contract

Each `expected/<stem>.json` pairs with a `fixtures/<stem>.*` input and declares
the unit under test plus the bound the actual output must satisfy.

### `/agent-type-advisor` (4 fixtures)

Targeted via `applicableSkills: ["agent-type-advisor"]` and a `skills` block:

| Fixture | Mode | Expected |
|---|---|---|
| `ata-prose-script` | forward-looking (prose) | `recommendation: script`, cites ≥2 of R1/R3/R4/R5 |
| `ata-prose-markdown` | forward-looking (prose) | `recommendation: markdown`, cites ≥2 of R6/R7/R9 |
| `ata-file-keep` | retrospective (agent file) | `KEEP` (should-be `markdown`), cites ≥2 |
| `ata-file-change` | retrospective (agent file) | `CHANGE` markdown→`script`, cites ≥2 of R1/R2/R5 |

A run **passes** when the recommendation matches `expectedRecommendation`, the
mode matches `expectedMode`, and the output cites at least `minRuleCitations`
distinct rule IDs from `knowledge/agent-type-decision-rules.md` (including the
`mustCiteAnyOf` set).

### `plugin-best-practices-review` (2 fixtures)

Targeted via `applicableAgents: ["plugin-best-practices-review"]` and an `agents`
block (same shape as the dev-team review-agent corpus — `expectedStatus`,
`issueCount` {min,max}, `severities`):

| Fixture | Plugin | Expected |
|---|---|---|
| `pbpr-clean` | one correctly-typed team agent, in budget, no review agents | `status: pass`, 0 issues |
| `pbpr-issues` | a markdown review agent doing mechanical version-sync work + no eval coverage | `status: fail`, ≥1 issue flagging the type mismatch |

`pbpr-clean` is the dogfood pattern: a clean plugin yields zero findings.
