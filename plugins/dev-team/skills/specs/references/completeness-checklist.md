# Completeness checklist

Loaded on demand by [`../SKILL.md`](../SKILL.md)'s completeness sweep, which
runs after the critique loop and before the Cross-Artifact Consistency Gate.

## What this checklist is for

`plan-review-acceptance` already checks whether each criterion a spec
*contains* is complete — boundaries at zero/one/many, an error path per happy
path, negative criteria, illegal state transitions. This checklist answers a
different question.

A spec that never mentions deletion produces **no criterion** for that agent to
find incomplete. The omission is not a weak criterion; it is the absence of one,
and absence is invisible to every per-criterion check. The same holds for
authorization, audit, and error handling when a spec simply never raises them.

**This checklist never grades a criterion that exists.** It reports cells with
no corresponding criterion at all. Judging the quality of one that is present
stays `plan-review-acceptance`'s scope, and that boundary is deliberate — the
two agents answer "is there a criterion here at all?" and "is this criterion
complete?" respectively.

## This checklist is fixed

One shipped list, not extensible per project. A per-project override is a
hypothetical requirement with no current caller; building it now would be
speculative design.

## CRUD, per named entity

For every entity the spec names, check all four:

| Operation | Ask |
|---|---|
| **Create** | How does one come into existence? Who may create it? What makes a creation invalid? |
| **Read** | Who may see it? Is any field restricted? What does a miss return? |
| **Update** | Which fields are mutable? What transitions are illegal? Is concurrent update addressed? |
| **Delete** | Can one be deleted? Soft or hard? What happens to things referencing it? |

A spec may legitimately have no answer for a cell — a read-only projection has
no create, update, or delete. That is an `inferable` finding **with its
rationale recorded**, never a silently dropped cell.

## Cross-cutting concerns

Check the spec as a whole against all four:

| Concern | Ask |
|---|---|
| **Authentication** | Who is the actor, and how is that established? |
| **Authorization** | Which actors may do which of the operations above? |
| **Audit / logging** | What must be recorded, and is any of it required rather than nice to have? |
| **Error handling** | What does the system do when a dependency fails, not just when input is invalid? |

## Domain-implied surfaces

Beyond the fixed cells above, check the administrative and non-functional
surfaces the spec's own domain implies — an operator's view, a retention or
export obligation, a throughput or latency expectation the domain takes for
granted. These are domain-specific by nature, so they are a prompt to look, not
a fixed list to tick.

## Reporting

**Say which entities were enumerated.** Extracting entities from prose is a
model step, not a parser's; showing the list is what lets a human catch one
that was missed. Without it, a missed entity is indistinguishable from an
entity with no findings.

**Group findings by entity**, and separate cells dispositionable in one answer
("nothing in this spec is ever deleted — confirm intentional?") from those
needing individual judgment. A flat dump of CRUD × every entity plus four
concerns is a wall of questions that invites rubber-stamping, which defeats the
sweep.

## Routing

Each unaddressed cell becomes an Ambiguity Log entry, classified `inferable`
(with rationale) or `requires-stakeholder-input`. **The sweep is not itself a
gate** — it blocks only through the existing Ambiguity Resolution Protocol,
exactly as every other finding does. No new gate, no new severity scheme, no
confidence score.
