# ADR Decision Criteria

Reference for the `adr-author` agent and any agent that should proactively suggest recording a decision. Use this to answer "should we write an ADR for this?"

---

## Core Definition

An ADR documents **a decision on a matter where "why?" would not be obvious** — especially for decisions that are **hard to change later**.

Two tests, both must apply:

1. **Obscure rationale** — a future engineer reading the code or config would not understand why this choice was made without outside context.
2. **High reversal cost** — undoing or changing the decision would require significant effort, coordination, or risk (data migration, API breakage, cross-team signaling, rewrite).

If only one test applies, the decision may not need an ADR.

---

## Signals That Warrant an ADR

| Signal | Why it qualifies |
|--------|-----------------|
| Technology choice (library, framework, database, language) | Alternatives are plausible; switching is expensive |
| Architectural pattern (event sourcing vs CRUD, monolith vs microservice, sync vs async) | Pattern permeates the codebase; re-patterning is a large effort |
| Breaking change to a public API or data format | External consumers absorb the cost of reversal |
| Security-significant decision (auth strategy, encryption approach, trust boundary) | Wrong choices have compounding risk; correctness is non-obvious |
| Cross-team contract (shared schema, service boundary, event contract) | Changes require coordination; silent drift causes incidents |
| Trade-off where the rejected option is reasonable (consistency vs availability, speed vs correctness) | The choice will be re-litigated without a record of why the other option was rejected |
| Deviation from an established project convention | Future readers will see the divergence and wonder if it's a mistake |

---

## Signals That Do NOT Warrant an ADR

| Signal | Why it does not qualify |
|--------|------------------------|
| Bug fix | No architectural decision involved |
| Style or formatting choice | Easily changed; obvious best practice or enforced by tooling |
| Obvious best practice (use HTTPS, validate input) | The "why?" is self-evident |
| Implementation detail easily replaced | Low reversal cost |
| Dependency version bump (unless major with breaking changes) | Routine maintenance, not a decision |
| Behavior-preserving refactor | No functional consequence |

---

## Proactive Suggestion Triggers

Suggest an ADR when you observe any of the following during review or implementation:

- A `TODO` or comment explaining *why* a technology or approach was chosen
- A design doc or PR description that records a significant trade-off but has no corresponding ADR
- A pattern in the codebase that deviates from stated conventions without explanation
- A migration or data format change that will be permanent
- A choice that was debated (evident from PR comments or discussion) but not recorded

---

## Relationship to Other Documents

- **Design doc** — explores options before a decision is made. An ADR records the outcome after the decision is made. They complement each other: design doc → decision → ADR.
- **CLAUDE.md / inline comments** — capture *what* the code does or *how* it works. ADRs capture *why* a particular approach was chosen over alternatives.
- **`adr-author` agent** — applies this framework and writes the ADR prose. This file is the criteria; that agent is the author.
- **`adr-tools` skill** — handles CLI mechanics (`adr new`, `adr link`, TOC regeneration). Use after the author has drafted the prose.
