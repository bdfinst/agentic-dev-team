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

Three artifacts (Intent, Architecture Specification, Acceptance Criteria) plus a consistency gate pass/fail verdict. Be concise — flag gaps and conflicts; do not narrate the collaboration process.

### Persist artifacts

After the gate passes, persist all three artifacts plus the verdict so downstream commands (`/plan`, `/build`, spec-compliance-review) can find the spec — chat-only specs are lost between sessions. **Where** they're persisted depends on the project's origin and whether it has opted into the issue-first specs convention.

#### Classify where to persist

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/git_origin_host.py` to classify the origin remote: `github` / `other` / `none`.
2. When the result is `github`, additionally run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs_convention_marker.py` to classify the project's root `CLAUDE.md`: `marker` (contains the issue-first-specs opt-in phrase, e.g. "Specs and plans are GitHub issues here, not files") / `no-marker` (file exists, phrase absent) / `none` (no root `CLAUDE.md` found). If it reports `no-marker` or `none`, you MAY still read the root `CLAUDE.md` yourself and apply judgment for an equivalently-worded-but-differently-phrased declaration of the same convention before concluding "no marker" — but this manual-judgment fallback is deliberately unverified by any automated test, unlike the script's literal-match path (see the script's own module docstring).
3. **Branch**:
   - `github` origin **and** a marker found (by the script or by manual judgment) → **Persist to GitHub issue** (below). No downstream consumer of the shipped plugin is silently switched to this path — it requires both an actual GitHub origin and an explicit, repo-declared opt-in.
   - Anything else — non-`github` origin, `none` origin, or a `github` origin with **no** marker found by either path — → **Persist to file** (below). This is today's behavior, unchanged.

#### Persist to file

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

## Ambiguity Log

All gap and ambiguity findings from the Ambiguity Resolution Protocol, with their classifications and rationale.

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| <decision text> | `inferable` / `requires-stakeholder-input` | inference / human | <rationale or human's answer> |

## Consistency Gate
- [x/  ] Intent is unambiguous
- [x/  ] Every behavior/goal maps to an acceptance criterion
- [x/  ] Architecture constrains without over-engineering
- [x/  ] Terminology consistent across artifacts
- [x/  ] No contradictions between artifacts
- [x/  ] Every gap/ambiguity finding is logged — inferable with rationale or resolved by human
```

1. **Print** the file path to chat so the user can find it.

#### Persist to GitHub issue

1. **Slugify** the feature name (same rule as above) — used to derive the issue title and search query, not a file path.
2. **Search** for an existing open issue: `gh issue list --search "Spec: <Feature Name> in:title" --state open`. If this call itself exits non-zero, treat it as a hard failure — **never** as "zero matches" (that would risk silently creating a duplicate issue) — report the failure and its cause to chat, and fall back to **Persist to file** above with the already-composed content so the approved spec is never lost.
3. **Branch on the match count**:
   - **Zero matches** → proceed straight to create (step 4).
   - **Exactly one match** → interactive: ask "Found existing issue #N for this spec — update it in place, or create a new one?"; non-interactive (no usable TTY): default to **updating** that single match in place (never create a duplicate) and log the auto-choice.
   - **Two or more matches** → interactive: surface every matching issue and ask which to update, or whether to create a new one instead — never silently pick one; non-interactive: default to **creating** a new issue and explicitly log the ambiguity (which candidate issues it did not act on).
4. **Compose** the issue body using the same structure as the file template above (Intent Description, Architecture Specification, Acceptance Criteria, Ambiguity Log, Consistency Gate), titled `Spec: <Feature Name>`.
5. **Create** (`gh issue create --title "Spec: <Feature Name>" --body "<composed body>"`) or **update** (`gh issue edit <N> --body "<composed body>"`) per step 3's decision.
6. If the create/update call exits non-zero, report the failure and its cause to chat, do **not** claim success, and fall back to **Persist to file** above with the already-composed content.
7. On success, **print** the resulting issue URL to chat — do not write `docs/specs/<slug>.md` on this path.

### Auto-trigger /plan

After persisting, automatically invoke `/plan` with the feature description. The plan command discovers the spec artifacts, decomposes the feature into vertical slices, and authors the Gherkin scenarios for each slice. Do not ask first — the approved spec is the trigger.

- **File-based persistence** (unchanged): invoke `/plan "<feature description>"` — `/plan` discovers `docs/specs/**` on its own.
- **GitHub-issue persistence**: invoke `/plan "<feature description>" --spec-issue <issue-url>`, passing the issue URL from "Persist to GitHub issue" step 7. Without this, `/plan`'s own Step 1 (which only searches `docs/specs/**`) would immediately hit its "no specification artifacts found" prompt in the very same run — reintroducing the human interruption this auto-trigger's "do not ask first" contract exists to avoid.
