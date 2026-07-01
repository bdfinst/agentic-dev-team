<!-- spec-version: 8.3.4 -->
# Spec: Resolve test-smell-review ↔ test-design-advisor remedy overlap at source

Closes #534.

## Intent Description

`test-smell-review` (agent) and `test-design-advisor` (skill) currently overlap on
remedy content: both derive fixture / verification / organization patterns from
the same knowledge files. `/test-design` papers over that overlap at report time
via orchestrator constraint 3 (drop duplicates, prefer the advisor's forward
sequence), but the redundancy is wasted work at the source: both components load
and reason over the same knowledge, and solo callsites (`/code-review`,
`/test-design-advisor`) re-emit the same remedies with no aggregator to reconcile
them.

The change draws an explicit division of labor between the two components — the
same shape already documented for `test-review` ↔ `test-smell-review` in
`knowledge/test-review-division-of-labor.md`. `test-smell-review` names the smell
and cites the **remedy family** (the knowledge file: `fixture-construction.md`,
`result-verification.md`, `test-organization.md`, `test-refactoring.md`); the
advisor owns the **specific remedy pattern** and its refactor sequence. The
`/test-design` orchestrator stops de-duplicating remedies (there is nothing to
de-duplicate at the family/pattern boundary) and instead joins smell rows with
advisor rows on `remedyFamily`. When either component runs solo, the smell agent
emits both fields so downstream consumers still have the full row.

Success = same-run output tokens drop (no duplicated remedy prose); the boundary
survives future knowledge-file evolution (advisor changes flow through without
needing to update smell-agent cites); every drop the `/test-design` orchestrator
still performs (mechanics duplicates between `test-review` and
`test-smell-review`) is enumerated in a "Suppressed duplicates" report footnote.

## Architecture Specification

### Components affected

1. `plugins/dev-team/knowledge/test-review-division-of-labor.md` — add a second
   section covering the smell-review ↔ advisor axis.
2. `plugins/dev-team/agents/test-smell-review.md` — extend Scope; extend JSON
   schema with a `remedyFamily` field; document that both `remedyFamily` and
   `suggestedFix` are always populated.
3. `plugins/dev-team/skills/test-design-advisor/SKILL.md` — Steps 3b / 3c each
   gain a one-line note that when invoked under `/test-design`, the advisor owns
   the specific pattern and refactor sequence; remove any residual "may overlap"
   language.
4. `plugins/dev-team/skills/test-design/SKILL.md` — rewrite orchestrator
   constraint 3 (advisor overlap no longer needs de-duplication; join on
   `remedyFamily`); extend the report template with a "Suppressed duplicates"
   section that enumerates any drops that DO still happen (mechanics overlap
   between `test-review` and `test-smell-review`).
5. `evals/expected/test-assertion-roulette.test.json` and
   `evals/expected/test-mystery-guest.test.json` — expected output now includes
   a `remedyFamily` cite alongside the smell name.

### Interfaces / data shape

`test-smell-review` output JSON gains an optional-but-always-populated
`remedyFamily` field. Allowed values are the four knowledge-file slugs:
`"fixture-construction"`, `"result-verification"`, `"test-organization"`,
`"test-refactoring"`, plus `null` for smells with no family cite (e.g. pyramid
placement flags).

```json
{
  "status": "pass|warn|fail|skip",
  "issues": [{
    "severity": "error|warning|suggestion",
    "confidence": "high|medium|none",
    "file": "",
    "line": 0,
    "smell": "",
    "message": "",
    "remedyFamily": "fixture-construction|result-verification|test-organization|test-refactoring|null",
    "suggestedFix": ""
  }],
  "summary": ""
}
```

Behavior contract: the agent **always** emits both `remedyFamily` and
`suggestedFix`. The aggregator picks — `/test-design` reports family (advisor
supplies pattern); `/code-review` and other solo callsites report the full row
using both fields. No env var, no invocation flag, no context threading.

### Constraints

- Additive schema change. Existing consumers that read `suggestedFix` continue
  to work unchanged.
- No production-code (plugin) file outside the list above should need changes.
  If any is discovered mid-build, escalate (scope violation).
- Consistent terminology across all files: **remedy family** (the knowledge
  file cite) vs **remedy pattern** (the specific named pattern within it).

### Dependencies

- Only touches the dev-team plugin. No release-please-relevant public API
  breakage (schema is additive).
