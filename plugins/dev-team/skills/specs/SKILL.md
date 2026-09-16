---
name: specs
description: Collaborative workflow for producing the three specification artifacts (intent, architecture notes, acceptance criteria) that describe a change and its goals before any implementation begins. Its value is resolving ambiguity with a human before build starts — not synthesizing edge cases. Use when starting any new feature or behavior change — do not write code until artifacts pass the consistency gate. BDD/Gherkin scenarios are authored later, per slice, in /plan.
role: orchestrator
user-invocable: true
---

# Agent-Assisted Specification

Role: orchestrator. This command produces specification artifacts and gates
progression to `/plan` — it does not write implementation code, author
per-slice Gherkin scenarios, or begin building.

## Positioning — what this skill is for

This skill's value is **resolving ambiguity with a human before build begins**
(Rec 1, `docs/experiments/RECOMMENDATIONS.md`). No downstream workflow recovers
information the spec never stated — under vague specs every workflow arm scored
0% on acceptance tests probing an omitted decision. The Ambiguity Resolution
Protocol below is the mechanism: it forces every gap to be either resolved by a
human or documented as inferable before implementation starts.

What this skill is **not** for: edge-case synthesis. Run to completion, the
full `/specs`→`/plan`→`/build` pipeline's explicit acceptance-criteria
synthesis does not out-perform TDD's failing-test discipline at surfacing
unstated edge cases (25% vs. 33% pooled EDGE pass — Experiment 03, reported in
`docs/experiments/02-final-results.md`). The two have different failure modes
and both are worth keeping: `/specs` catches ambiguity a human must resolve;
the build cadence's per-behavior tests catch edge cases the spec implies but
never enumerates.

## Step 0 — Select the mode

`/specs` runs in one of two modes, chosen from the **shape of the argument** —
there is no flag, so every existing `/specs "<description>"` invocation is
unaffected. Announce the selected mode and why before any work begins.

| Argument | Mode |
|---|---|
| Resolves to a readable `.md`/`.txt`/`.pdf`, or a fetchable GitHub issue URL | **validate** — critique a document we did not write |
| *Looks* like a path or issue URL (a path separator, one of those extensions, or a GitHub issue URL shape) but does not resolve or cannot be fetched | **refuse** — see below |
| Resembles neither | **authoring** — today's collaboration loop, unchanged |

**A path-like argument that does not resolve is never reinterpreted as prose.**
Silently feeding a mistyped path into the authoring loop turns a typo into a
spec seeded from the literal path string, which the author may not notice for
a long time. Refuse instead, naming the unresolved path or the fetch failure
(private, deleted, unauthenticated, network).

**Unsupported formats are refused too, never partially parsed.** The supported
set is what `Read` handles natively. `.docx` is explicitly out — the plugin
ships stdlib-only Python (ADR 0014/0015) and no stdlib path parses it. Name the
reason and the conversion to perform; do not guess at a partial read.

Validate mode then runs the same critique categories, Ambiguity Resolution
Protocol, and Consistency Gate as authoring mode, against the source text
rather than a co-authored draft — a third-party document blocks exactly as hard
as an in-house draft. **Every extracted acceptance criterion cites the source
passage it came from; one with no citable passage is an inference and is logged
as such, never presented as if the source stated it.** Load
[`references/extraction.md`](references/extraction.md) for the supported
inputs, the citation rule, and the routing.

## Step 0 — Existing-spec version check

Before drafting or updating a spec, check whether a spec file already exists for
this feature:

- If no spec file exists: proceed directly to Step 1.
- If a spec file exists: read its opening lines and check for a `<!-- spec-version: -->` comment or a `**Format:**` header field.
  - If the marker is absent or predates the current skill version (see frontmatter `version:`): surface this to the user — *"An existing spec was found but appears to use an older format. Regenerate from scratch, or confirm you want to update in place?"* — and wait for explicit direction before proceeding.
  - If the marker matches the current version: proceed to Step 1 with the existing file as base.

This prevents silently overwriting a current spec and catches format drift before
the plan phase consumes stale artifacts.
Produce three specification artifacts collaboratively with the human before any implementation begins. The spec describes the change and its goals; it does **not** define Gherkin scenarios — those are authored per slice during `/plan`. The consistency gate is a hard stop; do not proceed to planning until it passes.

## Rules

