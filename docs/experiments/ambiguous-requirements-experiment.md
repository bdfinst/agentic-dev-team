# Experiment Spec: Does TDD Pay Off When Requirements Are *Unclear*?

**Type:** Experiment design / reusable prompt (not yet run).
**Status:** Proposed. Specs the follow-up flagged in
[`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md) (Limitations).
**Harness:** extends [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py).
**Builds on:** [`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md).

---

## Motivation

The TDD-vs-non-TDD study found **no output advantage** for test-first — but it
held requirements **clear, complete, and frozen** (an unambiguous `spec.md` plus
hidden acceptance tests as an objective oracle). That design controls away TDD's
single most-claimed benefit: that **writing a failing test first forces you to
commit to a concrete interpretation of vague requirements, surfacing edge cases
and contradictions before you implement them.** This experiment removes the
clear-requirements assumption and measures whether test-first then diverges from
test-after.

## Hypothesis

**H1 (interaction).** Requirement clarity moderates the workflow effect. Under
**under-specified** requirements, test-first achieves **higher correctness on the
unstated edge cases** than test-after; under **clear** requirements (the prior
study) there is no such gap. Formally, a `workflow × clarity` interaction on
edge-case correctness.

**H0 (null).** Vagueness degrades both arms equally — no interaction. Test-first's
"red test surfaces ambiguity" benefit does not materialize for an autonomous agent
(plausible failure mode: test-first simply **tests its own happy-path
interpretation**, locking in the wrong guess just as firmly as test-after).

Either result is publishable; the null is itself informative about agentic TDD.

## Core idea: hold the *contract* fixed, vary only what the agent is *told*

The hidden acceptance tests **stay identical** to the clear-requirements study —
the ground-truth contract does not change. Only the **spec the agent reads**
changes: a vague variant **omits the very decisions the acceptance tests check**
(empty-input behavior, tie-breaking, error-vs-sentinel, case sensitivity,
rounding, ordering, bounds). An arm that infers those unstated decisions
*correctly* passes; one that guesses wrong fails. This isolates **contract
inference under ambiguity**.

## Design

**2 × 2 factorial**, paired by task:

| | **clear spec** | **vague spec** |
|---|---|---|
| **test-first** | *(reuse prior data)* | new |
| **test-after** | *(reuse prior data)* | new |

- The two **clear** cells already exist (`3sizes-*` data). Only the two **vague**
  cells are run new.
- The primary contrast is **test-first vs test-after under the vague spec**,
  paired across tasks; the interaction is read against the clear baseline.
- Model **fixed** (`claude-sonnet-4-6`), same as the parent study.

## The new instrument: split acceptance into CORE vs EDGE

Each task's hidden acceptance is partitioned into two graded files:

- `acc_core.py` — assertions for behavior **stated even in the vague spec** (the
  happy path). Both arms should pass these; a floor/sanity check.
- `acc_edge.py` — assertions for the **omitted/ambiguous decisions** (empty input,
  ties, errors, case, rounding, ordering). **This is the primary endpoint.**

`acc_core ∪ acc_edge` must equal the original clear-spec acceptance, so the
total contract is unchanged — it is only re-partitioned.

## Primary & secondary endpoints

1. **EDGE-subset pass rate** (primary), paired test-first vs test-after under
   vague, across tasks (exact sign + Wilcoxon). *Does test-first infer unstated
   edge behavior better?*
2. **CORE pass rate** (control) — expected ≈100% both arms; if it drops, the vague
   spec is too vague (broke the happy path), not just ambiguous.
3. **Interpretation variance across trials** — for each (task, arm), how many
   *distinct* edge-case behaviors appear across the N trials (e.g., does
   `empty → []` vs `raise` vary run-to-run?). Hypothesis: test-first **converges**
   more (lower variance) because the up-front test pins the choice.
4. **Cost / turns / rework** — does test-first cost *more* under ambiguity (extra
   spec-pinning iterations) or *less* (fewer wrong-path rewrites)?
5. **Assumption surfacing** (exploratory) — count explicit "I'm assuming X"
   statements or self-authored tests that target an unstated edge. A mechanism
   probe for *why* any H1 effect occurs.

## Optional third arm — TDD with a clarification oracle

