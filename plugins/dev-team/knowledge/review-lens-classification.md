# Review Roster: Discovery Lens vs. Verification Gate (#2007)

Two classes of review agent need two different value metrics, and pricing
both the same way misreads one of them:

- **Discovery lens** — scans an open-ended set of possible defects across a
  domain (SRP violations, race conditions, N+1 queries, ...). `$/finding` is
  a meaningful cost signal for this class: a lens that consistently costs a
  lot per finding is a real tier-down/removal candidate.
- **Verification gate** — confirms one specific, fixed thing (does the
  implementation match the spec, does the diff follow the plan). `$/finding`
  is the **wrong** metric here: a verification gate that mostly passes is a
  gate doing its job, not evidence of low value (see #2007's own framing —
  pricing silence as waste is the mirror image of the "gate that cannot
  fail" failure `CLAUDE.md` warns about). The meaningful measure for this
  class is **escape rate**: how often something the gate should have caught
  reached a later stage anyway.

This file is the durable record of that classification, per issue #2007's
acceptance criterion ("every roster agent classified ... with the
classification recorded"). The roster itself is
[`agent-registry.md`](agent-registry.md)'s Review Agents table — this file
classifies it, it does not duplicate the roster.

**Scope note.** This is a classification, not a routing decision. No entry
here tiers down, removes, or reweights any agent — see #2007's own scope
("Coordinate with #1980 and #1982 ... you're building the classification
and attempting the recomputation, not acting on either yet").

## Classification

| Agent | Class | Rationale |
| --- | --- | --- |
| a11y-review | discovery-lens | Scans WCAG/ARIA/keyboard-nav for an open set of possible violations — no single fixed contract to confirm against. |
| ai-provenance-review | discovery-lens | Surfaces unverified AI-authored assertions and regeneration-risk candidates — an open detection surface. |
| arch-review | discovery-lens | Scans layer boundaries, dependency direction, and pattern consistency broadly; its ADR-compliance sub-check is verification-flavored, but the majority of its surface is open-ended discovery. |
| claude-setup-review | discovery-lens | Scans for an open set of CLAUDE.md/rule/path gaps, not one pass/fail check. |
| complexity-review | discovery-lens | Metric-based scan (size, cyclomatic complexity, nesting, parameters) with no external fixed contract. |
| component-architecture-review | discovery-lens | Scans for reusable-component extraction, duplication, and prop-drilling — open-ended. |
| concurrency-review | discovery-lens | Scans for race conditions, async pitfalls, shared state — open-ended. |
| correctness-review | discovery-lens | Named explicitly as discovery in `skills/code-review/SKILL.md` ("an inverted assertion is exactly its subject"). |
| data-flow-tracer | discovery-lens (analysis-only) | Surfaces data-flow traces with no pass/fail verdict — `$/finding` needs adapting to "value per trace surfaced," but it is a discovery tool, not a gate. |
| doc-review | discovery-lens | Scans README/API-doc/ADR drift across an open set of possible staleness. |
| domain-review | discovery-lens | Scans domain-boundary and abstraction-leak violations — open-ended. |
| js-fp-review | discovery-lens | Scans array-mutation and impure-pattern violations — open-ended. |
| mutation-kill | **not applicable** | Explicitly documented in `agent-registry.md` as "Not a reviewer" — an autonomous survivor-reduction loop, not a panel lens. Neither `$/finding` nor escape rate applies; excluded from this classification rather than force-fit. |
| naming-review | discovery-lens | Scans naming-convention and magic-value violations — open-ended. |
| performance-review | discovery-lens | Scans resource leaks, N+1 queries, unbounded growth — open-ended. |
| progress-guardian | verification-gate | Checks plan adherence and commit discipline against one fixed contract (the plan itself) — `docs/team-structure.md` names it "a process gate-keeper, not a code reviewer," not part of the standard review-dispatch fan-out. |
| quality-reviewer | verification-gate (coordinator caveat) | Coordinates the Inline Review Checkpoint's fix loop to convergence rather than producing its own domain findings — its meaningful measure is "did the checkpoint converge," closer to a gate's pass/fail than a lens's per-finding cost. |
| refactor-opportunity-review | discovery-lens | Scans for post-GREEN refactoring opportunities — open-ended. |
| security-review | discovery-lens | Named explicitly as a discovery lens in `skills/code-review/SKILL.md`, and explicitly excluded from the test-only-diff skip candidates precisely because it finds real issues (credentials, injection payloads) across every diff shape. |
| session-analysis | discovery-lens (analysis-only) | Surfaces ranked improvement suggestions from a session digest — no pass/fail verdict, but an open discovery surface, not a fixed-contract check. |
| spec-compliance-review | **verification-gate** | The paradigm case named directly in #2007: confirms the implementation matches the spec. A gate that usually passes ("145 of 248 runs are pure pass") is doing its job — `$/finding` prices that silence as waste, which is the wrong metric for this class. |
| spec-reviewer | verification-gate | Same family as `spec-compliance-review`, narrower — spec-to-diff matching for a single freshly-implemented unit (Stage 1 of the three-stage inline review). |
| structure-review | discovery-lens | Scans SRP violations, DRY, coupling, file organization — open-ended. |
| angular-reactivity-review | discovery-lens | Scans Zone.js change-detection pitfalls, OnPush/immutability violations, RxJS leaks — open-ended. |
| react-reactivity-review | discovery-lens | Scans hook-rule violations, stale closures, missing dependency arrays, subscription leaks — open-ended. |
| vue-reactivity-review | discovery-lens | Scans ref/reactive unwrapping pitfalls and watchEffect dependency tracking — open-ended. |
| test-review | discovery-lens | Scans coverage gaps, assertion quality, test hygiene — open-ended. |
| test-smell-review | discovery-lens | Scans xUnit test smells, test-double selection, test-pyramid placement — open-ended. |
| token-efficiency-review | discovery-lens | Scans file/function size and LLM anti-patterns for token cost — open-ended. |

**Tally:** 24 discovery-lens (2 of them analysis-only, noted), 4
verification-gate, 1 not-applicable — 29 agents total, matching
`agent-registry.md`'s Review Agents table row count exactly.

## Applying the two metrics

- **Discovery lenses**: `$/finding` from `metrics/review-value.jsonl` (per
  `skills/harness-audit/SKILL.md` Step 4) remains the right cost signal.
  Tier-down/removal candidates are agents with a consistently high
  `$/finding` **and** a low finding-rate, per that step's existing
  drop-candidate logic.
- **Verification gates** (`spec-compliance-review`, `spec-reviewer`,
  `progress-guardian`): the meaningful measure is **escape rate** — how
  often a defect the gate should have caught was instead caught later (a
  subsequent review round, a production incident, a later gate). No
  instrumentation for escape rate exists yet; this is a gap this
  classification surfaces, not one it closes. A future slice would need a
  way to trace "the gate passed, but the defect it should have caught
  surfaced anyway" — out of scope for #2007 itself.

## `$/finding` recomputation attempt (#2007, post-#1998)

#1998 (the 18.2% silent-drop fix) has merged, so recomputation is no longer
blocked on principle. Attempted here against whatever data this checkout
actually has:

- `.claude/metrics/review-value.jsonl` — **absent**. No `/build`/`/code-review`
  review rounds have been logged in this checkout.
- `.claude/metrics/contract-failures.jsonl` (#1998's own instrumentation,
  the repaired denominator `$/finding` needs) — **absent**. No JSON-contract
  failures have been logged either.
- `.claude/metrics/boundary-events.jsonl` — present, but 17 lines, all
  `hook: "pre-commit-gate"` records from this session's own git commits (the
  #2051/#1983 work above). Zero `dispatch-evidence-*`/`agent_dispatch_ledger`
  records for any review agent.

**Verdict: no recomputation is possible from this checkout's data — not "a
thin sample," an empty one.** `.claude/metrics/` is deny-by-default
gitignored (`**/metrics/*`, with an explicit allowlist for a handful of
files that does not include `review-value.jsonl` or
`contract-failures.jsonl`), so a fresh checkout or worktree starts with
none of this history regardless of what a maintainer's long-running local
clone has accumulated. Per the epic's evidence-first constraint and #2007's
own instruction ("say so explicitly rather than presenting a thin number as
authoritative"), no `$/finding` figure is reported here. The next
recomputation attempt needs to run from a checkout that has actually
accumulated post-#1998 `/code-review`/`/build` sessions — most likely a
maintainer's own long-running local clone, not a fresh worktree — and
should re-run `skills/harness-audit/SKILL.md` Step 4 (which already gates
on `review_value_coverage.py`'s sample-validity verdict) rather than
re-deriving the query here.
