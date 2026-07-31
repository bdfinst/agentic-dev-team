---
name: ubiquitous-language
description: Build or refresh the project's ubiquitous language glossary — one markdown file per business concept at `.plans/domain/<Concept>.md` plus a `_index.md`. Mines grep-based signals (class names, enum values, interface names, domain-event names, BDD scenario names, validator rules) and applies a four-gate filter to keep only genuine business concepts. Optional interactive interview phase to refine definitions and capture behavior (state transitions, invariants, synonyms to avoid). Language-agnostic — works for JS/TS, C#, Java, Python, Go, or any mix. Use whenever the user says "build the glossary", "extract domain terms", "document the ubiquitous language", "what are the domain concepts", or when domain-review surfaces pervasive terminology inconsistency (3+ names for the same concept).
role: worker
user-invocable: true
argument-hint: "[path-to-source-root]"
---

# Ubiquitous Language

Produces a queryable per-concept glossary at `.plans/domain/`. Each concept gets its own file (one-sentence definition, classification, related terms). The glossary feeds `domain-review` as classification ground truth — run this skill before `domain-review` for sharper findings.

**This skill never modifies source files.** It writes only to `.plans/domain/` and `.plans/domain-language-plan.md`.

---

## Announce on start

"Running ubiquitous-language. Gathering domain signals from `$ARGUMENTS` (or cwd if empty). I'll apply a four-gate filter and write one file per approved business concept to `.plans/domain/`. Existing files are append-mostly — previous definitions are preserved."

---

## Phase 1: Gather signals (grep-based, no build required)

