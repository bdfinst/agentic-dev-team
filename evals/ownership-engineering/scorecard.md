# Ownership Engineering scorecard — baseline

Baseline assessment of this plugin's team agents and workflow skills against the
seven [rubric](rubric.md) dimensions. Scores are 1–5 (see rubric); **N/A** marks a
dimension outside a subject's role. This baseline is **hand-authored** from a prose
read of each file (file:line evidence below), analogous to `evals/baseline.json`'s
`hand-authored` provenance — it is not yet a measured judge run over the fixtures.

Dimensions: **CW** Clarification Window · **UA** Uncertainty Absorption ·
**CD** Committed Decisions · **ER** Evidence over Reasoning · **LV** Live Validation
· **DD** Debug-Don't-Stop · **DC** Demonstrable Completion.

## Scores

| Subject | CW | UA | CD | ER | LV | DD | DC | Notes |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| orchestrator | 4 | 2 | 4 | 3 | 3 | 2 | 3 | Phases gate well; escalates ambiguity instead of dispatching investigation. |
| software-engineer | 2 | 4 | 4 | 4 | 3 | 3 | 3 | Owns implementation; no upfront discovery, escalates per-conflict. |
| product-manager | 1 | 2 | 2 | N/A | N/A | N/A | N/A | No discovery phase; escalates stakeholder conflicts rather than mediating. |
| architect | 2 | 4 | 3 | N/A | N/A | N/A | 4 | Reasons in trade-offs but "recommends" rather than deciding. |
| codebase-recon | N/A | 5 | 4 | 4 | N/A | N/A | 4 | Exemplary: absorbs incomplete data, emits a contract-conformant artifact. |
| human-oversight-protocol | 2 | 1 | 2 | N/A | N/A | N/A | N/A | Medium tier mandates "present options" — the central anti-ownership gap. |
| design-interrogation | 5 | 4 | 3 | N/A | N/A | N/A | N/A | Excellent batched discovery; surfaces decisions but the user still decides. |
| build | N/A | N/A | N/A | 5 | 4 | 2 | 4 | Strong paste-output gates; escalates after N attempts with no debug protocol. |
| quality-gate-pipeline | N/A | N/A | N/A | 5 | 4 | 4 | 4 | "Verify don't assume"; softens DC by letting minor defects be "logged." |
| test-driven-development | N/A | N/A | N/A | 5 | 4 | 2 | 4 | Iron law + watch-it-fail; red flags say "restart," not "debug." |
| systematic-debugging | N/A | N/A | N/A | 5 | 5 | 4 | 4 | The model citizen for ER/LV/DD; lacks a cross-bug learning loop. |
| qa-engineer | N/A | N/A | N/A | 2 | 4 | 2 | 2 | No explicit evidence-paste sign-off gate; ownership of "done" is diffuse. |
| progress-guardian | N/A | N/A | N/A | 2 | 1 | N/A | 2 | Read-only: detects missing evidence but cannot run anything to verify it. |

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
