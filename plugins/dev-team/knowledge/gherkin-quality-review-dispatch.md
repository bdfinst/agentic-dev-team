# Adversarial Gherkin Quality Review — Dispatch & Aggregation

Shared procedure `/gherkin-derive` (Step 5b) and `/gherkin-public` (Step 4b)
both cite, so the dispatch/aggregation mechanics live in exactly one place
instead of being re-derived near-verbatim in two `SKILL.md` files (issue
#1452). Each calling step states only what's specific to it (when it fires,
what input it passes); everything below is common to both.

## Dispatch

Spawn **two** independent instances of the `gherkin-quality-review` agent as
parallel subagents in a single message, using the `Agent` tool — the same
"Spawn agents as parallel subagents in a single message using the Agent
tool" convention `../skills/code-review/SKILL.md` already documents. Both instances
receive the identical input (the `.feature` file(s) plus each surface's cited
source); neither instance's prompt may contain the other's output — that is
the entire point of running two, and it is a structural property of the
dispatch (one message, two calls, read neither result until both are issued),
not a runtime check.

## Aggregation

The calling skill performs the fold itself — no third agent, mirroring how
`/code-review` aggregates its panel's JSON without a meta-agent. Match each
instance's `gaps`/`balance_issues` entries by the key
**`(feature_file, title)`**:

- A finding present for the same key in **both** instances' output is
  **agreed** — even if the two instances worded the `rationale` differently,
  the same `(feature_file, title)` pair is what makes it agreed.
- A finding present in only **one** instance's output for a given key is
  **single-source (unconfirmed)**.

## Failure handling

If either `Agent` call errors, times out, or returns output that cannot be
parsed as the agent's documented JSON schema:

- Treat that instance's `gaps`/`balance_issues` as empty — never crash the
  skill run over one instance's failure.
- Never promote the absence of a matching finding from the failed instance
  into a false "agreed" classification, and never silently drop the note
  that a failure happened.
- The report must state explicitly: *"one review instance did not return
  usable output — findings below are single-source only."*
- If **both** instances fail, both new report sections print
  `Both review instances failed to return usable output — no Gherkin quality
  findings available for this run.` instead of the two per-finding sections.

## Zero-findings state

Both report sections — "Agreed Gherkin quality findings" and "Single-source
(unconfirmed) Gherkin quality findings" — **always print**, even when a
bucket is empty, so the section's presence in a report is predictable for
tooling/tests, not conditional on there being something to say:

```
Agreed Gherkin quality findings
  None — both instances raised no findings.

Single-source (unconfirmed) Gherkin quality findings
  None — both instances raised no findings.
```

## Scope of this doc

This doc owns only the dispatch/aggregation/failure/zero-findings mechanics.
It does not own: when a calling skill decides to dispatch at all (each
`SKILL.md`'s own Step 5b/4b states its skip conditions), or the report
section wording beyond the two headers above (each `SKILL.md`'s own report
step states the per-finding line format).