Run the colocated gather script. It collects raw candidates; it does not decide what is domain language (that is Phase 3's job).

```bash
python3 .claude/skills/ubiquitous-language/scripts/collect_domain_signals.py "$ARGUMENTS"
```

The script writes to `.plans/raw/domain-language/`:

- `class-names.txt` — PascalCase class/struct/record/interface names from domain and application layers
- `enum-values.txt` — enum declarations with their values
- `domain-events.txt` — type names ending in `Created`, `Updated`, `Submitted`, `Approved`, `Cancelled`, `Rejected`, `Completed`, `Failed`, `Requested`
- `bdd-names.txt` — BDD scenario and step names from `.feature` files (`Given_`, `When_`, `Then_`, `Should_`)
- `validator-rules.txt` — validation rule method names and error messages
- `interface-names.txt` — interface/protocol names from domain and application layers

If the script is unavailable, gather manually using `Grep` with the patterns documented in the script's comments.

**Graph-assisted disambiguation.** Prefer CodeGraph/Repowise over more `Grep` passes to check a candidate term's actual call sites and surrounding context when the raw signal is ambiguous (e.g. a name that could be a technical or a business concept, or two near-duplicate names that might be the same concept under different spellings). This is a supplement to Phase 1's grep-based collection, not a replacement — the collector script output is still the primary candidate source. See [`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md) for tool selection and the fallback contract.

---

## Phase 2: Load existing glossary (if present)

Check for `.plans/domain/_index.md`. If it exists, read the current term list so new terms can be diffed against what already exists. Do not regenerate files for terms already in the glossary unless the definition is missing or clearly wrong.

---

## Phase 3: Apply the four-gate filter

For each candidate term from Phase 1, apply all four gates. Promote only terms that pass all four.

| Gate | Question | Fail condition |
| --- | --- | --- |
| 1. Business concept | Would a domain expert (not a developer) recognize this term as part of the business vocabulary? | Pure technical terms: `Repository`, `Controller`, `Factory`, `Builder`, `Manager`, `Handler`, `Util`, `Helper`, `Config`, `Base`, `Abstract` |
| 2. Non-generic | Does the name carry specific business meaning beyond "thing that does stuff"? | Single-word generics: `Item`, `Data`, `Info`, `Record`, `Object`, `Entity`, `Model` (unless qualified: `OrderLineItem` passes) |
| 3. Appears in ≥2 signal sources | Is the term used in at least two different signal types (e.g., class name AND BDD scenario name)? | Terms that appear only once in a single file with no corroborating evidence |
| 4. Domain expert would recognize it | Would a domain expert, reading only the name, understand roughly what it refers to? | Portmanteaus, internal jargon, or abbreviations not explainable without context |

When in doubt on gate 3, lean toward including the term — false positives are cheap (the user can remove a file); false negatives mean silent glossary gaps.

---

## Phase 4: Write concept files

For each approved term, write (or update) `.plans/domain/<Concept>.md` using this format:

```markdown
---
classification: Aggregate | Entity | Value Object | Domain Event | Domain Service | Policy | Concept
context: <bounded context name, if multi-context repo>
---

# <ConceptName>

<One to two sentence definition in plain business language. Avoid technical terms.>

## Lifecycle / State Transitions
<!-- Optional: fill in during interview phase or when state-transition signals are present -->

## Invariants
<!-- Optional: business rules that must always hold for this concept -->

## Related
<!-- Optional: link to related concepts -->
- [[RelatedConcept]]

## Avoid
<!-- Optional: synonyms the codebase uses that should be consolidated to this term -->
- `PurchaseOrder` (use `Order` instead)

## Sources
<!-- Optional: where this definition came from -->
```

**Append-mostly**: if the file already exists, preserve existing content. Add new sections; do not overwrite human-curated definitions. Update only if the existing definition is blank or contradicted by new evidence.

---

## Phase 5: Regenerate index

After writing all concept files, regenerate `.plans/domain/_index.md`:

```markdown
# Domain Glossary Index

_Last updated: <date>_

## Aggregates
- [Order](Order.md)
- [Payment](Payment.md)

## Entities
- [OrderLine](OrderLine.md)

## Value Objects
- [Money](Money.md)
- [Address](Address.md)

## Domain Events
- [OrderSubmitted](OrderSubmitted.md)

## Domain Services
- [PricingPolicy](PricingPolicy.md)

## Concepts
- [FulfillmentWindow](FulfillmentWindow.md)
```

Preserve human-curated categorical structure if it exists. Only the term links are auto-maintained; section headings and ordering are owned by the human.

---

## Phase 6: Optional interview (interactive sessions only)

If running interactively (not in a non-interactive CI context), ask: "Would you like to interview to refine definitions and capture behavior (state transitions, invariants, synonyms to avoid)? This usually takes 5-10 minutes."

If yes, for each aggregate and entity in the glossary:

1. Ask: "How would you describe `<Term>` to a new team member in one sentence?"
2. Ask: "What states can a `<Term>` be in? What triggers transitions between them?"
3. Ask: "What must always be true about a `<Term>` (invariants)?"
4. Ask: "Are there other names in the codebase for `<Term>` that we should consolidate?"

Update the concept files with answers. Record the interview transcript in `.plans/domain-language-plan.md`.

---

## Output

Write a run summary to `.plans/domain-language-plan.md`:

```markdown
# Domain Language — Run Summary

**Date**: <date>
**Scope**: <path>
**Mode**: grep-fallback | roslyn (if available)

## New concepts written
- `Payment` (Aggregate) — new
- `Money` (Value Object) — new

## Updated concepts
- `Order` (Aggregate) — added Invariants section

## Skipped (already current)
- `Customer` — definition present, no changes

## Filtered out
- `Repository` — gate 1 fail (technical term)
- `Data` — gate 2 fail (generic)

## Open questions
- Is `Transaction` the same concept as `Payment`? Found both in codebase.

## Interview transcript
<!-- appended if Phase 6 ran -->
```

Tell the user: "Glossary written to `.plans/domain/`. Run `/code-review` or `domain-review` for domain boundary analysis using these terms as ground truth."

---

## Integration

- **[Domain Analysis](../domain-analysis/SKILL.md)** — run domain-analysis after this skill to get architectural coupling findings annotated with canonical terms
- **[Domain-Driven Design](../domain-driven-design/SKILL.md)** — use the glossary as input when designing bounded contexts or aggregate boundaries
- **[Specs](../specs/SKILL.md)** — when writing BDD scenarios, pull term names from `.plans/domain/` to ensure scenario language matches the glossary
