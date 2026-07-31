---
name: test-health
description: Project-wide test-strategy audit — derive the suite's shape and shape-vs-architecture fit, map coverage to the Agile Testing Quadrants, roll up coverage + mutation health, flag flaky tests and automation maturity, and produce an ordered improvement plan. Delegates CD-determinism + pipeline assessment to cd-test-architecture. Use when the user says "audit our tests", "how healthy is our test suite", "test strategy review", or runs /test-health. Advisory — writes a report, does not edit.
role: worker
user-invocable: true
argument-hint: "[--path <dir>] [--pdf]"
---

# Test Health

Role: worker. This command produces a strategic test-health report — it does
not edit code or tests; fixes go to `/apply-fixes`, refactors to `/plan` /
`/build`.

## Overview

An **advisory, project-wide** skill: it produces the *strategic-health* view of a test suite that a team needs periodically — the suite's **shape** vs. its architecture, **Agile Testing Quadrant** coverage, **coverage + mutation** health rolled up to ROI, flaky-test management, and **automation maturity** — then an ordered improvement plan. It complements, and does not duplicate, `cd-test-architecture`: that skill owns the CD-determinism + pipeline-placement assessment, which this skill **delegates to** rather than re-deriving.

Grounded in: `knowledge/testing-quadrants.md`, `knowledge/test-pyramid.md` (shapes + shape↔architecture fit), `knowledge/test-automation-maturity.md`, `knowledge/test-smells.md` (project smells / flakiness), and `knowledge/test-automation-principles.md` (the goals/principles that frame *why* a project smell hurts — e.g. Developers Not Writing Tests, Frequent Debugging → lost Defect Localization). It calls the `cd-test-architecture`, `/test-design`, and `mutation-testing` skills and folds their results into the strategic rollup.

## Constraints

- **Advisory only.** Write a report; do not edit code or tests. Hand fixes to `/apply-fixes`, refactors to `/plan` / `/build`.
- **Delegate, don't re-derive.** The architecture/pipeline section comes from `cd-test-architecture` — summarize its output, never restate or contradict its CD-determinism findings.
- **Strategic altitude.** This is a suite-level diagnostic. Per-file findings belong to `test-review` / `test-smell-review`; per-unit design belongs to `test-design-advisor`. Point to them; don't reproduce them.
- **No scoring reinvention.** Quantitative quality scoring and per-file design findings come from `/test-design` (Farley Score + test-review / test-smell-review) — consume them; summarize the themes and link to its report, don't re-derive or reproduce the per-file table.
- **Be concise.** One report; findings as tables, each item mapped to a concrete next move. No restating the knowledge files — cite them.

## Parse Arguments

Target repo/subtree path (default: cwd). Detect the test runner, coverage tool, and CI config from manifests and `.github/`/`.gitlab-ci.yml`/etc.

## Steps

### 1. Trivial-suite short-circuit

If the suite is tiny (few test files), shows no shape pathology, and follows clear conventions, **stop here** and return a one-paragraph summary ("suite is small and healthy; nothing structural to fix; revisit when it grows") instead of the full diagnostic.

### 2. Derive the test shape + architecture fit

Inventory tests by layer (unit / integration / component / contract / E2E). Derive the actual **shape** and compare it to the shape the architecture *should* produce, using the *Other shapes* + *Shape ↔ architecture fit* tables in `test-pyramid.md`. Report the mismatch (e.g. tall pyramid over thin-glue code, or ice-cream cone), not the silhouette alone.