- Reference the `/test-design-advisor` user-invocable demotion (#532) already
  landed as commit 5b3782b — no dependency conflict.

## Acceptance Criteria

Every criterion below is testable by reading the resulting files or running
existing gates.

1. **Division-of-labor knowledge file covers both pairs.**
   `plugins/dev-team/knowledge/test-review-division-of-labor.md` contains a new
   section headed `## test-smell-review ↔ test-design-advisor — remedy
   division` with a column-ownership table (Smell name+location, Severity,
   Remedy family, Specific remedy pattern, Refactor sequence, Forward-design
   placement) that assigns each column to one owner.
2. **Solo-vs-orchestrated rule stated explicitly.** The new section states in
   plain text: when the advisor runs (under `/test-design`), it owns the
   remedy-pattern columns; when `test-smell-review` runs solo, it fills the
   whole row.
3. **Smell-review schema carries `remedyFamily`.**
   `plugins/dev-team/agents/test-smell-review.md` documents `remedyFamily` in
   the JSON schema block with the four allowed values (or `null`) and states
   that both `remedyFamily` and `suggestedFix` are always populated.
4. **Smell-review Scope references the new section.**
   `plugins/dev-team/agents/test-smell-review.md` Scope explicitly references
   `knowledge/test-review-division-of-labor.md#test-smell-review--test-design-advisor--remedy-division`
   (or the exact heading slug the file uses) and summarizes the rule.
5. **Advisor SKILL notes the boundary in Steps 3b and 3c.**
   `plugins/dev-team/skills/test-design-advisor/SKILL.md` Steps 3b and 3c each
   contain a leading sentence stating that when invoked under `/test-design`,
   the smell agent has already named the smell and its family, and this step
   supplies the specific remedy pattern.
6. **Advisor SKILL contains no "may overlap" note.**
   `plugins/dev-team/skills/test-design-advisor/SKILL.md` does not contain
   language suggesting the advisor's remedies may overlap with smell-review
   (grep the file for "overlap" — the only permitted match is the removal
   comment in git history, not in the file itself).
7. **`/test-design` constraint 3 rewritten.**
   `plugins/dev-team/skills/test-design/SKILL.md` orchestrator constraint 3
   still handles `test-review` / `test-smell-review` mechanics overlap, but the
   smell-review / advisor remedy-overlap sentence is replaced with a statement
   that the report joins structurally on `remedyFamily` and no de-duplication
   is performed for advisor overlap.
8. **`/test-design` report template gains "Suppressed duplicates".**
   `plugins/dev-team/skills/test-design/SKILL.md` report template includes a
   `### Suppressed duplicates` section documenting each drop constraint 3 still
   performs (file:line, what was dropped, why). When nothing was dropped, the
   section reads `_None._`.
9. **Eval fixtures updated for the new field.**
   `evals/expected/test-assertion-roulette.test.json` and
   `evals/expected/test-mystery-guest.test.json` (and any other
   `test-smell-review` expected file discovered during the sweep) include a
   `mustMention` (or a new schema key) that requires the smell agent to emit
   the appropriate `remedyFamily` cite. Assertion Roulette →
   `result-verification`; Mystery Guest → `fixture-construction`.
10. **Structural gates pass.** `scripts/ci-local.sh` (agent-audit, schemas,
    lints) passes on the changed files.
11. **No solo-callsite regression.** `test-smell-review` output under
    `/code-review` still contains `suggestedFix` populated with the specific
    remedy pattern (family-only output is orchestrator-side de-emphasis, not
    an agent-side blank).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|--------------------|
| How does `test-smell-review` know it is running under `/test-design`? | `requires-stakeholder-input` | human | Always emit both fields; aggregator picks. No context threading. |
| Additive `remedyFamily` field vs reusing `suggestedFix` with new semantics? | `requires-stakeholder-input` | human | Additive — add `remedyFamily`; keep `suggestedFix`. |
| Allowed values for `remedyFamily`? | `inferable` | inference | The four knowledge files named in the issue (`fixture-construction`, `result-verification`, `test-organization`, `test-refactoring`) plus `null` for smells with no family cite (e.g. bare pyramid-placement flags). Codified directly from `test-smells.md` remedy citations. |
| Does the `Suppressed duplicates` section apply to `test-review` / `test-smell-review` mechanics drops too, or only to smell / advisor drops? | `inferable` | inference | Issue § 5 says "regardless of remedy fix" — every silent drop constraint 3 still performs must be enumerated. Since the smell/advisor branch of constraint 3 goes away in this change, the remaining drops are the `test-review` / `test-smell-review` mechanics drops. |
| Update solo-invocation eval fixtures too, or only under-`/test-design` fixtures? | `inferable` | inference | The agent always emits both fields per the confirmed design; the field is additive. Fixtures assert on the smell agent's raw output (which now always includes `remedyFamily`). All `test-smell-review` expected files need updating. |
| `LOW_VALUE` gap check | `inferable` | inference | No `LOW_VALUE` findings surfaced. Every acceptance criterion is either a documentable file change (NO_REFACTOR) or a schema/gate assertion. |

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts (**remedy family** vs **remedy pattern**)
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — inferable with rationale or resolved by human
