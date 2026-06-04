# Plan: Behavior pre-gates + redundancy check for test-design-advisor (#80)

**Created**: 2026-06-04
**Branch**: feat/test-layer-gates
**Status**: approved
**Spec**: GitHub issue #80 (epic #79). Spec lives in the issue per the repo's specs→issues workflow — not `docs/specs/`.
**Revision**: v2 — incorporates plan-review critic feedback (falsifiable criteria, versioned fixture, output schema, token budgets, sequencing decision).

## Goal

Add behavior **pre-gates** to the `test-design-advisor` skill so it can escalate a behavior to a higher test layer based on *how it can break* — not just the lowest layer that can verify it. Four gates (user-facing dynamic, bug-fix regression, SSR/dynamic-swap delivery chain, visual-output fidelity) run before pyramid placement and escalate **upward only**, plus a Swiss-cheese redundancy check for business-critical behaviors. Delivered as one new progressive-disclosure knowledge file (`test-layer-gates.md`), a thin insertion into the advisor's step sequence, a versioned fixture for verification, and registry wiring. The advisor stays advisory and at unit/module altitude: when a gate mandates application-level E2E architecture, it flags the requirement and defers the harness/pipeline design to `cd-test-architecture`.

## Definitions (resolve critic ambiguities)

- **"business-critical"** — a behavior the input explicitly marks as business-critical (keyword/label in the description) OR, when unmarked, one the advisor flags by asking the user. The redundancy check fires **only** on a positive business-critical determination; it never guesses silently.
- **layer vocabulary** — the gates reuse the advisor's existing labels from `test-pyramid.md` (unit / integration / component / contract / E2E). The gates define **no new taxonomy**. Quadrants/test-shapes (#84) are orthogonal axes and do not collide (see Sequencing risk).
- **Gate-column sentinels** (pyramid-placement output table) — `—` = no gate fired (Step 2 pick stands); `↑<layer>` = gate escalated to `<layer>`; `→ cd-test-architecture` = E2E architecture deferred (advisor flags the seam, does not design the harness).

## Acceptance Criteria

*(Each is structurally checkable — by grep on the markdown, a token count, `/agent-audit`, or a row in the versioned fixture. No criterion describes unobservable runtime.)*

- [ ] **AC1 (ordering)** `SKILL.md` contains a `Step 1b — Behavior pre-gates` heading positioned **between** Step 1 (testability) and Step 2 (pyramid placement); its text states gates escalate **upward only** and contains no instruction that lowers a Step 2 layer assignment. *(grep + read)*
- [ ] **AC2 (fixture)** `evals/fixtures/test-layer-gates.md` exists and lists ≥6 behaviors — {pure fn, user-facing dynamic, browser-found bug fix, unit-found bug fix, SSR swap w/ mutation, visual artifact w/ reference, business-critical single-layer} — each with its **expected gate firing(s)** and **expected layer**. The Step 3 walk-through records actual == expected for every row. *(file + walk-through log in commit)*
- [ ] **AC3 (gate output)** Each fired gate emits, once, a cost trade-off **and** ≥1 amortization strategy. When multiple gates fire, layers are unioned (no duplicate) and reconciliation guidance is given. *(fixture rows + read)*
- [ ] **AC4 (Gate C)** Gate C marks the browser test **required** in both the state-mutation and the structural-only case, and labels the integration test complementary. *(read + fixture)*
- [ ] **AC5 (Gate D, split)** With a reference: text output → approval; visual-fidelity → screenshot; both surface maintenance cost. Without a reference: manual review + suggest creating a reference. *(four checkable clauses)*
- [ ] **AC6 (Gate B negative)** Gate B anchors the regression at the **discovery** layer; when the bug was found at unit level it does **not** escalate to E2E. *(fixture: unit-found bug row)*
- [ ] **AC7 (redundancy)** Fires only on a business-critical determination (per Definitions); output names a second, different-failure-mode layer **and a concrete recommendation**, not just a flag. *(read + fixture)*
- [ ] **AC8 (ambiguity interaction)** When dynamic-ness is ambiguous, the skill text instructs: state the assumption, ask **once per behavior** (batch multiple ambiguities into one prompt), offer a "treat all ambiguous as dynamic" option, and never silently escalate. *(read)*
- [ ] **AC9 (altitude boundary, durable)** `SKILL.md` flags+defers E2E architecture to `cd-test-architecture` (contains the `→ cd-test-architecture` sentinel and a deferral sentence) and contains **no** E2E-harness/pipeline design instructions. Enforced by a Step 3 grep assertion. *(grep)*
- [ ] **AC10 (terminology mapping)** `test-layer-gates.md` contains an explicit cross-reference line mapping its layer labels to `cd-test-architecture.md`'s six test types (pointing at that file's *Terminology Reconciliation* section); `SKILL.md` Constraints restate the altitude boundary. *(grep)*
- [ ] **AC11 (budgets)** `test-layer-gates.md` ≤ 450 tokens (wc-based check); the `Step 1b` insertion in `SKILL.md` ≤ ~150 tokens (thin trigger, detail lives in the knowledge file). *(token count)*
- [ ] **AC12 (wiring)** Registered in `agent-registry.md` (Knowledge Files row, used-by `test-design-advisor`) + `CLAUDE.md` (list + count 18→19) + regenerated `index.json` (not hand-edited); added to the advisor's grounding line (14). *(grep + agent-audit)*
- [ ] **AC13 (audit)** `/agent-audit` passes.

