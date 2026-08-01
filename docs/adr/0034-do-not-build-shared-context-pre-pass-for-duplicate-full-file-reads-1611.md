# 34. Do not build a shared-context pre-pass for duplicate full-file reads (#1611)

Date: 2026-08-01

## Status

Accepted

## Context

Issue #1611 observed that during a large `/code-review` panel, many
independently-dispatched review agents each read the same large, unchanged
file in full within one review round. Each agent is a fresh dispatch with no
shared context, so no agent's request can reuse another agent's file read.
Two hypotheses were raised for whether this is worth fixing:

1. Anthropic prompt caching might already mitigate the cost.
2. If not, a shared "file digest" pre-pass — computed once per round and
   injected into every agent's prompt, mirroring the pattern this repo
   already uses for `repo_invariants.py`'s static-analysis pre-pass — could
   eliminate the duplicate reads.

Issue #1618 (closed via PR #1698) investigated both. Prompt caching cannot
help here, structurally: the cache key hashes the entire cumulative prefix
(tools → system → messages) up to the marked breakpoint, and each review
agent carries its own agent-definition markdown as its system prompt, so the
prefix diverges from the very first block across agents in a round — no
agent's request can ever hit a cache entry another agent's request wrote.

#1618 then built `scripts/measure_full_file_duplication.py` (repo-root per
ADR 0032 category 2 — monorepo-only measurement tooling, no shipped-skill
caller) with two legs: a theoretical floor (reusing `select_lenses.py`'s
Scope-based roster resolution plus a `Context needs:` parser to compute how
many review agents would receive a given file as a full-file payload) and
empirical validation against 9 real, independently-dispatched multi-agent
review rounds — the only real `/code-review`-equivalent transcript available
when #1618 ran, spanning two different units of review activity within that
one session. The measured avoidable-token percentage of a round's real total
spend was: min 0.38%, median 0.8%, max 4.86% (full numbers posted to #1611).
The figure is a dispatch-derived ceiling, not an observed read count — it
counts an agent as a potential duplicate reader once dispatched into a
full-file-reading role, without confirming it actually issued a `Read` on
the target file — so true duplication is at or below the quoted band.

#1618 also flagged that the pre-pass fix carries real quality-regression
risk: a structural skeleton (CodeGraph/Repowise `get_context`) is plausibly
sufficient for structural lenses (arch-review, structure-review,
domain-review, doc-review) but not for lenses that need actual line-level
logic (correctness-review, security-review, js-fp-review,
complexity-review, and others) — building it risks quietly degrading those
lenses' detection quality.

## Decision

Do not build the shared-context pre-pass fix for #1611. The measured cost —
well under 1% of round spend at the median, never above ~5% across the
sampled rounds — does not justify a fix whose own risk profile threatens
detection quality on line-level-reading lenses. Recorded by the maintainer
on #1611 — no further work will be done there.

## Consequences

**Not gained:** Round-level token spend keeps a small, measured amount of
avoidable duplication (median 0.8%, max 4.86% across the sampled rounds).

**Avoided:** The quality-regression risk a partial structural pre-pass would
have introduced for correctness-review, security-review, js-fp-review,
complexity-review, and other line-level lenses.

**Recorded, not forgotten:** #1611 is closed as measured-and-declined, not
abandoned. A future engineer re-reading #1611 does not need to redo the
measurement work in #1618/PR #1698 to reach the same conclusion, and a
future session should not re-open or re-attempt this fix without first
reading why it was declined here.

**Boundary of the evidence:** the 9 rounds come from a single session
transcript — the only `/code-review`-equivalent transcript available when
#1618 ran — and `avoidable_tokens_estimate` is a dispatch-derived ceiling
rather than an observed read count, so true duplication is at or below the
quoted band. These percentages should not be quoted beyond panels of the
shape sampled here.

**Future option:** If a review panel materially larger than the sampled
rounds, or substantially larger target files, become routine, that would be
grounds to remeasure with `scripts/measure_full_file_duplication.py` against
the new shape — but no such remeasurement is scheduled or expected.

## References

- Issue #1611 — the original observation
- Issue #1618 — the caching-structural-impossibility finding and the
  measurement
- PR #1698 — closed #1618, added `scripts/measure_full_file_duplication.py`
