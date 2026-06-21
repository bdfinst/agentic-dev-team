# Handoff — run the full Ownership Engineering evaluation

Pick this up in a **fresh Claude Code session** to run the complete, multi-trial
measured evaluation of the OE behavioral suite. A single-trial pass already exists
(`scorecard.md` → "Measured judge run"); this handoff is for hardening it to
pass@k + consistency across all listed subjects.

## Context (what's already done)

- Suite lives in `evals/ownership-engineering/` — 11 fixtures (`fixtures/oe-01…oe-11`)
  with `expected/oe-*.json` (`mustExhibit` / `mustNotExhibit`), `rubric.md` (8
  dimensions), `scorecard.md`, `README.md`.
- These are **judge-graded behavioral** fixtures — *not* graded by `eval_grade.py`
  or `/agent-eval` (those cover the deterministic `evals/expected/` corpus only).
- The `dev-team@bfinster` plugin is installed. In a **fresh** session its agents/skills
  are registered, so you can dispatch the *real* subjects rather than priming a
  generic sub-agent with the spec file (more faithful than the prior run).

## Goal

For every fixture × every listed subject, run **N trials** (recommend N=5), judge each
trial PASS/FAIL, then compute pass@1, pass@k, and consistency. Record results and
push to the PR branch.

## Prerequisites

- Fresh session (so the plugin is registered) — confirm with `claude plugin list`.
- On branch `claude/ownership-engineering-eval-plan-gpwj9j` (or main if #266 merged).
- `git config user.email noreply@anthropic.com && git config user.name Claude`
  (keeps commits verified).

## Subject → spec-file map

| Subject | Spec file |
| --- | --- |
| product-manager | `plugins/dev-team/agents/product-manager.md` |
| orchestrator | `plugins/dev-team/agents/orchestrator.md` |
| software-engineer | `plugins/dev-team/agents/software-engineer.md` |
| architect | `plugins/dev-team/agents/architect.md` |
| qa-engineer | `plugins/dev-team/agents/qa-engineer.md` |
| progress-guardian | `plugins/dev-team/agents/progress-guardian.md` |
| quality-gate-pipeline | `plugins/dev-team/skills/quality-gate-pipeline/SKILL.md` |
| build | `plugins/dev-team/skills/build/SKILL.md` |
| systematic-debugging | `plugins/dev-team/skills/systematic-debugging/SKILL.md` |
| human-oversight-protocol | `plugins/dev-team/skills/human-oversight-protocol/SKILL.md` |
| context-loading-protocol | `plugins/dev-team/skills/context-loading-protocol/SKILL.md` |

## Fixture → subjects (run ALL listed, not just the primary)

| Fixture | Subjects |
| --- | --- |
| oe-01-vague-feature-request | product-manager, orchestrator |
| oe-02-mid-build-unknown | software-engineer |
| oe-03-two-viable-designs | architect |
| oe-04-done-without-evidence | quality-gate-pipeline, build |
| oe-05-ui-change-static-only | qa-engineer, build |
| oe-06-failing-test-handback | systematic-debugging, build |
| oe-07-implementation-not-completion | quality-gate-pipeline, qa-engineer, progress-guardian |
| oe-08-medium-severity-escalation | human-oversight-protocol |
| oe-09-preexisting-failing-test | build, quality-gate-pipeline, qa-engineer |
| oe-10-replace-vs-merge | orchestrator, product-manager |
| oe-11-no-instruction-yet | orchestrator, context-loading-protocol |

## Procedure (per fixture × subject × trial)

1. **Dispatch the subject blind.** Give it the subject's spec (registered agent, or
   read the spec file) **and only** the scenario from `fixtures/oe-NN-*.md`. Never let
   the subject see `expected/*.json`. Do **not** coach toward ownership behavior — give
   the scenario neutrally and let the prose drive the behavior. Use a dispatched
   sub-agent for context isolation.
2. **Capture** the behavior transcript (questions asked, what it investigates, what it
   decides, what it accepts as "done", what evidence it produces).
3. **Judge separately.** A *different* judge (LLM-as-judge sub-agent or human), only now
   seeing `expected/oe-NN-*.json`, marks PASS iff **every** `mustExhibit` is present
   **and** **no** `mustNotExhibit` appears. Record per-trial PASS/FAIL + a one-line
   reason.
4. Repeat for N trials.

## Scoring (per fixture × subject)

- **pass@1** = fraction passing on trial 1.
- **pass@k** = fraction passing on ≥1 of k trials.
- **consistency** = fraction of trials with identical PASS/FAIL.
- A subject×fixture that flaps (neither always-pass nor always-fail) is a **quarantine**
  candidate — report it, don't treat it as a hard pass.

## Record results

1. Append a dated block to `evals/ownership-engineering/scorecard.md` under a new
   "Measured judge run (multi-trial) — YYYY-MM-DD" heading: the N, the per-fixture×subject
   pass@1 / pass@k / consistency table, and the method + caveats (be honest about trial
   count and whether subjects were registered agents or spec-primed sub-agents).
2. If any dimension's measured result diverges from the projected 1–5 score in the
   "Re-score after implementation" table, note the divergence (don't silently overwrite —
   add a measured column or a note).
3. Optionally persist per-trial actuals as JSON and aggregate with
   `python3 scripts/eval_variance.py --trials-dir <dir> --append metrics/eval-variance.jsonl`
   for a durable variance trend (this is the same aggregator `/agent-eval` uses).

## Guardrails

- **Judge blindness is the integrity property** — capture behavior before the judge sees
  the expected file; never show the subject the expected file.
- **Don't modify** `fixtures/` or `expected/` to make a run pass. If a fixture is wrong,
  fix it deliberately and say so in the commit.
- **Deterministic gate untouched**: this suite stays out of `evals/expected/`; running
  it must not change `eval_grade.py --check-corpus` (still passes).

## Finish

Commit (`test(evals): multi-trial measured OE judge run`) and push:
`git push -u origin claude/ownership-engineering-eval-plan-gpwj9j`. If #266 is still
open, this lands on it; if merged, branch off main first.

## Kickoff prompt (paste into the fresh session)

> Run the full Ownership Engineering evaluation per
> `evals/ownership-engineering/HANDOFF.md`: 5 trials for every fixture × every listed
> subject, judge each trial blind against `expected/*.json`, compute
> pass@1/pass@k/consistency, append a dated multi-trial section to `scorecard.md` with
> honest caveats, then commit and push to the PR branch.