## User-Facing Behavior

```gherkin
Feature: Behavior pre-gates escalate test layer by failure mode

  Background:
    Given test-design-advisor has assessed testability (Step 1)
    And is about to place each behavior on the pyramid (Step 2)

  Scenario: Gate A — user-facing dynamic behavior escalates to E2E
    Given a behavior where the user acts and must see a rendered result
    When the pre-gates run
    Then an E2E/browser test is recommended alongside the lower layers
    And the recommendation states the cost trade-off and at least one amortization strategy

  Scenario: Gate B — bug fix anchors the regression at the discovery layer
    Given the target is a bug fix and the bug was found in the browser
    When the pre-gates run
    Then the regression test is recommended at the E2E layer
    And the spec states the test must fail on the old code and pass on the fix

  Scenario: Gate B negative — bug found at unit level does not escalate
    Given the target is a bug fix and the bug was found while unit-testing
    When the pre-gates run
    Then Gate B anchors the regression at the unit layer
    And does not escalate to E2E

  Scenario: Gate C — SSR swap with a server state mutation requires a browser test
    Given an HTMX/Alpine/Turbo swap driven by a server-side state mutation
    When the pre-gates run
    Then the browser test is marked REQUIRED (not "recommended") for the swap seam
    And the integration test is labelled complementary, not sufficient

  Scenario: Gate C — SSR swap without a state mutation still requires a browser test
    Given a client-side swap with no server state change
    Then the browser test is marked REQUIRED for the structural seam
    And the rationale cites the swap failure modes (wrong hx-target, stale swap, re-init)

  Scenario: Gate D — visual artifact with a reference routes to approval/screenshot
    Given a behavior renders a visual artifact and a reference (mockup/template) exists
    Then approval testing is recommended for text-based output
    And screenshot testing is recommended when CSS/layout fidelity matters
    And both recommendations surface their maintenance cost

  Scenario: Gate D — visual artifact without a reference falls back to manual
    Given a visual artifact but no reference exists
    Then manual visual review is recommended
    And the advisor suggests creating a reference to enable future automation

  Scenario: Redundancy check on a business-critical single-layer behavior
    Given a behavior determined business-critical (per Definitions)
    And it is covered at only one layer after Step 2
    When the redundancy check runs
    Then it flags the single-layer coverage
    And names a second layer with a different failure mode
    And gives a concrete recommendation (e.g., "add a contract test for API-shape drift")

  Scenario: No gate fires for a pure function (gates are silent)
    Given a pure function with no user-facing, regression, swap, or visual aspect
    When the pre-gates run
    Then no gate fires, the Step 2 lowest-layer pick stands, and the Gate cell shows "—"

  Scenario: A gate may only escalate upward, never downgrade
    Given Step 2 placed a behavior at E2E
    When a pre-gate evaluates a lower-layer signal
    Then the recommended layer is never reduced below the pyramid pick

  Scenario: Multiple gates fire — layers unioned, costs listed once
    Given a behavior that is both user-facing dynamic (A) and a browser-found bug fix (B)
    Then the required layers are the union of both gates' outputs with no duplicate
    And each gate's cost/amortization is listed once
    And reconciliation guidance is given when the amortization advice differs

  Scenario: Altitude boundary — E2E architecture defers to cd-test-architecture
    Given a gate mandates an application-level E2E/browser test
    Then the advisor flags the E2E requirement at the seam with "→ cd-test-architecture"
    And defers the pipeline/driver architecture to the cd-test-architecture skill
    And does not itself design the E2E harness

  Scenario: Ambiguous dynamic behavior is surfaced once, not nagged
    Given one or more behaviors whose dynamic-ness is unclear
    Then the advisor states the assumption it would make
    And asks once, batching multiple ambiguities into a single prompt
    And offers a "treat all ambiguous as dynamic" option
    And never silently escalates
```

