# Ownership Engineering scorecard — baseline

Baseline assessment of this plugin's team agents and workflow skills against the
eight [rubric](rubric.md) dimensions. Scores are 1–5 (see rubric); **N/A** marks a
dimension outside a subject's role. This baseline is **hand-authored** from a prose
read of each file (file:line evidence below), analogous to `evals/baseline.json`'s
`hand-authored` provenance — it is not yet a measured judge run over the fixtures.

Dimensions: **CW** Clarification Window · **UA** Uncertainty Absorption ·
**CD** Committed Decisions · **ER** Evidence over Reasoning · **LV** Live Validation
· **DD** Debug-Don't-Stop · **DC** Demonstrable Completion · **QO** Quality Ownership.

## Scores

| Subject | CW | UA | CD | ER | LV | DD | DC | QO | Notes |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| orchestrator | 4 | 2 | 4 | 3 | 3 | 2 | 3 | N/A | Phases gate well; escalates ambiguity instead of dispatching investigation. |
| software-engineer | 2 | 4 | 4 | 4 | 3 | 3 | 3 | 3 | Owns implementation; no upfront discovery, escalates per-conflict. |
| product-manager | 1 | 2 | 2 | N/A | N/A | N/A | N/A | N/A | No discovery phase; escalates stakeholder conflicts rather than mediating. |
| architect | 2 | 4 | 3 | N/A | N/A | N/A | 4 | N/A | Reasons in trade-offs but "recommends" rather than deciding. |
| codebase-recon | N/A | 5 | 4 | 4 | N/A | N/A | 4 | N/A | Exemplary: absorbs incomplete data, emits a contract-conformant artifact. |
| human-oversight-protocol | 2 | 1 | 2 | N/A | N/A | N/A | N/A | N/A | Medium tier mandates "present options" — the central anti-ownership gap. |
| design-interrogation | 5 | 4 | 3 | N/A | N/A | N/A | N/A | N/A | Excellent batched discovery; surfaces decisions but the user still decides. |
| build | N/A | N/A | N/A | 5 | 4 | 2 | 4 | 3 | Runs the full suite but no "pre-existing failures block too" framing. |
| quality-gate-pipeline | N/A | N/A | N/A | 5 | 4 | 4 | 4 | 3 | "No regressions = count not decreasing" tolerates a standing red test. |
| test-driven-development | N/A | N/A | N/A | 5 | 4 | 2 | 4 | 3 | "All tests passing" but silent on failures the change didn't cause. |
| systematic-debugging | N/A | N/A | N/A | 5 | 5 | 4 | 4 | 3 | Phase 4 gates on full-suite-no-regressions; scoped to the one bug. |
| qa-engineer | N/A | N/A | N/A | 2 | 4 | 2 | 2 | 2 | Regression testing in scope but no whole-suite-green sign-off gate. |
| progress-guardian | N/A | N/A | N/A | 2 | 1 | N/A | 2 | 2 | Read-only: detects missing evidence but cannot run anything to verify it. |

## Evidence (selected, with file:line)

**Strengths to preserve**

- `systematic-debugging/SKILL.md:14` — "Iron Law: Find root cause before attempting
  fixes. Symptom fixes are failure." (ER/DD/DC)
- `quality-gate-pipeline/SKILL.md:69` — "Execute the command fresh and completely.
  Not from cache, not from memory." (ER/LV); `:89` "Inspect VCS diff independently —
  don't trust self-report." (ER)
- `build/SKILL.md:97` — "all tests must pass. Paste the passing output. Do NOT
  proceed without pasted passing output." (ER/DC)
- `test-driven-development/SKILL.md:14` — "No production code without a failing test
  first. If you didn't watch the test fail, you don't know if it tests the right
  thing." (ER/LV)
