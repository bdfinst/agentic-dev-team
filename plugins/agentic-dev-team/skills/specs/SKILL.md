---
name: specs
description: Collaborative workflow for producing the four specification artifacts (intent, BDD scenarios, architecture notes, acceptance criteria) before any implementation begins. Use when starting any new feature or behavior change — do not write code until artifacts pass the consistency gate.
role: worker
user-invocable: true
---

# Agent-Assisted Specification

Produce four specification artifacts collaboratively with the human before any implementation begins. The consistency gate is a hard stop; do not proceed to code until it passes.

## Rules

1. **No implementation during specification.** No code, no tests, no infrastructure until the consistency gate passes.
2. **One vertical slice per specification.** Split if scope is too broad (see Scope Split Protocol).
3. **Consistency gate is a hard stop.** Conflicts caught now cost minutes; conflicts caught during implementation cost sessions.
4. **Gherkin scenarios are contracts.** BDD scenarios in feature files are the single source of truth for expected behavior. No implementation without a scenario; no scenario without an acceptance test.
5. **Max 2 critique-refine iterations** per artifact. If it doesn't stabilize, escalate to the Orchestrator.
6. **Preserve human language** when refining. The human owns the specification; the agent improves precision.
7. **Structured critique output.** Categorize every critique (gap, ambiguity, conflict, scope violation) with a specific reference to the artifact text.
8. **Document decisions, not just outcomes.** When the human rejects an agent suggestion, note why — prevents the same suggestion from recurring.

## Artifacts

| Artifact | Purpose | Format |
|---|---|---|
| Intent Description | What the change achieves and why | Plain language, 1–3 paragraphs |
| User-Facing Behavior | Observable behavior from the user's perspective | BDD/Gherkin scenarios |
| Architecture Specification | Where the change fits and what constraints apply | Structured notes: components, interfaces, dependencies, constraints |
| Acceptance Criteria | Non-functional requirements and quality thresholds | Measurable criteria with pass/fail conditions |

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
| Gaps | Missing scenarios, unstated assumptions, undefined behavior |
| Ambiguities | Statements two implementers would interpret differently |
| Conflicts | Contradictions between artifacts or with existing system behavior |
| Scope violations | Change covers more than one vertical slice |

## Scope signals

Specification is too broad when any of these fire:

- Specification effort exceeds a short conversation.
- More than 3 components are affected.
- Multiple independent behaviors are described.
- The change cannot be deployed and validated independently.

### Scope Split Protocol

1. Identify the independent behaviors within the oversized change.
2. Propose a split into separately deliverable vertical slices.
3. Human approves the split before specification continues on any slice.
4. Each slice gets its own full set of four artifacts.

## BDD Scenario Review

Before the consistency gate, run `feature-file-validation` against the User-Facing Behavior artifact:

- Negative cases covered (invalid, unauthorized, missing, malformed input)
- Edge cases covered (empty collections, boundary values, concurrent access, idempotency)
- Error scenarios explicit (specify observable error behavior, not just "should fail")

If gaps appear, present them as a critique and run another collaboration loop iteration before the gate.

## Cross-Artifact Consistency Gate

Validate all four artifacts as a set:

- [ ] Intent is unambiguous — two developers would interpret it the same way.
- [ ] Every behavior in the intent has at least one BDD scenario.
- [ ] Architecture specification constrains implementation to what the intent requires, without over-engineering.
- [ ] Same concepts are named consistently across all four artifacts.
- [ ] No artifact contradicts another.

**Hard stop**: do not proceed to implementation until every item passes.

## Output

Four artifacts (Intent, User-Facing Behavior in Gherkin, Architecture Specification, Acceptance Criteria) plus a consistency gate pass/fail verdict. Be concise — flag gaps and conflicts; do not narrate the collaboration process.

### Persist to file

After the gate passes, write all four artifacts plus the verdict to a markdown file. Downstream commands (`/plan`, `/build`, spec-compliance-review) find the spec via this file — chat-only specs are lost between sessions.

1. **Slugify** the feature name: lowercase, replace spaces with hyphens, strip special characters. ("User Login with MFA" → `user-login-with-mfa`)
2. **Create** `docs/specs/` if missing.
3. **Check** whether `docs/specs/<slug>.md` already exists. If yes, ask: overwrite or create a versioned file (`<slug>-v2.md`)?
4. **Write** using this structure:

```markdown
# Spec: <Feature Name>

## Intent Description
<intent artifact>

## User-Facing Behavior
<Gherkin scenarios in a fenced code block>

## Architecture Specification
<architecture artifact>

## Acceptance Criteria
<acceptance criteria artifact>

## Consistency Gate
- [x/  ] Intent is unambiguous
- [x/  ] Every behavior has a corresponding BDD scenario
- [x/  ] Architecture constrains without over-engineering
- [x/  ] Terminology consistent across artifacts
- [x/  ] No contradictions between artifacts
```

5. **Print** the file path to chat so the user can find it.

### Auto-trigger /plan

After persisting, automatically invoke `/plan` with the feature description. The plan command discovers spec artifacts and includes BDD scenarios in the plan document. Do not ask first — the approved spec is the trigger.