## TDD note for content artifacts

This change is plugin **knowledge + skill prose**, not executable code, so RED→GREEN→REFACTOR maps to *structural verification*: RED = a concrete failing check (grep for required markers, `wc` token budget, `/agent-audit`, or a fixture row whose actual ≠ expected); GREEN = author content so the check passes; REFACTOR = tighten to house style/budget. The fixture file (`evals/fixtures/test-layer-gates.md`) is the **versioned, reviewer-rerunnable artifact** that makes the behavioral criterion falsifiable — it is authored in Step 1 (before the gates), so the gates are written to satisfy a pre-existing expected-firings table. Full automation of the walk-through (an agent-eval harness for advisory output) is a tracked follow-on, not in scope here.

## Steps

### Step 1: Author the fixture spec + `knowledge/test-layer-gates.md`

**Complexity**: standard
**RED**:

- `evals/fixtures/test-layer-gates.md` absent.
- `knowledge/test-layer-gates.md` absent; grep for `Gate A`…`Gate D` and a `catches/misses` table returns nothing.
- token check not yet satisfiable.
**GREEN**:
- Write `evals/fixtures/test-layer-gates.md` first: a table of ≥6 behaviors (the AC2 set) → expected gate firing(s) → expected layer. This is the falsifiable expected-output spec.
- Write `knowledge/test-layer-gates.md` in house style (no frontmatter; opens `Reference file for the test-design-advisor skill.`; cites the Swiss-cheese model / testing-tutor lineage): four gates as compact decision blocks (trigger → required layer(s) → cost → amortization), the layer **catches/misses** redundancy table, the **business-critical** definition, and the **terminology cross-reference line** to `cd-test-architecture.md`'s six types (AC10).
**REFACTOR**: Trim to **≤ 450 tokens** (`wc`-based check — AC11); decision-table format; pointer not restatement of `test-pyramid.md` / `cd-test-architecture.md`.
**Files**: `plugins/dev-team/evals/fixtures/test-layer-gates.md`, `plugins/dev-team/knowledge/test-layer-gates.md`
**Commit**: `feat(dev-team): add test-layer-gates knowledge file + fixture (#80)`

### Step 2: Integrate the pre-gates into `test-design-advisor` (with output schema)

**Complexity**: complex (behavioral change to a skill; cross-cuts the `cd-test-architecture` altitude boundary)
**RED**: grep of `SKILL.md` finds no `Step 1b`, no grounding-line reference (14), no redundancy check, no `Gate` column; a fixture walk-through does not yet produce the expected firings.
**GREEN**:

