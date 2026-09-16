# The spec glossary

Loaded on demand by [`../SKILL.md`](../SKILL.md) when domain terms need
capturing. The persisted shape lives in
[`persistence.md`](persistence.md)'s body template.

## Why a glossary at spec time

`ubiquitous-language` enforces terminology consistency, but only once terms are
already in use. Nothing captured, at spec time, which domain terms were still
undefined — so a term nobody had agreed on reached `/plan` looking like an
ordinary word, and the disagreement surfaced later as a naming argument or, far
worse, as two components meaning different things by "order".

## When terms are captured

**While drafting Intent and Acceptance Criteria**, not as a separate pass. Terms
surface naturally there; a separate pass would re-read the same artifacts to
find the same words.

## The two statuses

| Status | Meaning |
|---|---|
| `verified` | A **human** confirmed this definition during the collaboration loop |
| `unverified` | The agent inferred it, or nobody has confirmed it yet |

There is no third state. "Proposed" or "disputed" would need their own routing
rules and have no consumer.

**`verified` requires a human.** An agent confirming its own inferred definition
is exactly the "looks thorough while encoding a happy-path assumption" failure
the Ambiguity Resolution Protocol exists to prevent — if an agent could
self-verify, the status would carry no information at all.

## Routing, and what it does not do

A term still `unverified` at the end of the loop is a gap finding and enters the
existing Ambiguity Resolution Protocol, classified `inferable` (the definition
follows unambiguously from codebase or domain convention) or
`requires-stakeholder-input` (two reasonable people would define it
differently).

**An unverified term does not block the Consistency Gate by itself.** It blocks
only if the protocol classifies it as blocking. Blocking on every unverified
term would make specs painful enough that people route around `/specs` entirely
— which costs more than the ambiguity it would catch.

**When a human later confirms a term**, its row flips to `verified` **and** its
Ambiguity Log entry is resolved. A term cannot be `verified` while its own
finding stays open; leaving the entry dangling would make the log's audit trail
lie about what is still outstanding.

## Downstream

The glossary is persisted inside the spec artifact, so `ubiquitous-language` and
`domain-review` consume it by reading the spec they already locate. No separate
file, no index, no new lookup mechanism — and no new gate, severity scheme, or
confidence score.
