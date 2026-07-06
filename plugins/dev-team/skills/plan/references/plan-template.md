# Plan File Template

Use this structure when writing the plan file (step 3 of `SKILL.md`).

````markdown
# Plan: <Task Title>

**Created**: <date>
**Branch**: <current branch>
**Status**: draft
**Gherkin persistence**: <destination dir | plan-file-only | custom: <path>>
<!-- Recorded once at plan creation (detected convention, operator answer, or
     headless default). Re-runs honor this line without re-prompting; editing
     it is the supported way to change the decision. -->
**Scope enforcement**: <freeze | none> <!-- OPTIONAL. Omit or set `none` for
     today's behavior. `freeze` opts every slice declaring `**Files:**` into
     `/build` auto-freezing its worktree to the declared scope at dispatch
     (see Slice 2's `**Files:**` line below) — declared Files alone, without
     this line, only feeds `plan_waves.py`'s scope-mismatch warnings, never
     freeze. -->

## Goal

<One paragraph describing what this plan achieves and why.>

## Acceptance Criteria

- [ ] <Criterion 1 — observable, testable>
- [ ] <Criterion 2>
- [ ] <Criterion 3>

## Slices

A slice is a vertically deliverable increment. Each slice carries the Gherkin
scenario(s) that define its behavior, followed by the TDD steps that satisfy them.
Steps are numbered `<slice>.<step>` (1.1, 1.2, 2.1, …).

### Slice 1: <Slice Name>

**Depends-on:** none
**Files:** `path/to/file.ts`, `path/to/file.test.ts`

**Behavior:**

```gherkin
Feature: <feature name>

  Scenario: <happy path>
    Given <precondition>
    When <action>
    Then <observable outcome>

  Scenario: <negative / edge / error case>
    Given <precondition>
    When <action>
    Then <observable outcome>
```

**Steps:**

#### Step 1.1: <Description>

**Complexity**: <trivial | standard | complex>
**IMPLEMENT**: Write <the one behavior this step adds>
**TEST**: Write test covering <scenario / behavior>; full suite green
**REFACTOR**: <What to clean up — runs every cycle; never "skip">
**Files**: `path/to/file.ts`, `path/to/file.test.ts`
**Commit**: `<draft commit message>`

#### Step 1.2: <Description>

...

### Slice 2: <Slice Name>

**Depends-on:** 1
**Files:** `path/to/other.ts`
**Invariants:** `<runnable shell command>`, `<another command>`
**Rollback point:** slice-start
<!-- All three of Files/Invariants/Rollback point are OPTIONAL — a slice
     that omits them parses, reviews, and builds exactly as today.
     - **Files**: declared write scope for the slice (glob patterns
       accepted, e.g. `src/auth/**`). Feeds `plan_waves.py`'s
       declared-vs-inferred scope-mismatch check; only auto-freezes when
       the plan sets `**Scope enforcement:** freeze` above.
     - **Invariants**: runnable shell commands (exit 0 = green) that must
       stay green *beyond* this slice's own new acceptance tests — run by
       `/build`'s slice gate after the slice's own suite passes.
     - **Rollback point**: the commit boundary to revert to if the slice
       dead-ends — `slice-start` (default: HEAD at slice dispatch),
       `wave-start`, `plan-start`, or an explicit ref. `/build` resolves it
       to a concrete SHA at dispatch and records it. -->

**Behavior:**

```gherkin
...
```

**Steps:**

#### Step 2.1: <Description>

...

## Parallelization

Each slice declares `Depends-on` (slice ids it must follow, or `none`). The build
**waves** are derived from those declarations by `scripts/plan_waves.py` — do not
hand-maintain them. Independent slices in the same wave can be built concurrently
(`/build` dispatches them to isolated worktrees).

```mermaid
graph TD
  S1[Slice 1] --> S2[Slice 2]
```

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

If `scripts/plan_waves.py` reports a cycle, a missing `Depends-on`, an unknown reference,
or a **same-wave file collision** (two slices in one wave declaring the same file —
now computed conservatively over each slice's declared **and** inferred files),
fix the plan before the human gate — those break safe concurrent delivery.

A `scope_mismatches` entry (a slice's declared `Files` disagreeing with the union
of its steps' `**Files**:` lines) is **fix-or-acknowledge, not fix-before-gate**:
shown as a warning at the human gate (step 6), and recorded in `## Risks & Open
Questions` if the author proceeds without reconciling it.

## Complexity Classification

Each step must include a complexity rating that controls review depth during `/build`:

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Single-file rename, config change, typo fix, documentation-only | Skip inline review; covered by final `/code-review` |
| `standard` | New function, test, module, or behavioral change within existing patterns | Spec-compliance + relevant quality agents |
| `complex` | Architectural change, security-sensitive, cross-cutting concern, new abstraction | Full agent suite including opus-tier agents |

When in doubt, classify up (standard rather than trivial, complex rather than standard).

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Type check passes (if applicable)
- [ ] Linter passes
- [ ] `/code-review` passes
- [ ] Documentation updated (if applicable)

## Skipped (low value)

Findings classified `LOW_VALUE` — feasible but no signal (no branching logic, no
observable outcome, coverage already provided by a higher-layer test). These are
**skipped, not deferred**: they never appear in a slice or a work stream. Omit this
section when there are none.

| Finding | Rationale (one line) |
|---|---|
| <finding> | <why it delivers no signal> |

## Risks & Open Questions

- <Risk or question, with mitigation or who should answer>

## Build Progress

This section is the machine-parseable recovery handle. `/build` updates checkboxes here via Edit tool so progress survives a `/clear` or session restart. `/continue` reads this section to determine the resume point.

### Slices (grouped by wave)

#### Wave 1
- [ ] Slice 1: <title>
  - [ ] Step 1.1: <title>
  - [ ] Step 1.2: <title>

#### Wave 2
- [ ] Slice 2: <title>
  - [ ] Step 2.1: <title>
````