1. **No implementation during specification.** No code, no tests, no infrastructure until the consistency gate passes.
2. **One feature per specification.** A spec describes a single coherent change end-to-end. Vertical slicing is deferred to `/plan` — do not slice here. Split into separate specs only when the request bundles genuinely unrelated features (see Scope Split Protocol).
3. **Consistency gate is a hard stop.** Conflicts caught now cost minutes; conflicts caught during implementation cost sessions.
4. **Behavior contracts are authored in the plan.** The spec sets intent, architecture constraints, and acceptance criteria. `/plan` turns those into per-slice Gherkin scenarios — the single source of truth for expected behavior. No implementation without a scenario; no scenario without an acceptance test.
5. **Max 2 critique-refine iterations** per artifact. If it doesn't stabilize, escalate to the Orchestrator.
6. **Preserve human language** when refining. The human owns the specification; the agent improves precision.
7. **Structured critique output.** Categorize every critique (gap, ambiguity, conflict, scope violation) with a specific reference to the artifact text.
8. **Document decisions, not just outcomes.** When the human rejects an agent suggestion, note why — prevents the same suggestion from recurring.

## Artifacts

| Artifact | Purpose | Format |
| --- | --- | --- |
| Intent Description | What the change achieves and why | Plain language, 1–3 paragraphs |
| Architecture Specification | Where the change fits and what constraints apply | Structured notes: components, interfaces, dependencies, constraints |
| Acceptance Criteria | Observable outcomes and quality thresholds that define "done" | Measurable criteria with pass/fail conditions |

Observable user behavior is captured as Gherkin in `/plan`, one scenario set per slice. The spec's job is to make that authoring unambiguous, not to pre-write it.

## Collaboration loop

Every artifact follows the same loop:

1. **Human drafts** based on current understanding.
2. **Agent critiques** — categorize each finding as gap, ambiguity, conflict, or scope violation, with a specific reference.
3. **Human decides** — accept, reject, or modify.
4. **Agent refines** — produce an updated version incorporating decisions.

Repeat up to **2 iterations** before escalating.

### Critique categories

| Category | Description |
| --- | --- |
| Gaps | Missing acceptance criteria, unstated assumptions, undefined behavior |
| Ambiguities | Statements two implementers would interpret differently |
| Conflicts | Contradictions between artifacts or with existing system behavior |
| Scope violations | Spec bundles unrelated features that belong in separate specs |

## Ambiguity Resolution Protocol

After critiquing the artifacts but before writing the final acceptance criteria, run this protocol on every gap and ambiguity finding. This is a hard step — it cannot be skipped.

For each gap or ambiguity:

**Step A — Attempt inference.** Look for a reliable basis: existing codebase behavior, domain conventions, similar precedents in the system, or unambiguous implication from stated requirements.

**Step A2 — Predictability check.** Generate **at most one** plausible
alternative outcome per criterion and test it against the source; if the source
does not rule it out, classify `requires-stakeholder-input`. Record the outcome
in the Ambiguity Log row every time, pass included. Load
[`references/predictability-check.md`](references/predictability-check.md) — it
covers absurd-candidate rejection, the no-plausible-alternative case, and why
this does not duplicate `plan-review-acceptance`.

**Step B — Classify the finding.**

| Class | Meaning | Action |
|-------|---------|--------|
| `inferable` | A reasonable developer, given the codebase and domain, would make the same choice | Document the inference and its rationale; proceed |
| `requires-stakeholder-input` | The decision depends on product or business intent not evident from context; two reasonable developers would choose differently | **Block — ask the human before proceeding** |

**Step C — Resolve `requires-stakeholder-input` items.** Collect all such items and present them as a single batch to the human before writing acceptance criteria:

> "Before writing acceptance criteria, I need clarification on N decisions the spec leaves open: [list]"

Wait for answers. Only then finalize the criteria.

**What "inferable" is NOT:** a convenient default. Naturalness or simplicity does not make a decision inferable — the test is whether a developer working from context alone would reliably land on the same answer. If in doubt, classify as `requires-stakeholder-input`.

**Record every classification** in an `## Ambiguity Log` section of the spec file (see Output below). This log is the audit trail that turns "we asked before building" from an assertion into an artifact.

This protocol exists because the most common failure mode of spec synthesis from a vague prompt is writing decisions that look thorough while encoding the same happy-path assumptions a direct implementation would make silently. The log prevents that by making every assumption visible and every gap either resolved by the human or documented as inferable with explicit rationale.

