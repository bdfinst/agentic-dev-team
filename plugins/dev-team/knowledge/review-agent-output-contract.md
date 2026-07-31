# Review-agent output contract

The JSON shape every read-only `*-review` agent emits. This is the single
source of truth — agent files cite this instead of inlining the schema, so
the contract can't drift between the ~20 agents that share it.

## Canonical schema

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

## Status values

- **pass**: zero issues
- **warn**: issues found, none are errors
- **fail**: at least one error-severity issue
- **skip**: agent is inapplicable to the target (e.g., no JS/TS files for `js-fp-review`)

**Documented per-agent status exception:** `doc-review` and `naming-review`
escalate a `warning`-severity finding to `fail` as well as `error` — for
these two, a misleading name or a stale/incomplete doc is high-cost enough
on its own that it doesn't wait for a second, error-severity finding to
raise the tier. Every other agent uses the default rule above.

## `severity` values

`error` (must fix), `warning` (should fix), `suggestion` (could improve).

## `confidence` values

| Value | Meaning | `apply-fixes` behavior |
|-------|---------|----------------------|
| `high` | Mechanical fix; correct with high certainty | Auto-apply |
| `medium` | Direction right; tradeoffs possible | Present as suggested diff — require confirmation |
| `none` | Requires human judgment | Present finding only; do not generate correction prompt |

## Documented per-agent extensions

A handful of agents extend the canonical schema with extra fields specific
to their domain. These are intentional, documented exceptions — not drift:

- **`security-review`**: adds `"category": "A<NN>.<slug>"` to each issue
  (the OWASP category the finding maps to).
- **`test-smell-review`**: adds `"smell": ""` and
  `"remedyFamily": "fixture-construction|result-verification|test-organization|test-refactoring|null"`
  to each issue.

An agent that needs a new field beyond these documents it here rather than
drifting silently.

## Aggregation

`/code-review` wraps each agent's raw result with `agentName` and
`modelTier` when assembling the panel-wide report — see
[`skills/code-review/output-format.md`](../skills/code-review/output-format.md)
for the aggregated `--json` shape, the per-slice section artifact, and the
progress-ledger/consolidation formats sliced mode adds on top of this
per-agent contract.
