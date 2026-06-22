# Agile Testing Quadrants

Reference file for the `test-health` skill (project-wide audit) and `test-design-advisor`. The quadrants are a *coverage-completeness* lens — they answer "what **kind** of testing is missing?", orthogonal to `test-pyramid.md`'s "what **layer**?". Use them to find blind spots an all-unit suite can't see.

Source: Brian Marick's testing matrix, popularized by Lisa Crispin & Janet Gregory, *Agile Testing* / *More Agile Testing*. Language- and stack-agnostic.

Two axes: **business-facing ↔ technology-facing** (what the test speaks to) and **supporting the team ↔ critiquing the product** (does it guide building, or probe the finished thing).

---

## The Four Quadrants

| Q | Facing × Stance | Tests | Mode |
|---|-----------------|-------|------|
| **Q1** | technology · support | unit, component, integration | automated |
| **Q2** | business · support | functional / acceptance, story tests, BDD examples, prototypes | automated + manual |
| **Q3** | business · critique | exploratory, usability, UAT, alpha/beta | manual |
| **Q4** | technology · critique | performance, load, security, resilience, the "-ilities" | tool-driven |

Q1+Q2 **guide development** (write them first — they're specifications). Q3+Q4 **probe the built product** for what specifications miss.

---

## Reading coverage against the quadrants

For each quadrant, classify the suite as **strong / thin / empty**, then name the business impact of a gap:

| Quadrant weak/empty | What slips through | How to strengthen |
|---------------------|--------------------|-------------------|
| **Q1 thin** | logic/wiring regressions | push checks down the pyramid (`test-pyramid.md`) |
| **Q2 empty** | "built the wrong thing" — no shared definition of done | add acceptance/BDD examples before coding (see the `specs` skill) |
| **Q3 empty** | bugs only a human notices: confusing flows, broken edge journeys | charter exploratory sessions (`exploratory-testing-field-guide.md`) |
| **Q4 empty** | non-functional failures in prod: slow, insecure, falls over under load | add perf/security/resilience checks; route to `security-review`, `performance-review` |

---

## Anti-pattern: "Q3 as the gate"

Leaning on manual exploratory/UAT (Q3) as the *primary* safety net — instead of Q1/Q2 automation — is the quadrant form of the ice-cream cone (`test-pyramid.md`). Exploratory testing **finds new** problems; it must not be the regression net. If Q3 is the only thing catching regressions, the fix is more Q1/Q2, not more manual testing.

## Boundaries

- A suite need not fill every quadrant equally — weight by risk. A pure library leans Q1/Q4; a user-facing app needs Q2/Q3. Flag *empty* quadrants where the product's risk clearly demands coverage, not arithmetic imbalance.
- This file classifies; it does not score. Quantitative suite scoring stays in `farley-score`.