- Insert **Step 1b — Behavior pre-gates** between Step 1 and Step 2: Gates A–D as a **reference-forward table** (one line per gate; detail lives in the knowledge file), escalate **upward only**. Keep ≤ ~150 tokens (AC11).
- Define the **output schema**: add a `Gate` column to the pyramid-placement table (`| Behavior | Layer | Gate | Why |`) using the sentinels from Definitions (`—`, `↑<layer>`, `→ cd-test-architecture`); compact one-line-per-fired-gate; for multi-gate, union layers + list each cost once + reconciliation guidance (AC3); redundancy output carries a concrete recommendation (AC7); ambiguity handled by a single batched prompt with a global option (AC8).
- Add the **Swiss-cheese redundancy check** to the tail of Step 2 (business-critical only).
- Add `knowledge/test-layer-gates.md` to the grounding line (14).
- Add **Constraints**: altitude boundary (flag+defer E2E architecture to `cd-test-architecture`, no harness design) and terminology reconciliation.
**REFACTOR**: Preserve concision; verify existing Step 2/3/3b/4 references still resolve after the insertion.
**Files**: `plugins/dev-team/skills/test-design-advisor/SKILL.md`
**Commit**: `feat(dev-team): wire behavior pre-gates + redundancy into test-design-advisor (#80)`

### Step 3: Register, regenerate index, run durable checks, verify against fixture

**Complexity**: standard
**RED**: `/agent-audit` flags the unregistered file; no registry row; `CLAUDE.md` still `(18)`; `index.json` lacks the entry; altitude grep + token checks + fixture walk-through not yet recorded.
**GREEN**:

- Add the **Test Layer Gates** row to `agent-registry.md` (used-by `test-design-advisor`).
- Update `CLAUDE.md` line 50: append `test-layer-gates`, bump `(18)`→`(19)`.
- Regenerate `index.json` via `hooks/lib/build_knowledge_index.py` (or let `hooks/pre-commit-knowledge-index.sh` run) — **not** hand-edited.
- **Durable altitude check (AC9)**: grep asserts `SKILL.md` contains the `→ cd-test-architecture` deferral and no E2E-harness design language.
- **Budget checks (AC11)**: `wc` on the knowledge file (≤450) and the Step 1b block (≤~150).
- **Fixture walk-through (AC2)**: run the advisor against each row of `evals/fixtures/test-layer-gates.md`; record actual vs expected in the commit body. Adjust gate wording and re-run on any mismatch.
- `/agent-audit` → clean.
- File a **follow-on issue**: automated agent-eval fixture for gate firings (infra exists; out of scope here).
**REFACTOR**: If a fixture row misfires, fix the gate text and re-run; reconcile registry rows by **union** if #77 landed meanwhile.
**Files**: `plugins/dev-team/knowledge/agent-registry.md`, `plugins/dev-team/CLAUDE.md`, `plugins/dev-team/knowledge/index.json` (generated)
**Commit**: `feat(dev-team): register test-layer-gates + verify gate firings vs fixture (#80)`

## Complexity Classification

| Step | Rating | Why |
|------|--------|-----|
| 1 | standard | New knowledge file + fixture within an established house-style pattern |
| 2 | complex | Behavioral change to an advisory skill; introduces the altitude boundary, output schema, and terminology reconciliation |
| 3 | standard | Registry wiring + generated index + structural/durable checks; classified up from trivial |

## Pre-PR Quality Gate

- [ ] All structural checks pass (greps, token budgets, altitude grep)
- [ ] Fixture walk-through: actual == expected for every row, recorded in commit
- [ ] `/agent-audit` passes
- [ ] `index.json` regenerated (not hand-edited)
- [ ] `/code-review` passes
- [ ] `agent-registry.md` + `CLAUDE.md` reflect the new file (the doc surface)
- [ ] Follow-on eval-fixture issue filed

## Risks & Open Questions