**Graph-assisted inventory.** Prefer CodeGraph/Repowise over raw `Grep` for mapping test files to the architecture layers they exercise — see [`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md) for tool selection and the fallback contract.

### 3. Quadrant coverage

Classify coverage across the four quadrants (`testing-quadrants.md`) as strong / thin / empty, and for each gap name the **business impact** of leaving it empty (e.g. empty Q3 → no human catches confusing flows; empty Q4 → non-functional failures reach prod).

**Gherkin scenarios as a Q2 signal.** Run `python3
${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py` (the same detection
`/gherkin-derive` and `/plan` already use) to locate the project's
`.feature` directory. When a directory is reported, enumerate its scenario
titles (`Scenario:` / `Scenario Outline:` lines) and count them as an
additional Q2 (business-facing) signal alongside any existing
business-facing tests — a documented scenario counts toward Q2 strength
whether or not it is yet bound to a runnable test; binding status feeds
Step 7's gap classification, not this step's strong/thin/empty call. When
`detect_bdd_convention.py` reports no signal, Q2's classification is
unaffected — it falls back to the existing business-facing-test-based
signal only, with no error and no placeholder text.

### 4. Delegate architecture + pipeline

Invoke `cd-test-architecture` on the target. Summarize its findings (which tests can't run in a clean pre-merge gate, target architecture, migration path) in one section — **do not re-derive**.

### 5. Test-design + mutation health (ROI)

Invoke `/test-design` on the target, passing the same scope this run was
invoked with — the dispatch must be explicit so a subtree audit never
inherits a whole-repo Farley Score:

- `/test-health --path <dir>` → dispatch `/test-design --path <dir>`.
- `/test-health` (unscoped) → dispatch `/test-design` with no scope flag.

Consume its results: the scope-labelled **Farley Score** (`(all tests)` when
unscoped, `(under <dir>)` when passing `--path`, or the empty-scope note
`no in-scope test files` when the in-scope set is empty), the dominant
`test-review` / `test-smell-review` themes (weak assertions,
non-determinism, fixture/structure smells, testability blockers), and the
advisor's testability verdicts. Then invoke `mutation-testing` on the
**critical-logic** modules only (not the whole repo — that's the ROI
framing). Roll both up: where is coverage high but mutation-weak
(assertions that don't catch bugs)? Where do test-design smells
concentrate? Where is critical logic under-covered? Prioritize by risk,
not by raw %. Both feed the ordered plan (Step 7) — summarize the themes
and link to the `/test-design` report for per-file detail; do not
reproduce it.

### 6. Flaky-test + automation maturity

Flag flakiness signals (`test-smells.md` project/behavior smells: order-dependence, unstubbed clock/RNG, real I/O at unit level) and a management recommendation (quarantine + fix, don't `retry`). Assess automation maturity with `test-automation-maturity.md`: report the rung and the single-point-of-change metric, scaled by suite size (graduated thresholds).

### 7. Classify gaps + recommend removals

Classify every gap the audit surfaces into one of three **actionable** classes, plus one **non-actionable** class reserved for behavior that doesn't exist yet (see Gherkin gaps below), so the improvement plan (Step 8) only ever plans work that delivers signal:

| Class | Meaning | Action |
| --- | --- | --- |
| `NO_REFACTOR` | A test can be added against the code as it stands | Plan it |
| `REFACTOR_REQUIRED` | Production code needs a testability change before a meaningful test is possible | Plan the production-code change first |
| `LOW_VALUE` | Technically feasible but delivers no signal — **skip, never plan** | List for removal, not for work |
| `NOT_IMPLEMENTED` | The scenario's behavior doesn't exist in production code at all — not a testability gap | Feature-gap call-out for the product backlog, never a test-improve target |

A finding is `LOW_VALUE` only when **all three** hold:

1. **No branching logic** — trivial getters/setters, pass-through constructors, framework boilerplate, or auto-generated code.
2. **No observable outcome** — the only assertion possible is that a mock was called.
3. **Coverage already provided** — a higher-layer test already exercises the same path.

For existing tests that meet all three criteria, emit a **Recommended removals** table: the redundant test, the higher-layer test that already covers it, and a one-line rationale. These are the suite's `LOW_VALUE` tests — keeping them costs maintenance for no defect-localization gain.

**Gherkin gaps (tag `gherkin-gap`).** A documented Gherkin scenario surfaced
in Step 3 with no bound step-definition (`bdd-runner` mode) or cited xUnit
test (`xunit-with-annotations` mode) classifies `NO_REFACTOR` when its
behavior already exists in production code and a test can be added against
it as-is. It classifies `REFACTOR_REQUIRED` when the behavior exists but
needs a testability seam first (interface extraction, DI point, virtual
method promotion) — the same kind of seam-only change `/test-improve`'s
Phase 7 is scoped to perform.

**When the scenario's behavior doesn't exist yet in production code at
all, classify it `NOT_IMPLEMENTED` instead — neither `NO_REFACTOR` nor
`REFACTOR_REQUIRED` applies.** Phase 7 accepts seam introductions only —
implementing new behavior is explicitly out of its scope — so routing a
`NOT_IMPLEMENTED` scenario through `REFACTOR_REQUIRED` would dead-end there
with no seam to introduce. Tag it `gherkin-gap` as usual, mark it
`NOT_IMPLEMENTED` in the Gap classification table's Class column, and carry
it into Step 8's ordered improvement plan as a feature-gap call-out for the
product backlog — never as a refactor-for-testability item, and never
written as a Phase-5 Story or deferred to Phase 7 by `/test-improve`.

**Discriminator: judge existence against the `Then` outcome, not the
`Given`/`When` setup.** If no production code path can produce the asserted
outcome, the behavior does not exist even when the surrounding
`Given`/`When` code does. Split a partially-implemented Scenario Outline
per example row — some rows can be `REFACTOR_REQUIRED` while others are
`NOT_IMPLEMENTED`. When existence is genuinely ambiguous, default to
`NOT_IMPLEMENTED`: an over-classified feature gap is inert and visible in
the report, whereas an over-classified `REFACTOR_REQUIRED` dead-ends at
Phase 7 with no seam to introduce.

Use this exact wording for the finding's Meaning/Action for the
`NO_REFACTOR`/`REFACTOR_REQUIRED` cases:

> **Meaning:** "documented Gherkin scenario '<title>' has no bound step-definition or cited test yet." **Action:** "implement the missing binding/test before treating this area as low-risk."

For the `NOT_IMPLEMENTED` case, use this wording instead — it must never
tell the operator to add a binding/test, since there is no behavior yet to
bind one to:

> **Meaning:** "documented Gherkin scenario '<title>' describes behavior that does not exist in production code yet." **Action:** "implement the behavior via the product backlog; the binding/test follows once it exists — this is not a /test-improve target."

A Gherkin gap can never qualify as `LOW_VALUE`: a documented scenario has an
observable outcome by construction (its own `Then` steps assert one), so it
always fails criterion 2 above. `NOT_IMPLEMENTED` and `LOW_VALUE` are
mutually exclusive for the same reason `LOW_VALUE` never applies to a
Gherkin gap.

### 8. Ordered improvement plan

Produce a risk-ordered, incremental plan — each item a concrete next move (which layer to add, which shape to correct, which quadrant to fill, which abstraction to extract, which weak-assertion or smell cluster to fix), driven by the test-design themes and mutation hotspots from Step 5. `LOW_VALUE` findings never appear here — they live only in the Recommended removals table.

`NOT_IMPLEMENTED` findings never appear here either — no test-improvement move can close a scenario whose behavior doesn't exist yet, so it can never satisfy "a concrete next move." List them instead in a dedicated **Feature gaps (product backlog)** call-out beneath the ordered plan, and never count them in the risk ordering.

### 9. Report

Write `.dev-team-reports/test-health-<date>.md`.

When `--pdf` was passed, render that report to a sibling PDF per
`knowledge/report-pdf-integration.md` (additive; non-fatal if no engine):

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/test-health-<date>.md
```

## Output

For the header block and closing Provenance section, follow
`knowledge/report-template.md`; the sections below are this skill's own
body.

```markdown
# Test Health

**Date**: <ISO 8601>
**Target**: <repo>
**Tool versions**: <coverage tool, mutation tool versions — or _Not applicable — <reason>._>
**Scope**: <full repo | --path <dir>>

## Test Health — <repo> (<date>)

**Shape**: <derived> · **Expected for this architecture**: <expected> · **Fit**: <match|mismatch + why>

### Quadrant coverage
| Quadrant | Status | Gap impact |

### Architecture & pipeline (via cd-test-architecture)
<one-paragraph summary + link to its report>

### Test-design & mutation health (via /test-design + mutation-testing)
<Farley Score — render the scope-labelled value from `/test-design`
verbatim (`(all tests)` when this run is unscoped, `(under <dir>)` when
`--path` is set), or the literal `no in-scope test files` when the in-scope
set was empty; do not synthesize a number. Top test-design themes ·
mutation ROI hotspots · under-covered critical logic>

### Gap classification
| Gap | Class (NO_REFACTOR / REFACTOR_REQUIRED / LOW_VALUE / NOT_IMPLEMENTED) | Note |

### Recommended removals (LOW_VALUE existing tests)
| Test to remove | Covering test | Rationale |

### Flakiness & automation maturity
<flaky signals + management rec · maturity rung · single-point-of-change metric>

### Improvement plan (ordered)
1. <highest-leverage move> …

### Feature gaps (product backlog)
<NOT_IMPLEMENTED gherkin-gap findings only — never a numbered plan item;
omit this section entirely when there are none>
- <gap> — <one-line rationale for why the behavior doesn't exist yet>…

## Provenance

- Repository: `<repo path>`
- Branch / SHA: `<branch>` / `<sha>`
- Run parameters: `<flags — e.g. --path <dir>>`
- `dev-team` plugin version: `<plugin_version>`
```

## Integration

- **Front door** for periodic test-strategy review; the unified entry point that runs `cd-test-architecture` + `/test-design` + `mutation-testing` and rolls their results into one strategic view.
- `/test-design` runs inside this flow (Step 5) and also stands alone for a focused per-file review. For *forward* design of a specific module, use `test-design-advisor`. This skill is the strategic rollup that consumes their output.
