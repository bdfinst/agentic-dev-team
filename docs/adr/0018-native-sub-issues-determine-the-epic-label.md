# 18. Native sub-issues determine the epic label

Date: 2026-07-08

## Status

Accepted

## Context

This repo's issue-first workflow already treats specs as epic issues and plan
slices as sub-issues, using GitHub's native sub-issues feature (queried via
GraphQL `subIssuesSummary`, linked via the `addSubIssue` mutation) rather than
a body-text list. A separate `epic-auto-close` GitHub Action (issue #987)
closes the parent epic once every one of its native sub-issues closes —
GitHub's own tracking only ever computes a completion percentage, it never
closes the parent as a side effect.

None of that wiring defines when an issue should carry the `epic` **label**.
An audit of the repo's open issues needed a concrete, repeatable rule to
apply it consistently. Two candidate criteria surfaced:

1. **Prose shape** — label an issue `epic` if its body reads like one: an
   Architecture Specification, Acceptance Criteria, an Ambiguity Log, or
   similar spec-shaped sections, as produced by `/specs`.
2. **Native sub-issue linkage** — label an issue `epic` only once it has at
   least one sub-issue linked through the native GitHub relationship
   (`subIssuesSummary.total > 0`).

Applying both during the audit surfaced a concrete divergence: #1020 and
#1042 have sub-issues linked via `addSubIssue` and clearly belong under
`epic`. #1018 is a large `/specs`-style issue — it has an Architecture
Specification, Acceptance Criteria, and an Ambiguity Log, and reads exactly
like an epic — but it has not yet been sliced into sub-issues
(`subIssuesSummary.total` is `0`). Labeling it `epic` on prose shape alone
would produce a label that a later `gh api graphql` re-audit could not
reproduce from the same rule, and that stays accurate only as long as
someone remembers to re-check it by eye.

Prose shape is necessary but not sufficient — a `/specs` issue is written as
a future epic, not yet an operational one. The native sub-issue relationship
is the point at which an issue actually starts behaving like an epic: it has
children whose completion `epic-auto-close` will track, and whose count
`subIssuesSummary` can report on demand.

## Decision

An issue gets the `epic` label if and only if it has at least one linked
native GitHub sub-issue (`subIssuesSummary.total > 0`). Prose content — even
unambiguous `/specs`-style epic shape (Architecture Specification,
Acceptance Criteria, Ambiguity Log) — is not sufficient on its own.

Concretely:

- Apply the label the same moment sub-issues are linked (typically when
  `/issues-from-plan` or `/issues-from-assessment` runs `addSubIssue` against
  the parent), not earlier.
- A `/specs` issue with zero linked sub-issues stays unlabeled until it is
  actually sliced. It does not retroactively need the label just because its
  body is epic-shaped — see #1018 as the reference case.
- Re-auditing the label is a single GraphQL query per issue
  (`subIssuesSummary { total }`), the same query used to apply it, so the
  label can be verified mechanically rather than by re-reading issue bodies.

## Consequences

- The `epic` label stays a reliable filter: `is:open label:epic` will always
  match issues that actually have tracked children, matching what
  `epic-auto-close` acts on.
- Re-auditing the label after any bulk issue review is cheap and
  deterministic — one batched GraphQL query, not a manual re-read of every
  issue body.
- A spec issue that is clearly headed toward becoming an epic (like #1018)
  goes unlabeled for a period between being filed and being sliced into
  sub-issues. Anyone scanning `label:epic` for "epics in flight, including
  ones not yet sliced" needs a second signal (e.g. the `/specs` issue
  template) to catch these — this ADR does not introduce one.
- If a future workflow wants to distinguish "planned epic, not yet sliced"
  from "no epic intent at all," that is a new label or convention layered on
  top of this one, not a reason to loosen this criterion.
