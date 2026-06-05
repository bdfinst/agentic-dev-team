---
name: test-health
description: Project-wide test-strategy audit — derive the suite's shape and shape-vs-architecture fit, map coverage to the Agile Testing Quadrants, roll up coverage + mutation health, flag flaky tests and automation maturity, and produce an ordered improvement plan. Delegates CD-determinism + pipeline assessment to cd-test-architecture. Use when the user says "audit our tests", "how healthy is our test suite", "test strategy review", or runs /test-health. Advisory — writes a report, does not edit.
role: worker
user-invocable: true
---

# Test Health

## Overview

An **advisory, project-wide** skill: it produces the *strategic-health* view of a test suite that a team needs periodically — the suite's **shape** vs. its architecture, **Agile Testing Quadrant** coverage, **coverage + mutation** health rolled up to ROI, flaky-test management, and **automation maturity** — then an ordered improvement plan. It complements, and does not duplicate, `cd-test-architecture`: that skill owns the CD-determinism + pipeline-placement assessment, which this skill **delegates to** rather than re-deriving.

Grounded in: `knowledge/testing-quadrants.md`, `knowledge/test-pyramid.md` (shapes + shape↔architecture fit), `knowledge/test-automation-maturity.md`, `knowledge/test-smells.md` (project smells / flakiness). It calls the `cd-test-architecture`, `test-design-reviewer`, and `mutation-testing` skills.

## Constraints

- **Advisory only.** Write a report; do not edit code or tests. Hand fixes to `/apply-fixes`, refactors to `/plan` / `/build`.
- **Delegate, don't re-derive.** The architecture/pipeline section comes from `cd-test-architecture` — summarize its output, never restate or contradict its CD-determinism findings.
- **Strategic altitude.** This is a suite-level diagnostic. Per-file findings belong to `test-review` / `test-smell-review`; per-unit design belongs to `test-design-advisor`. Point to them; don't reproduce them.
- **No scoring reinvention.** Quantitative quality scoring comes from `test-design-reviewer` (Farley Score) — consume it.
- **Be concise.** One report; findings as tables, each item mapped to a concrete next move. No restating the knowledge files — cite them.

## Parse Arguments

Target repo/subtree path (default: cwd). Detect the test runner, coverage tool, and CI config from manifests and `.github/`/`.gitlab-ci.yml`/etc.

## Steps

### 1. Pain-point calibration (non-blocking)

In the first response, ask **one** optional question — "What hurts most about testing here right now (slow suite / flaky CI / fear of changing code / low confidence / something else)?" — then **continue the audit immediately** without waiting for an answer. If the user answers later, weight the improvement plan toward it.

### 2. Trivial-suite short-circuit

If the suite is tiny (few test files), shows no shape pathology, and follows clear conventions, **stop here** and return a one-paragraph summary ("suite is small and healthy; nothing structural to fix; revisit when it grows") instead of the full diagnostic.

### 3. Derive the test shape + architecture fit

Inventory tests by layer (unit / integration / component / contract / E2E). Derive the actual **shape** and compare it to the shape the architecture *should* produce, using the *Other shapes* + *Shape ↔ architecture fit* tables in `test-pyramid.md`. Report the mismatch (e.g. tall pyramid over thin-glue code, or ice-cream cone), not the silhouette alone.

### 4. Quadrant coverage

Classify coverage across the four quadrants (`testing-quadrants.md`) as strong / thin / empty, and for each gap name the **business impact** of leaving it empty (e.g. empty Q3 → no human catches confusing flows; empty Q4 → non-functional failures reach prod).

### 5. Delegate architecture + pipeline

Invoke `cd-test-architecture` on the target. Summarize its findings (which tests can't run in a clean pre-merge gate, target architecture, migration path) in one section — **do not re-derive**.

### 6. Coverage + mutation health (ROI)

Invoke `test-design-reviewer` for the Farley-score quality view, and `mutation-testing` on the **critical-logic** modules only (not the whole repo — that's the ROI framing). Roll up: where is coverage high but mutation-weak (assertions that don't catch bugs)? Where is critical logic under-covered? Prioritize by risk, not by raw % .

### 7. Flaky-test + automation maturity

Flag flakiness signals (`test-smells.md` project/behavior smells: order-dependence, unstubbed clock/RNG, real I/O at unit level) and a management recommendation (quarantine + fix, don't `retry`). Assess automation maturity with `test-automation-maturity.md`: report the rung and the single-point-of-change metric, scaled by suite size (graduated thresholds).

### 8. Ordered improvement plan

Produce a risk-ordered, incremental plan — each item a concrete next move (which layer to add, which shape to correct, which quadrant to fill, which abstraction to extract), weighted by the pain point from Step 1.

### 9. Report

Write `reports/test-health-<date>.md`.

## Output

```markdown
## Test Health — <repo> (<date>)

**Shape**: <derived> · **Expected for this architecture**: <expected> · **Fit**: <match|mismatch + why>

### Quadrant coverage
| Quadrant | Status | Gap impact |

### Architecture & pipeline (via cd-test-architecture)
<one-paragraph summary + link to its report>

### Coverage & mutation health
<Farley score · mutation ROI hotspots · under-covered critical logic>

### Flakiness & automation maturity
<flaky signals + management rec · maturity rung · single-point-of-change metric>

### Improvement plan (ordered)
1. <highest-leverage move> …
```

## Integration

- **Front door** for periodic test-strategy review; the unified entry point over `cd-test-architecture` + `test-design-reviewer` + `mutation-testing` without collapsing them.
- For *forward* design of a specific module, use `test-design-advisor`. For per-file findings, run `/test-design` (test-review + test-smell-review). This skill is the strategic rollup above them.
