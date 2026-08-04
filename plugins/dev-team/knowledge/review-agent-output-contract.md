# Review-agent output contract

The JSON shape every read-only `*-review` agent emits. This is the single
source of truth — agent files cite this instead of inlining the schema, so
the contract can't drift between the ~20 agents that share it.

## Canonical schema

```json
{"status": "pass|warn|fail|skip", "issues": [{"category": "", "severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

`category` is optional per finding — omit it rather than emit an empty
string when a finding genuinely has no natural taxonomy tag.

## `category` (#1639)

A short, stable tag identifying the *kind* of finding within an agent's own
taxonomy — not a cross-agent enum, and not required to be a strict
linter-style rule ID. Its purpose is round-to-round finding identity:
`skills/code-review/scripts/finding_signature.py`'s `signature()` hashes
`(agent, file, category, normalized-message)`, with the finding's `line`
compared separately at a `±3` tolerance by `same_finding()` rather than
folded into the hash. The `category` component of that hash is resolved
from a fallback chain — `category` → `smell` → `rule` → `ruleId` (#1692) —
so an agent that spells its taxonomy tag `smell` (`test-smell-review`) gets
the same round-to-round identity protection as an agent that spells it
`category`. Message normalization strips quoted spans and numbers
by design, so two genuinely *different* findings from the same agent, same
file, and within a few lines of each other can normalize to the same text
(e.g. two distinct missing-guard-clause defects a couple of lines apart
whose messages differ only in the quoted identifier that normalization
strips). Without `category` to tell them apart, those collide into one
signature, and — because they also fall inside the `±3` proximity window —
a later round's genuinely new defect matches a prior round's key and reads
as `carried` rather than new, silently suppressing a fix round the
loop-until-dry/severity-floor termination rules #1625 added were supposed to
run.

Each agent defines its own taxonomy in its own body — see each agent's
`## Detect` (or equivalent) section for its specific category values. Three
worked examples already shipping on this contract (kept in sync with the
named agent files by `tests/repo/test_review_agent_output_contract_examples.py`):

- **`security-review`**: `"category": "A<NN>.<slug>"` (the OWASP category the
  finding maps to), e.g. `"A03.sql-injection"`.
- **`ai-provenance-review`**: `"category": "verification-debt|regeneration-risk"`.
- **`spec-compliance-review`**: `"category": "unmet-criterion|uncovered-scenario|scope-violation|plan-deviation"`.

Four more agents converge on the same field name independently: the
`plan-review-*` critics (`plan-review-design`, `plan-review-parallelization`,
`plan-review-strategic`, `plan-review-ux`) each emit their own `category`
values too, on a different `{"verdict", "issues"}` schema dispatched by
`/plan` rather than this contract's `{"status", "issues"}` shape — not a
fourth spelling to reconcile, but further evidence the name reads naturally
across this repo's own review agents.

A new agent that reports findings across more than one natural taxonomy
bucket should add its own `category` values the same way — a short,
lower-case, hyphenated tag per bucket, documented in the agent's own body —
rather than leaving the field unset.

**Not the same `category` as `apply-fixes`'s correction-prompt schema.**
`skills/apply-fixes/SKILL.md`'s correction-prompt `category` field holds the
*reporting agent's name* (e.g. `"structure-review"`), grouping fixes for
display — a different concept that happens to share this field name in a
downstream artifact generated *from* findings. Do not assume a correction
prompt's `category` carries a finding's taxonomy tag through unchanged.

## Status values

- **pass**: zero issues
- **warn**: issues found, none are errors
- **fail**: at least one error-severity issue
- **skip**: agent had nothing to review this run — no files in scope (e.g.,
  no JS/TS files for `js-fp-review`), or excluded by a pre-flight gate.
  Canonical definition — `output-format.md` and `SKILL.md` cite this rather
  than restate it.

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
to their domain, beyond the canonical `category` documented above. These are
intentional, documented exceptions — not drift:

- **`test-smell-review`**: adds `"smell": ""` and
  `"remedyFamily": "fixture-construction|result-verification|test-organization|test-refactoring|null"`
  to each issue. `smell` is this agent's own taxonomy tag; `signature()`'s
  fallback chain is `category` → `smell` → `rule` → `ruleId` (#1692), so its
  findings hash with `smell` as their taxonomy component instead of an empty
  segment.

An agent that needs a new field beyond these documents it here rather than
drifting silently.

## Aggregation

`/code-review` wraps each agent's raw result with `agentName` and
`modelTier` when assembling the panel-wide report — see
[`skills/code-review/output-format.md`](../skills/code-review/output-format.md)
for the aggregated `--json` shape, the per-slice section artifact, and the
progress-ledger/consolidation formats sliced mode adds on top of this
per-agent contract.
