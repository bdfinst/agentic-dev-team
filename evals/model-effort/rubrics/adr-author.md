# Rubric: adr-author

A good answer writes a terse ADR to `docs/adr/` that records the context, forces, rejected alternatives, and consequences of a hard-to-reverse decision, numbered and formatted like the existing ADRs, and updates the index. It writes an ADR only when the decision framework holds (non-obvious why and hard to reverse), supersedes rather than deletes earlier decisions, and leaves the status for a human to accept.

## Criteria

- **follows-existing-format**: Each new ADR uses the next free number and the same file naming, heading, and section structure as the existing ADRs in the fixture.
- **context-not-just-outcome**: Each new ADR states the problem and constraints that forced the decision, not only the chosen option.
- **terse**: Each new ADR body stays near or under 200 words and contains no discussion outside the ADR sections.
- **grounded**: Every fact in the ADR (numbers, names, alternatives, and dates in the body) comes from the provided notes or ADRs; nothing is invented. The ADR's own `Date:` line is exempt: the date the notes give or the date the ADR was written both meet this criterion.
- **status-proposed**: Each new ADR's status is Proposed, not Accepted.