## Gap classification: NO_REFACTOR / REFACTOR_REQUIRED / LOW_VALUE

When a critique surfaces a missing-test or coverage gap, classify it so the spec only carries work that delivers signal:

- `NO_REFACTOR` — a meaningful test can be written against the code as it stands. Carry it into the acceptance criteria.
- `REFACTOR_REQUIRED` — production code needs a testability change before a meaningful test is possible. Note the change.
- `LOW_VALUE` — **skip, not defer.** A `LOW_VALUE` finding is never written into the acceptance criteria and is never parked as deferred backlog; deferring it only re-surfaces the same no-signal work later. All three criteria must hold: no branching logic, no observable outcome (the only possible assertion is that a mock was called), and a higher-layer test already covers the path.

`LOW_VALUE` is the one class dropped rather than tracked — the Ambiguity Log records the skip and its rationale, nothing more. It never becomes an acceptance criterion and never reaches `/plan` as work.

## Scope signals

A specification bundles too much when any of these fire:

- Specification effort exceeds a short conversation.
- More than ~5 components are affected.
- Genuinely unrelated features are described (not just multiple slices of one feature).
- The features described would not ship or be validated together.

Note: a single feature that decomposes into several deliverable increments is **normal and expected** — that decomposition happens in `/plan`, not here. Only split the spec when the features are independent.

### Scope Split Protocol

1. Identify the unrelated features bundled into the request.
2. Propose a split into separate specs, one per feature.
3. Human approves the split before specification continues on any feature.
4. Each feature gets its own full set of three artifacts.

## Glossary

Capture domain terms **while drafting** Intent and Acceptance Criteria. A
definition the agent inferred starts `unverified`; `verified` requires a human.
A term still `unverified` at the end of the loop is a gap finding and routes
through the Ambiguity Resolution Protocol — it does not block the Consistency
Gate by itself. Load [`references/glossary.md`](references/glossary.md) for the
status contract, the resolution rule, and the downstream consumers.

## Completeness sweep

After the critique loop and **before** the Consistency Gate, sweep for what the
spec never mentioned. A spec that says nothing about deletion produces no
criterion to find incomplete — the omission is the absence of a criterion, and
absence is invisible to every per-criterion check we run.

Load [`references/completeness-checklist.md`](references/completeness-checklist.md)
and apply it: CRUD per named entity, plus authentication, authorization,
audit/logging, and error handling for the spec as a whole.

- **Report the entities you enumerated.** Enumeration is a model step, not a
  parser's, so showing the list is what lets a human catch a missed entity.
- **Group findings by entity**, separating cells dispositionable in one answer
  from those needing individual judgment — a flat dump invites rubber-stamping.
- **Route each unaddressed cell** into the Ambiguity Log as `inferable` (with
  rationale — including "read-only by design") or `requires-stakeholder-input`.
  A cell that does not apply is recorded with its reason, never dropped.

**The sweep is not a gate.** It blocks only through the existing Ambiguity
Resolution Protocol; it introduces no new gate, severity scheme, or confidence
score. It also never grades a criterion that already exists — that is
`plan-review-acceptance`'s scope. The two answer different questions: "is there
a criterion here at all?" versus "is this criterion complete?"

## Cross-Artifact Consistency Gate

Validate all three artifacts as a set:

- [ ] Intent is unambiguous — two developers would interpret it the same way.
- [ ] Every behavior or goal in the intent maps to at least one acceptance criterion.
- [ ] Architecture specification constrains implementation to what the intent requires, without over-engineering.
- [ ] Same concepts are named consistently across all three artifacts.
- [ ] No artifact contradicts another.
- [ ] Every gap and ambiguity finding is logged — either documented as `inferable` (with explicit rationale) or resolved via explicit stakeholder input. No finding is left as an undocumented assumption.

**Hard stop**: do not proceed to planning until every item passes. The ambiguity log item is the most critical: a passing gate with undocumented assumptions produces false confidence.

## Output

Three artifacts (Intent, Architecture Specification, Acceptance Criteria) plus a
consistency gate pass/fail verdict. Be concise — flag gaps and conflicts; do not
narrate the collaboration process.

Once the gate passes, persist the artifacts and trigger the next phase. That
procedure — classifying file vs. GitHub-issue persistence, the body template,
and the `/plan` auto-trigger — lives in
[`references/persistence.md`](references/persistence.md). **Load it now.**
