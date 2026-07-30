# 30. Use ancestor-check instead of exact-SHA comparison for mutation baseline reuse

Date: 2026-07-30

## Status

Accepted

## Context

Issue #1545 speced staleness for mutant-kill's Round-1 baseline-reuse feature
(#1565) as "exact commit-SHA comparison" — matching the loop's existing
convergence-history pattern (`git log -1 --format=%H -- <file>` vs. a recorded
SHA). The pre-loop baseline scan captures one mutation report at one commit,
shared across every file in the run. Literal exact-SHA equality between a
file's own last-commit SHA and that single shared capture commit would almost
never hold in practice — most files were last touched at some earlier commit,
not the exact commit the baseline happened to be captured at. Implementing
the spec literally would make reuse fire close to never, defeating the
feature's purpose (skipping a redundant scoped mutation run per file).

## Decision

Use `git merge-base --is-ancestor <file's last commit> <baseline capture
commit>` instead of exact-SHA equality — still SHA-based, not date-based, so
it preserves the spirit of "exact commit-SHA comparison" (no fuzzy date
staleness) while accepting any file whose last change happened at or before
the baseline's capture point. Git treats a commit as its own ancestor, so a
file last committed exactly at the capture commit remains eligible too (the
"self-ancestor boundary"). Implemented in
`plugins/dev-team/skills/mutation-testing/scripts/mutation_baseline_reuse.py`
(`is_eligible_for_reuse`), combined with a separate per-commit consumption
check so a baseline already consumed by a file isn't reused again for that
same capture commit.

This reinterpretation was explicitly reconsidered once during implementation
and confirmed by the human operator (2026-07-30, recorded in PR #1565's
description) before landing.

## Consequences

**Easier:** Baseline reuse actually fires for the common case — a file
unchanged since before the baseline capture — delivering the intended
skip-redundant-run savings.

**Harder / watch:** A file whose last commit is an ancestor of the capture
commit but reflects since-reverted or since-amended history could reuse a
report that no longer reflects its exact working state as precisely as
literal SHA equality would have guaranteed; the consumption check and the
loop's existing convergence-history mechanism bound this risk. Any future
reader diffing this behavior against the literal issue #1545 spec wording
should read this ADR before "fixing" it back to exact-SHA equality.