A realistic TDD workflow lets the developer *ask*. Add `test-first-clarify`: the
agent may emit up to **k** clarifying questions; an **oracle auto-answers** them
from the clear spec (the harness greps the question, returns the relevant clear-
spec line). This tests "test-first **+** the ability to ask," which is closer to
how TDD surfaces ambiguity in practice, and separates "test-first thinks harder"
from "test-first asks better questions." Headless and reproducible because the
oracle is deterministic. Run only if the 2×2 shows a signal worth decomposing.

## Authoring the vague specs (the craft step)

For each existing task, write `spec_vague.md` that is **genuinely buildable but
under-specified**:

- Keep a one–three sentence **goal** and the public API surface (names/arity), so
  the task is still well-formed and `acc_core` is reachable.
- **Delete every enumerated scenario and every edge-case decision** that
  `acc_edge` checks. Do not hint at the answer.
- Do **not** introduce contradictions or impossibilities — the ambiguity must be
  *unstated decisions*, not *broken requirements*. A competent dev could ship a
  reasonable (possibly wrong-per-oracle) implementation.
- Calibrate vagueness: pilot one task and confirm `acc_core` is ~always passable
  and `acc_edge` is *sometimes* missed (if edge is always passed, the spec leaked
  the answer; if never passed, it's unbuildable).

Reuse the existing tasks; large multi-file tasks are the richest (more
unstated-decision surface). Suggested starting set: the 6 large tasks, plus 3–4
medium for a clarity gradient.

## Harness changes required

1. **Per-cell spec selection.** Add a `specVariant`/`spec` override so a fixture
   can point at `spec_vague.md` while keeping the same `goldenRepo`. Simplest:
   parallel experiment manifests `evals/experiments/exp-amb-<task>.json` that set
   `"spec": "spec_vague.md"` and `"gradeFiles": ["acc_core.py","acc_edge.py"]`.
2. **Per-file grade results.** The runner already records per-command exit codes;
   ensure `acc_core.py` and `acc_edge.py` are graded and reported **separately**
   (they are distinct `testCommands`, so this is already supported — the analyzer
   just needs to read them as two endpoints).
3. **Interpretation-variance capture.** Optionally snapshot each cell's behavior
   on a fixed probe vector (run a small `probe.py` that prints the arm's answers
   to the ambiguous inputs) so variance across trials is computed from observed
   behavior, not just pass/fail.
4. **(Optional) clarification oracle.** A deterministic Q→A responder injected
   into the `test-first-clarify` dispatch; out of scope unless the 2×2 fires.

No change to isolation, cost capture, or the timeout fix already landed.

## Pre-registration

- **Primary:** EDGE-subset pass rate, test-first − test-after under vague, paired
  across tasks; exact sign + Wilcoxon; one-sided in the TDD-favorable direction
  pre-declared, two-sided reported alongside.
- **Trials:** N=3 per (task × arm × clarity), as in the parent study.
- **Decision rule for H1:** test-first beats test-after on EDGE pass in ≥ a
  pre-set majority of tasks *and* the clear-spec cells show no such gap
  (interaction), with CORE pass ≈100% (vagueness didn't break the happy path).
- **Stopping rule:** run the pre-registered N; no peeking-based stopping.

## Threats to validity (call them before running)

- **Happy-path lock-in.** Autonomous test-first may just encode its own guess as a
  passing test — the variance and edge endpoints are designed to expose this.
- **Vagueness calibration.** Too vague breaks `acc_core` (confounds "ambiguous"
  with "impossible"); too mild leaks the answer (no edge misses). Pilot-gate every
  task on the core-always / edge-sometimes criterion above.
- **Oracle leakage** (clarify arm). The Q→A responder must answer *only* what was
  asked, from the clear spec, without volunteering — else it hands over the
  contract.
- **Grader independence.** `acc_edge` must not be inferable from `acc_core` or the
  golden-repo stubs; keep it hidden exactly as in the parent study.

## Expected deliverables

- `evals/fixtures/exp-tdd-<task>/spec_vague.md`, `acc_core.py`, `acc_edge.py` for
  each task in the set (acc files validated against a reference solution, as in the
  parent study).
- `evals/experiments/exp-amb-<task>.json` manifests.
- Raw JSONL under `docs/experiments/data/`, analyzed into a `clarity × workflow`
  grid with the EDGE-pass primary endpoint and the interpretation-variance
  secondary.
- A report: does test-first’s value appear once requirements stop being handed to
  it on a plate?
