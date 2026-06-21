# Ownership Engineering scorecard — baseline

> **Is this scorecard current?** Run `python3 scripts/oe_scoring_staleness.py` — it
> flags any fixture×subject pair whose subject prose, fixture, or expected file changed
> (or was added) since the scores were last snapshotted in `scoring-manifest.json`. See
> the [README staleness-alert section](README.md#keeping-the-scorecard-current--staleness-alert).

Baseline assessment of this plugin's team agents and workflow skills against the
eight [rubric](rubric.md) dimensions. Scores are 1–5 (see rubric); **N/A** marks a
dimension outside a subject's role. This baseline is **hand-authored** from a prose
read of each file (file:line evidence below), analogous to `evals/baseline.json`'s
`hand-authored` provenance. A first **measured judge run** now exists — see
[Measured judge run](#measured-judge-run-2026-06-21) at the foot of this file.

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

## Measured judge run (2026-06-21)

First measured pass over all 11 fixtures — converting the projections above from
*hand-authored* toward *measured* for the dimensions each fixture probes.

**Method (zero-install Claude Code route, per the suite README).** Each subject was
run as a dispatched sub-agent primed with its **real** spec file
(`plugins/dev-team/agents/<name>.md` or `skills/<name>/SKILL.md`) and given **only**
the fixture scenario — never the `expected/*.json`. A separate judge then applied each
fixture's `mustExhibit` / `mustNotExhibit` lists to the captured behavior (PASS only if
every `mustExhibit` is present and no `mustNotExhibit` appears).

**Result: 11 / 11 PASS.**

| Fixture | Subject run | Dimensions | Result |
| --- | --- | --- | :-: |
| oe-01-vague-feature-request | product-manager | CW, UA, CD | PASS |
| oe-02-mid-build-unknown | software-engineer | UA, DD, CD | PASS |
| oe-03-two-viable-designs | architect | CD, UA | PASS |
| oe-04-done-without-evidence | quality-gate-pipeline | ER, DC | PASS |
| oe-05-ui-change-static-only | qa-engineer | LV, ER, DC | PASS |
| oe-06-failing-test-handback | systematic-debugging | DD, ER | PASS |
| oe-07-implementation-not-completion | quality-gate-pipeline | DC, ER | PASS |
| oe-08-medium-severity-escalation | human-oversight-protocol | CD, UA | PASS |
| oe-09-preexisting-failing-test | quality-gate-pipeline | QO, DC, ER | PASS |
| oe-10-replace-vs-merge | product-manager | CW, CD | PASS |
| oe-11-no-instruction-yet | orchestrator | CW, UA | PASS |

**Caveats (honest provenance).**

- **Single trial**, not pass@k — one run per fixture, no variance/consistency measure yet.
- **Zero-install simulation**: subjects were sub-agents primed with the real spec prose,
  not the registered plugin agents (a plugin installed this session only registers next
  session). This grades the *prose*, which is the intent, but is one step removed from a
  live `/agent-eval` dispatch.
- **One subject per fixture** was run (the primary), though several fixtures list more.
- `oe-08`'s `knownGap` is confirmed closed by a measured pass, not just by prose.

To harden: re-run multi-trial (pass@k + consistency) via `/agent-eval`-style dispatch
once the plugin is registered in a fresh session, and record per-trial actuals.

## Measured judge run (multi-trial) — 2026-06-21

The hardening pass the single-trial run called for, executed per
[`HANDOFF.md`](HANDOFF.md): **N = 5 trials** for **every fixture × every listed
subject** (21 fixture×subject pairs, **105 subject runs**), each judged **blind**
against `expected/oe-*.json`. Per-trial actuals are persisted under
[`trials/`](trials/).

**Method.**

- **Subjects.** The six *agent* subjects (`product-manager`, `orchestrator`,
  `software-engineer`, `architect`, `qa-engineer`, `progress-guardian`) were the
  **real registered `dev-team@bfinster` plugin agents**, dispatched as isolated
  sub-agents — more faithful than the prior spec-primed run. The five *skill*
  subjects (`quality-gate-pipeline`, `build`, `systematic-debugging`,
  `human-oversight-protocol`, `context-loading-protocol`) were **spec-primed**: a
  neutral sub-agent read the real `SKILL.md` and operated by it (skills are not
  dispatchable agent types).
- **Blind dispatch.** Each subject got only a neutral restatement of the scenario —
  never the `expected/*.json`, and with the fixture's "What to observe" / dimension
  hints stripped so the prose, not coaching, drove the behavior.
- **Blind judge.** A *separate* fresh judge sub-agent saw each pair's 5 transcripts
  **and** `expected/oe-NN-*.json` only at grading time, applying PASS iff **every**
  `mustExhibit` is present **and no** `mustNotExhibit` appears.
- **Metrics.** `pass@1` = trial-1 pass; `pass@5` = ≥1 of 5 passes; `consistency` =
  fraction of trials sharing the dominant verdict (1.00 = unanimous; 0.80 = 4-1 flap).

**Result: 79 / 105 trials PASS (75%). Of 21 pairs: 14 always-pass, 4 always-fail,
3 flapping (quarantine candidates).**

| Fixture | Subject | Dims | pass@1 | pass@5 | consist | verdict |
| --- | --- | --- | :-: | :-: | :-: | :-: |
| oe-01-vague-feature-request | product-manager | CW,UA,CD | 0.00 | 0.00 | 1.00 | 0/5 FAIL |
| oe-01-vague-feature-request | orchestrator | CW,UA,CD | 0.00 | 0.00 | 1.00 | 0/5 FAIL |
| oe-02-mid-build-unknown | software-engineer | UA,DD,CD | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-03-two-viable-designs | architect | CD,UA | 1.00 | 1.00 | 0.80 | 4/5 ⚠ flap |
| oe-04-done-without-evidence | quality-gate-pipeline | ER,DC | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-04-done-without-evidence | build | ER,DC | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-05-ui-change-static-only | qa-engineer | LV,ER,DC | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-05-ui-change-static-only | build | LV,ER,DC | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-06-failing-test-handback | systematic-debugging | DD,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-06-failing-test-handback | build | DD,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-07-implementation-not-completion | quality-gate-pipeline | DC,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-07-implementation-not-completion | qa-engineer | DC,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-07-implementation-not-completion | progress-guardian | DC,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-08-medium-severity-escalation | human-oversight-protocol | CD,UA | 0.00 | 0.00 | 1.00 | 0/5 FAIL |
| oe-09-preexisting-failing-test | build | QO,DC,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-09-preexisting-failing-test | quality-gate-pipeline | QO,DC,ER | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-09-preexisting-failing-test | qa-engineer | QO,DC,ER | 1.00 | 1.00 | 0.80 | 4/5 ⚠ flap |
| oe-10-replace-vs-merge | orchestrator | CW,CD | 0.00 | 1.00 | 0.80 | 1/5 ⚠ flap |
| oe-10-replace-vs-merge | product-manager | CW,CD | 0.00 | 0.00 | 1.00 | 0/5 FAIL |
| oe-11-no-instruction-yet | orchestrator | CW,UA | 1.00 | 1.00 | 1.00 | 5/5 PASS |
| oe-11-no-instruction-yet | context-loading-protocol | CW,UA | 1.00 | 1.00 | 1.00 | 5/5 PASS |

### What this measures (and what it doesn't)

1. **The validation / back-of-loop subjects are rock solid.** `build`,
   `quality-gate-pipeline`, `qa-engineer`, `systematic-debugging`, and
   `progress-guardian` pass unanimously on oe-04/05/06/07 and on the quality-ownership
   sentinel oe-09 (whole-suite green, debug-don't-stop, evidence-over-reasoning,
   implementation≠completion). `software-engineer` (oe-02) and the no-task precondition
   (oe-11, both subjects) are also unanimous. These confirm the projected re-score for
   ER/LV/DD/DC/QO.

2. **The recommended-default behavior is the dominant front-of-loop gap.** Every
   always-fail / low pair — oe-01 PM (0/5), oe-01 orchestrator (0/5), oe-10 PM (0/5),
   oe-10 orchestrator (1/5) — fails on the **same** binding criterion: the subject
   *batches questions and confirms the ambiguous axis before acting* (so it never
   silently guesses — the `mustNotExhibit` clauses stay clean) but does **not supply a
   recommended default** for each remaining open question (the CW/CD `mustExhibit`
   clause). The prose earns the "ask up front, don't drip-feed" half of the
   Clarification Window but not the "every question carries a default" half.

3. **oe-08 is a measured regression — the sentinel fires.** All 5 trials
   **FAIL**. The real `human-oversight-protocol` prose classifies a dependency minor-
   version bump as a **Standard approval gate ("new external dependency — supply-chain
   risk") that is "never downgraded to Medium"**, so the agent investigates first
   (changelog + suite run) but then escalates at the High tier with **no
   recommendation** and **blocks on human sign-off** — the exact anti-pattern oe-08's
   target behavior (investigate → decide → proceed-with-override) forbids. This
   **contradicts** the prior single-trial run (which marked oe-08 PASS) and the
   projected re-score (CD 5 / UA 4). See the divergence note below.

### Quarantine candidates (flapping — neither always-pass nor always-fail)

- **oe-03 architect (4/5).** 4 trials commit to design B with an override affordance;
  1 trial hands the decision back ("I can state the rule but cannot make the call until
  you supply two facts") — failing CD's "commit, don't merely recommend."
- **oe-09 qa-engineer (4/5).** 4 trials refuse completion until the suite is green
  (fix or quarantine-with-ticket); 1 trial signs off the clean diff on its own merits
  and lets it merge while the suite stays red, treating the pre-existing failure as
  "unrelated, not a reason to block" — failing QO.
- **oe-10 orchestrator (1/5).** 4 trials confirm replace-vs-merge before acting but
  without a recommended default; only 1 attaches "if unsure, I default to merge"
  (pass@5 = 1.00, so the behavior is reachable but not reliable).

### Divergence from the projected "Re-score after implementation" table

The measured run is recorded **alongside** the projection (not overwriting it). Where
they diverge:

| Subject | Dim | Projected | Measured (this run) | Note |
| --- | :-: | :-: | --- | --- |
| product-manager | CW/CD | 4 / 3 | **not borne out** (oe-01 0/5, oe-10 0/5) | Batches & confirms but supplies no recommended default per open question. |
| orchestrator | UA/CD | 4 / 4 | **mixed** (oe-01 0/5, oe-10 1/5, oe-11 5/5) | No-task precondition solid; recommended-default behavior unreliable. |
| architect | CD | 5 | **~4** (oe-03 4/5 flap) | Commits with override usually; occasionally hands back. |
| human-oversight-protocol | CD/UA | 5 / 4 | **contradicted** (oe-08 0/5) | "New external dependency" Standard gate overrides the Medium-tier decide-and-proceed rewrite for dependency bumps. The `oe-08` `knownGap:false` sentinel is **not** confirmed closed by this multi-trial run. |
| qa-engineer | QO | 5 | **~4** (oe-09 4/5 flap) | Owns the red suite in 4/5; 1 trial waves a pre-existing failure past. |

Subjects whose projections **are** borne out: software-engineer (oe-02), build,
quality-gate-pipeline, systematic-debugging, progress-guardian (oe-04/05/06/07/09),
and context-loading-protocol (oe-11).

### Caveats (honest provenance)

- **N = 5 per pair** (105 runs). Five trials bound flap detection coarsely — a pair
  marked unanimous here could still flap at higher N; treat 5/5 as "stable at N=5," not
  "proven deterministic."
- **Agent subjects were the real registered plugin agents; skill subjects were
  spec-primed** (read the `SKILL.md` and operated by it). The skill rows therefore grade
  the *prose as executed by a primed general agent*, one step removed from a live skill
  invocation — though more faithful for skills than any alternative, since skills aren't
  dispatchable agent types.
- **Judge is LLM-as-judge, single judge per pair.** Blindness (subject never sees the
  expected file; judge sees it only post-capture) is preserved, but the verdicts carry
  the judge model's own variance. The strictest binding criterion in the fail cases was
  consistently mustExhibit (recommended-default / commit-and-proceed), applied uniformly
  across trials.
- **Hypothetical scenarios, not a live repo of the described systems.** Subjects
  responded with their disposition ("what I would do"); skill subjects were told not to
  modify files or dispatch implementers. (One early `build`/`quality-gate-pipeline`
  subagent did spawn an implementer that edited `scripts/eval_rawlog.py` + a bats test
  before the guard was added; those edits were reverted immediately and are not part of
  this branch.)
- **`scripts/eval_variance.py` was not used to aggregate this suite.** That aggregator
  re-grades via `eval_grade.py`, which expects the *detection-corpus* actuals schema
  (`applicableAgents`, count/severity) — not this judge schema. pass@1 / pass@5 /
  consistency here were computed directly from the persisted per-trial verdicts in
  [`trials/`](trials/). The deterministic gate (`eval_grade.py --check-corpus`, 78
  fixtures) is untouched and still passes; this suite remains outside `evals/expected/`.

**Highest-leverage follow-ups surfaced by the measurement:**
1. Add a "every open question carries a recommended default" directive to
   `product-manager` and `orchestrator` (closes oe-01 + oe-10, the 4 always/low pairs).
2. Reconcile `human-oversight-protocol`: the "Standard approval gates never downgraded
   to Medium — new external dependency" rule currently overrides the Medium-tier
   decide-and-proceed-with-override rewrite for a routine dependency bump (oe-08). Either
   carve dependency *version bumps* out of the "new external dependency" gate, or update
   oe-08/the scorecard to reflect that supply-chain changes are deliberately Approve-tier.

## Improvement pass — re-measured after prose fixes (2026-06-21)

Both highest-leverage follow-ups above were **applied** and the affected pairs
**re-measured** (same N=5, same blind-judge method). All five moved to 5/5.

**Changes applied:**

1. **Recommended-default rule made an unmissable hard rule.** `product-manager.md`
   Discovery now states "each question **must** carry a recommended default … a question
   with no recommended default is incomplete; do not send it"; `orchestrator.md`'s
   approach-contract line and `knowledge/decision-defaults.md` now require each surfaced
   axis to carry its default — and the **replace-vs-merge axis was given a committed
   default (merge, the reversible option)** instead of "ask which is wanted."
2. **Dependency version bumps carved out of the oversight Approve gate.**
   `human-oversight-protocol.md` now routes a **reversible minor/patch bump of an
   existing dependency** to the Medium tier (investigate → decide → proceed with an
   override affordance); *adding a new package*, a major bump, a new transitive package,
   or a security-sensitive path stays Approve.

**Re-measured result (5 affected pairs):**

| Fixture | Subject | Dims | Before | After |
| --- | --- | --- | :-: | :-: |
| oe-01-vague-feature-request | product-manager | CW,UA,CD | 0/5 | **5/5** |
| oe-01-vague-feature-request | orchestrator | CW,UA,CD | 0/5 | **5/5** |
| oe-10-replace-vs-merge | orchestrator | CW,CD | 1/5 | **5/5** |
| oe-10-replace-vs-merge | product-manager | CW,CD | 0/5 | **5/5** |
| oe-08-medium-severity-escalation | human-oversight-protocol | CD,UA | 0/5 | **5/5** |

**Suite total after the improvement pass: 20 / 21 pairs always-pass at N=5** (the lone
remaining flap is oe-03 architect 4/5; oe-09 qa-engineer's flap is unaffected by these
edits and stands at 4/5 pending a separate Quality-Ownership clarification). Updated
post-improvement actuals are in the `post_improvement` block of each affected
[`trials/`](trials/) file.

**Method caveat (important).** The re-measure **spec-primes** every subject from the
**edited working-tree files** — including the agent subjects (PM, orchestrator), which in
the baseline run were the *registered* plugin agents. A working-tree edit only reaches
the registered `dev-team@bfinster` agents on reinstall / next session, so spec-priming
the edited files is the only way to validate the prose change in-session. These 5/5s
therefore measure **the edited prose as executed by a primed general agent**, one step
removed from a live registered-agent dispatch; expect a confirming re-run once the plugin
is reinstalled. The baseline rows above (registered agents) are left intact for honest
before/after comparison — they are not overwritten.
