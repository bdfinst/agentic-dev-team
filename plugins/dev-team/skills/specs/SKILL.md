---
name: specs
description: Collaborative workflow for producing the three specification artifacts (intent, architecture notes, acceptance criteria) that describe a change and its goals before any implementation begins. Use when starting any new feature or behavior change — do not write code until artifacts pass the consistency gate. BDD/Gherkin scenarios are authored later, per slice, in /plan.
role: worker
user-invocable: true
---

# Agent-Assisted Specification

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
|---|---|---|
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
|---|---|
| Gaps | Missing acceptance criteria, unstated assumptions, undefined behavior |
| Ambiguities | Statements two implementers would interpret differently |
| Conflicts | Contradictions between artifacts or with existing system behavior |
| Scope violations | Spec bundles unrelated features that belong in separate specs |

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

## Cross-Artifact Consistency Gate

Validate all three artifacts as a set:

- [ ] Intent is unambiguous — two developers would interpret it the same way.
- [ ] Every behavior or goal in the intent maps to at least one acceptance criterion.
- [ ] Architecture specification constrains implementation to what the intent requires, without over-engineering.
- [ ] Same concepts are named consistently across all three artifacts.
- [ ] No artifact contradicts another.

**Hard stop**: do not proceed to planning until every item passes.

## Output

Three artifacts (Intent, Architecture Specification, Acceptance Criteria) plus a consistency gate pass/fail verdict. Be concise — flag gaps and conflicts; do not narrate the collaboration process.

### Persist to file

After the gate passes, write all three artifacts plus the verdict to a markdown file. Downstream commands (`/plan`, `/build`, spec-compliance-review) find the spec via this file — chat-only specs are lost between sessions.

1. **Slugify** the feature name: lowercase, replace spaces with hyphens, strip special characters. ("User Login with MFA" → `user-login-with-mfa`)
2. **Create** `docs/specs/` if missing.
3. **Check** whether `docs/specs/<slug>.md` already exists. If yes, ask: overwrite or create a versioned file (`<slug>-v2.md`)?
4. **Write** using this structure:

```markdown
# Spec: <Feature Name>

## Intent Description
<intent artifact>

## Architecture Specification
<architecture artifact>

## Acceptance Criteria
<acceptance criteria artifact>

## Consistency Gate
- [x/  ] Intent is unambiguous
- [x/  ] Every behavior/goal maps to an acceptance criterion
- [x/  ] Architecture constrains without over-engineering
- [x/  ] Terminology consistent across artifacts
- [x/  ] No contradictions between artifacts
```

1. **Print** the file path to chat so the user can find it.

### Auto-trigger /plan

After persisting, automatically invoke `/plan` with the feature description. The plan command discovers the spec artifacts, decomposes the feature into vertical slices, and authors the Gherkin scenarios for each slice. Do not ask first — the approved spec is the trigger.