- `codebase-recon.md:154` — absorbs missing git history ("fills `git_history` with
  empty arrays + a note") and continues. (UA)
- `design-interrogation/SKILL.md:46` — "If the question can be answered by exploring
  the codebase, explore it yourself instead of asking the user." (CW/UA); `:79`
  every question carries a recommended answer. (CD)

**Gaps driving the plan**

- `human-oversight-protocol/SKILL.md:155` — "Medium: present options to human with
  recommendation." A reversible medium-severity decision should be
  investigated-and-decided with an override, not menu-ed. (CD/UA) — **highest leverage.**
- `product-manager.md` — no Clarification Window / discovery section anywhere; escalation
  criteria fire on conflict rather than directing mediation/investigation. (CW/UA/CD)
- `architect.md:10` — "before recommending an approach" — advice framing where the
  architect has authority to decide a reversible design. (CD)
- `build/SKILL.md:134-140` — escalation conditions ("after 3 attempts") with no named
  investigation/debugging step before handing back. (DD)
- `quality-gate-pipeline/SKILL.md:133` — exit criteria allow minor defects to be
  "logged" as if resolved. (DC)
- `qa-engineer.md:14` — evidence is written to files, not surfaced; no explicit
  "QA-complete = pasted passing evidence + named sign-off owner" gate. (ER/DC)
- `progress-guardian.md` — `tools: Read, Grep, Glob` only; can detect "marked complete
  without acceptance criteria verified" but cannot run the suite to confirm. (LV/DC)
- `orchestrator.md:279` — "Escalation criteria: Ambiguous requirements …" treated as a
  hand-off trigger rather than a dispatch-to-investigate trigger. (UA)

## Reading the baseline

Two clusters stand out:

1. **Discovery & decision subjects under-own the front of the loop.** PM, architect,
   orchestrator, and the oversight protocol are strong at *gating* but weak at
   *absorbing uncertainty and committing* — they route ambiguity to the human early.
   `design-interrogation` already encodes the right pattern; it just isn't wired into
   PM/architect, and the oversight protocol actively contradicts it at the Medium tier.

2. **The validation skills are the system's Ownership-Engineering exemplars.**
   `systematic-debugging`, `quality-gate-pipeline`, `build`, and `tdd` already enforce
   evidence and live validation hard. Their residual gaps are narrow: DD (debug rather
   than escalate-on-count) and DC (don't let "logged" mean "done"). The weak links on
   the back of the loop are `qa-engineer` (diffuse sign-off) and `progress-guardian`
   (can't execute).

The [improvement plan](../../plans/ownership-engineering-improvements.md) targets
cluster 1 first (highest leverage, lowest risk) and tightens cluster 2's two narrow
gaps.

## Re-score after implementation (Waves 1–3)

The plan's prose changes have been applied to the agents and skills. The table below
is the projected re-score, **hand-authored from the new prose** (same provenance
caveat as the baseline — it is not yet a measured judge run over the fixtures).
Changed cells are **bold**; the citation is the edit that moved them.

| Subject | CW | UA | CD | ER | LV | DD | DC | QO | What changed |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| orchestrator | 4 | **4** | 4 | 3 | 3 | 2 | 3 | N/A | Ambiguity is now a dispatch-to-investigate trigger before escalation (`orchestrator.md` Decision Making). |
| software-engineer | 2 | 4 | 4 | 4 | 3 | **4** | 3 | **4** | Inherits build/TDD's debug-before-escalate rule and the whole-suite quality-ownership gate. |
| product-manager | **4** | **4** | **3** | N/A | N/A | N/A | N/A | N/A | New Discovery (Clarification Window) section; escalation reframed to mediate-first (`product-manager.md`). |
| architect | 2 | 4 | **5** | N/A | N/A | N/A | 4 | N/A | Persona now "commit to a decision"; ADR-with-override for reversible choices (`architect.md`). |
| codebase-recon | N/A | 5 | 4 | 4 | N/A | N/A | 4 | N/A | unchanged (already exemplary). |
| human-oversight-protocol | 2 | **4** | **5** | N/A | N/A | N/A | N/A | N/A | Medium tier rewritten from "present options" to decide-and-proceed-with-override (`human-oversight-protocol.md:155`). |
| design-interrogation | 5 | 4 | 3 | N/A | N/A | N/A | N/A | N/A | unchanged. |
| build | N/A | N/A | N/A | 5 | 4 | **4** | 4 | **5** | Escalation now requires a systematic-debugging root cause first; whole-suite-green blocks `/pr` even for pre-existing failures (`build/SKILL.md`). |
| quality-gate-pipeline | N/A | N/A | N/A | 5 | 4 | 4 | **5** | **5** | Deferred ≠ resolved; whole-suite green required — a red test is failure regardless of whose change caused it (`quality-gate-pipeline.md` Phase 2). |
| test-driven-development | N/A | N/A | N/A | 5 | 4 | **4** | 4 | **4** | Unexplained failure routes to debugging; checklist now requires the whole suite green, not just touched tests. |
| systematic-debugging | N/A | N/A | N/A | 5 | 5 | **5** | 4 | 3 | Added the "Improve" step (capture the pattern) — closes the ownership loop. |
| qa-engineer | N/A | N/A | N/A | **4** | **5** | **4** | **4** | **5** | New evidence-backed Sign-off gate with a named owner; signs off on the whole suite green, not just changed tests. |
| progress-guardian | N/A | N/A | N/A | **3** | **3** | N/A | **3** | **3** | Verify-by-dispatch: flags missing evidence and names the validation to run (stays read-only). |

Quality Ownership (QO) is enforced cross-cutting in the always-loaded
`plugins/dev-team/CLAUDE.md` Quality & Accuracy section, so the principle reaches
every agent, not only the validation skills scored above.

**Result vs. the plan's Definition of Done:** no subject sits below 3 on any in-role
dimension; the human-oversight, PM, and qa-engineer rows have risen out of the 1–2
band. The `oe-08` `knownGap` sentinel is retired (the target behavior is now in the
prose). Confirming these projections requires a judge run over
`evals/ownership-engineering/fixtures/` — see the suite README for the procedure.