- **Sequencing vs #84 (decided)** — Epic #79 recommends landing #84 (foundations: quadrants/shapes) before #80. **Decision: proceed with #80 first.** Rationale: `test-layer-gates.md` reuses the advisor's *existing* layer vocabulary from `test-pyramid.md` and defines **no new taxonomy**; quadrants and test-shapes are orthogonal axes, so there is nothing for #84 to reconcile. If #84 lands first, the only touch-up is an optional cross-link from the catches/misses table to its shape file. Added #84 to the coordination set below.
- **No automated behavioral harness** — the fixture walk-through is manual. Mitigation: the **versioned fixture file** makes expected output reviewer-rerunnable (closes the "unfalsifiable" blocker); a follow-on issue tracks automating it via `agent-eval`.
- **Altitude-boundary drift** — Gate A/C push toward E2E (cd-test-architecture territory). Mitigation: the `→ cd-test-architecture` sentinel + the **durable grep check (AC9)** make the boundary enforceable, not just prose.
- **Shared-wiring coordination with #77 and #84** — `agent-registry.md`, `CLAUDE.md`, `index.json` are edited by #73–76 and #84 too. Mitigation: append by union, regenerate `index.json` last, rebase rather than re-add rows (epic #79 coordination note).
- **Token budget** — Mitigation: progressive disclosure (gates in the knowledge file ≤450; Step 1b trigger ≤~150), both enforced in Steps 1/3.

## Plan Review Summary

**Verdict: APPROVED** — 4/4 critics. Design approved on iteration 1; Acceptance, UX, and Strategic approved on iteration 2 after the v2 revision resolved all 6 blockers and folded in the warnings.

**Blockers resolved (v1 → v2):**

- *Acceptance:* unfalsifiable walk-through → versioned `evals/fixtures/test-layer-gates.md` (AC2); runtime-prose criteria → grep/wc-checkable ACs (AC1); orphan ambiguity scenario → AC8; "stated" weasel word → explicit cross-ref line (AC10).
- *UX:* ambiguity nagging → batched single prompt + global option (AC8); multi-gate output composition → union + costs-once + reconciliation + sentinel grammar (AC3, Definitions).

**Warnings folded in:** Gate B negative case (AC6), business-critical definition (Definitions/AC7), token-budget enforcement (AC11), Gate D split (AC5), Gate-column sentinels + empty-cell `—` (Definitions), redundancy actionable recommendation (AC7), Step 1b compactness (AC11), durable altitude grep (AC9), `→ cd-test-architecture` deferral sentinel (AC9), sequencing decision vs #84 (Risks), follow-on eval issue (Step 3).

**Residual observations (non-blocking):** the `~150 token` Step 1b budget is approximate (acceptable — wc gives an objective signal); the gate-firing walk-through remains manual until the tracked follow-on eval automates it.

## Build Progress

### Steps

- [ ] Step 1: Author the fixture spec + `knowledge/test-layer-gates.md`
- [ ] Step 2: Integrate the pre-gates into `test-design-advisor` (with output schema)
- [ ] Step 3: Register, regenerate index, run durable checks, verify against fixture

### Acceptance Criteria

- [ ] AC1 Step 1b positioned between Step 1 and Step 2; upward-only; no downgrade language
- [ ] AC2 Fixture file ≥6 behaviors with expected firings; walk-through actual == expected
- [ ] AC3 Each gate cost+amortization once; multi-gate union + reconciliation
- [ ] AC4 Gate C browser required (both cases); integration complementary
- [ ] AC5 Gate D approval/screenshot/cost; no-reference → manual + suggest reference
- [ ] AC6 Gate B negative — unit-found bug does not escalate
- [ ] AC7 Redundancy fires only on business-critical; names layer + concrete recommendation
- [ ] AC8 Ambiguity: assumption stated, asked once/batched, global option, no silent escalation
- [ ] AC9 Altitude boundary durable grep: deferral present, no harness design
- [ ] AC10 Terminology cross-ref to cd-test-architecture six types; Constraints restate boundary
- [ ] AC11 Budgets: knowledge ≤450 tokens; Step 1b ≤~150 tokens
- [ ] AC12 Registered in agent-registry + CLAUDE.md (18→19) + regenerated index.json; grounding line
- [ ] AC13 `/agent-audit` passes
