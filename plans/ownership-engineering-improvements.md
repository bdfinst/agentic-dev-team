# Plan — raising the team's Ownership Engineering scores

## Status — implemented on this branch

All three waves have been applied as prose changes to the agents and skills (see the
checklist at the foot of each wave; every "Acceptance" item's prose now exists).
Wave 3.1's parked decision was resolved to **option (b)** — `progress-guardian` stays
read-only and flags the validation to dispatch rather than gaining an execution tool
— as recommended, since the human was unavailable. Wave 3.2 (the systematic-debugging
"Improve" step) was implemented rather than deferred. A later request added an
eighth dimension, **Quality Ownership** (Wave 2.4) — a failing test is a failing test
regardless of whose change caused it — enforced cross-cutting in the always-loaded
CLAUDE.md and hard-gated in the validation skills. The
[scorecard re-score](../evals/ownership-engineering/scorecard.md#re-score-after-implementation-waves-13)
records the projected post-change scores; a judge run over the fixtures is the
remaining step to convert those projections to measured results.

**Goal:** move the team agents and workflow skills toward the Ownership
Engineering posture (deliver outcomes, own results) on the dimensions where the
[baseline scorecard](../evals/ownership-engineering/scorecard.md) shows them
routing uncertainty to the human too early or accepting un-proven "done."

**North-Star framing (per `plugins/dev-team/CLAUDE.md`):** each change below names
the friction it removes. The friction is **avoidable human round-trips and
un-owned outcomes** — every premature escalation or un-evidenced "done" is a
misstep the user has to catch and correct. The instrument is the
[OE eval suite](../evals/ownership-engineering/README.md): the listed fixtures
flip from fail→pass and the scorecard cells rise.

**Method:** these are prose/spec changes to existing agents and skills. Each
change ships behind the repo's normal gates: `/agent-audit` for structural
compliance, the deterministic `--check-corpus` gate (unaffected — see suite
README), and a judge pass over the named fixtures to confirm the target behavior.
Do **not** weaken any existing evidence/validation gate; these changes *add*
ownership at the front of the loop and *tighten* two spots at the back.

---

## Wave 1 — Front-of-loop ownership (highest leverage, lowest risk)

These four changes address the weakest cluster: discovery/decision subjects that
gate well but under-absorb uncertainty and under-commit.

### 1.1 Human Oversight Protocol — replace the Medium-tier menu (`CD`, `UA`)
**File:** `plugins/dev-team/skills/human-oversight-protocol/SKILL.md:155`
**Friction removed:** every reversible medium-severity decision currently triggers
a human round-trip the agent could have owned.
**Change:** rewrite the Medium escalation path from *"present options to human with
recommendation"* to an **investigate-decide-proceed-with-override** rule:
> Medium: absorb the uncertainty first (investigate within the codebase / run the
> relevant check). If the decision is reversible and low-blast-radius, **commit to
> one path, state the rationale, proceed, and surface an explicit override** ("I'm
> taking X; reply `override` to change course"). Reserve no-recommendation
> escalation (High) for irreversible or high-blast-radius decisions.
Keep High unchanged (genuinely needs human judgment; no anchoring).
**Acceptance:** `oe-08-medium-severity-escalation` (the `knownGap` sentinel) flips
fail→pass; oversight CD ≥4, UA ≥4. The override affordance and accumulation rule
(3+ overrides → config amend) still hold.

### 1.2 Product Manager — add a Clarification Window (`CW`, `UA`, `CD`)
**File:** `plugins/dev-team/agents/product-manager.md`
**Friction removed:** vague requests today produce drip-fed questions or escalated
conflicts instead of one decisive discovery round.
**Change:** add a **Discovery** section that wires in `design-interrogation`'s
pattern: on an underspecified request, (a) resolve codebase-answerable unknowns by
investigating, (b) batch the genuinely user-only questions into **one** round, each
with a recommended default, (c) for conflicting stakeholder needs, **mediate and
propose a resolution** before escalating. Reframe the escalation criteria from
"conflict → escalate" to "conflict → investigate/mediate, escalate only if
unresolved."
**Acceptance:** `oe-01-vague-feature-request` passes; PM CW ≥4, UA ≥3, CD ≥3.

### 1.3 Architect — decide, don't merely recommend (`CD`)
**File:** `plugins/dev-team/agents/architect.md:10`
**Friction removed:** reversible design choices within the architect's authority
get handed back as menus.
**Change:** keep "reason in trade-offs," but change the closing move from
"recommending an approach" to **"commit to a decision, with the human able to
override"** for reversible, in-authority choices; reserve true menus for
architecture-shifting/irreversible decisions (which already require approval).
Add a one-line discovery cue ("identify the constraints you need from the codebase
before deciding").
**Acceptance:** `oe-03-two-viable-designs` passes; architect CD ≥4.

### 1.4 Orchestrator — dispatch-to-investigate before escalating (`UA`)
**File:** `plugins/dev-team/agents/orchestrator.md` (escalation-criteria section, ~:279)
**Friction removed:** "ambiguous requirements" currently triggers a human hand-off
when the orchestrator could dispatch the PM/architect/recon to resolve it.
**Change:** reword so ambiguity is first a **dispatch trigger** (route to PM for
product ambiguity, architect for design ambiguity, codebase-recon for factual
unknowns); escalate to the human only after that investigation fails to resolve it.
**Acceptance:** `oe-01` (orchestrator path) passes; orchestrator UA ≥3.

---

## Wave 2 — Back-of-loop tightening (narrow, additive)

The validation skills are already OE exemplars; these close their two residual gaps
without loosening any existing gate.

### 2.1 build & TDD — name the debugging step before escalating (`DD`)
**Files:** `plugins/dev-team/skills/build/SKILL.md:134-140`;
`plugins/dev-team/skills/test-driven-development/SKILL.md` (red-flags section)
**Friction removed:** an attempt-count cap that hands back on the Nth failure with
no required investigation — the user inherits an undiagnosed failure.
**Change:** before any "escalate after N attempts," require an explicit
`systematic-debugging` pass (reproduce → root cause stated in one sentence) and
**escalate with that diagnosis**, not just the count. Change TDD's "Inability to
explain why a test failed → restart from RED" to "→ enter systematic-debugging to
find root cause, *then* decide restart vs. fix." Keep the iron laws intact.
**Acceptance:** `oe-06-failing-test-handback` passes; build/TDD DD ≥4. No change to
the RED/GREEN paste-output gates.

### 2.4 Quality Ownership — a failing test is a failing test (`QO`, new dimension)
**Files:** `plugins/dev-team/CLAUDE.md` (Quality & Accuracy, always-loaded);
`plugins/dev-team/skills/quality-gate-pipeline/SKILL.md` (Phase 2 evidence);
`plugins/dev-team/skills/build/SKILL.md` (full-suite step);
`plugins/dev-team/agents/qa-engineer.md` (sign-off gate);
`plugins/dev-team/skills/test-driven-development/SKILL.md` (verification checklist)
**Friction removed:** agents narrowing responsibility to their own diff and shipping
over a red suite by calling failures "pre-existing / not my change" — the user
inherits a broken build the agent watched go red.
**Change:** add **Quality Ownership** as the eighth rubric dimension and enforce it:
green means the **whole suite**, not just the changed tests; a failing test is a
failing test **regardless of whether the current change caused it**. A red signal
must be **fixed** or **explicitly surfaced and triaged** (`/triage`/quarantine with a
recorded reason) and reported as not-green — never stepped over. The principle lives
in the always-loaded CLAUDE.md so it reaches every agent, with hard enforcement in
the validation skills.
**Acceptance:** `oe-09-preexisting-failing-test` passes; build/quality-gate/qa QO
≥4. No existing evidence/validation gate weakened.

### 2.2 quality-gate-pipeline — "logged" ≠ "resolved" (`DC`)
**File:** `plugins/dev-team/skills/quality-gate-pipeline/SKILL.md:133`
**Friction removed:** a minor defect marked "logged" can ride out under a "complete"
banner, so the user discovers it later.
**Change:** the completion gate must distinguish *resolved* (fixed + re-verified)
from *deferred* (logged with an owner and a tracking ref). A slice cannot be called
**complete** on the strength of "logged" alone; deferred items must be explicitly
surfaced in the completion summary, not folded into "done."
**Acceptance:** `oe-07-implementation-not-completion` passes (quality-gate path);
quality-gate DC stays 4 but the "logged-as-done" escape is closed.

### 2.3 qa-engineer — an explicit evidence-backed sign-off gate (`ER`, `DC`, `LV`)
**File:** `plugins/dev-team/agents/qa-engineer.md`
**Friction removed:** QA "done" is diffuse — evidence goes to files the human may
never open, and no one owns the final sign-off.
**Change:** add a **QA sign-off gate**: a feature is QA-complete only when (a) the
relevant suite/browser run was executed **this session** and its result **surfaced
in the conversation** (not just written to a file), and (b) the QA agent is the
named owner of that sign-off. For UI changes, the sign-off requires live
verification via `/browse`, not a static reading.
**Acceptance:** `oe-04`, `oe-05`, `oe-07` (qa paths) pass; qa-engineer ER ≥4, DC ≥4.

---

## Wave 3 — Enablement (optional, larger)

### 3.1 progress-guardian — give it the ability to verify, or re-scope it (`LV`, `DC`)
**File:** `plugins/dev-team/agents/progress-guardian.md`
**Friction removed:** the guardian can detect "marked complete without acceptance
criteria verified" but cannot run anything to confirm it — a structural blind spot.
**Decision required (carry to the human):** either (a) grant a constrained Bash
capability (run the suite read-only) so it can verify rather than infer, or (b)
keep it read-only and make it **dispatch** the build/quality-gate to validate, then
report on that evidence. Option (b) is lower-risk and preserves its read-only
contract; option (a) is more direct but widens its tool surface. Recommend (b).
**Acceptance:** `oe-07` (progress-guardian path) passes; guardian LV/DC ≥3.

### 3.2 Cross-bug learning loop for systematic-debugging (`DD`, stretch)
**File:** `plugins/dev-team/skills/systematic-debugging/SKILL.md`
A recurring bug class should leave behind a diagnostic pattern (an "Improve" step in
the ownership loop) rather than being re-discovered each time. Lower priority; ties
into the existing feedback-learning machinery. Defer unless Waves 1–2 land cleanly.

---

## Sequencing & risk

| Wave | Changes | Risk | Why first/last |
| --- | --- | --- | --- |
| 1 | 1.1–1.4 | Low (prose-only, additive at the front of the loop) | Highest leverage; no existing gate touched. 1.1 is the single biggest win. |
| 2 | 2.1–2.3 | Low–medium (must not weaken evidence gates) | Tightens proven skills; 2.3 adds a gate rather than relaxing one. |
| 3 | 3.1–3.2 | Medium (tool-surface / new machinery) | Needs a human decision (3.1) and is larger (3.2). |

**Guardrails for every wave**
- Run `/agent-audit` after each agent/skill edit (structural compliance).
- The deterministic `--check-corpus` gate is unaffected (behavioral expecteds live
  outside `evals/expected/`), but run it anyway to prove no collision.
- For each change, judge the named fixture(s) before/after and record the
  fail→pass flip; update `evals/ownership-engineering/scorecard.md` cells with the
  new scores and re-stamp provenance.
- **Do not** trade front-of-loop ownership against back-of-loop rigor: the agent
  decides *more* on reversible choices **and** proves *more* before claiming done.
  Both move up; neither moves down.

## Definition of done for this plan

- Waves 1 and 2 implemented; all eight OE fixtures pass under a judge run
  (`oe-08` flips off its `knownGap` sentinel).
- Scorecard re-scored: no subject below 3 on any in-role dimension; the
  human-oversight, PM, and qa-engineer rows rise out of the 1–2 band.
- No regression in the existing detection corpus or any evidence/validation gate.
- Wave 3's 3.1 decision (a vs. b) put to the human; 3.2 explicitly deferred or
  scheduled.
