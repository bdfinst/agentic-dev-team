# Pilot Report: Test-First (TDD) vs. Test-After Workflow

**Status:** Superseded by
[`tdd-vs-test-after-campaign-report.md`](tdd-vs-test-after-campaign-report.md)
(6-task campaign with test-quality sensors). Kept for history.
**Original status:** Pilot complete — directional only, not statistically powered
**Date:** 2026-06-21
**Design:** [`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md)
**Raw data:** [`data/tdd-pilot-2026-06-21.jsonl`](data/tdd-pilot-2026-06-21.jsonl)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)

## TL;DR

A 16-dispatch pilot ran both workflows against two tasks, each with a withheld
follow-up change. Every cell passed its hidden acceptance suite (16/16) with zero
contamination. The one **consistent** signal: **test-first was cheaper on the
change (Stage 2) for both tasks** — the "easy to change" axis — by 15–24%. Build
and total cost were **mixed** (test-first won one task, test-after the other).

**This is a pilot (N = 2 tasks × 2 trials).** It validates the harness and gives
direction; it is far below the ~8-task × ~6-trial scale the design calls for, so
**no inferential claim is made.**

## Methodology

### Question

Does the test-first workflow produce cheaper, better-tested, easier-to-change
code than writing tests at the end, for small testable features?

### Design

Paired, two-arm, repeated-trial, two-stage (full design in the linked doc).

- **Arms** (only variable = *when* tests are written):
  - **test-first** — prompt mandates strict RED → GREEN → REFACTOR.
  - **test-after** — prompt mandates all production code first with **no** test
    files, then a test suite at the end covering the same criteria.
- **Two stages per task**: **Stage 1 (build)** implements from a frozen `spec.md`;
  **Stage 2 (change)** applies a **withheld** `change.md` on top of the Stage-1
  output. Stage-2 cost is the changeability signal.
- **Tasks** (`evals/fixtures/exp-tdd-*`):
  - `word-tally` — `word_count(text)` → withheld `top_n(text, n)`.
  - `roman` — `to_roman(n)` (1–3999) → withheld `from_roman(s)` round-trip.
- **Trials:** 2 per (task × arm). **Model:** `claude-haiku-4-5` (held constant).
- **Cells:** 2 tasks × 2 arms × 2 trials × 2 stages = **16 dispatches**.

### Isolation (verified, zero contamination)

Each cell ran in its own ephemeral git worktree **and** its own scratch
`$HOME`/`CLAUDE_CONFIG_DIR`, dispatched as a fresh `claude -p` (no session resume).
Stage 2 was seeded from the Stage-1 **files only** — it saw the code but none of
the build's reasoning, so changeability is measured, not memory. All 16 rows
carry an empty `contamination[]` (no dispatch errors, no turn-count blow-ups).

### Hidden acceptance tests (fairness)

Acceptance suites were **withheld from the worktree during the build** and injected
only at grading time (`gradeFiles` / `changeGradeFiles`). Neither arm could simply
satisfy a given test; each had to author its own tests against the prose spec. The
graded suite then judged real behavior. Both arms wrote tests (`agent_test_files`
= 2–3 in every cell), confirming the manipulation held.

### Metrics captured

- **Cost / tokens / turns** — verified from `claude -p --output-format json`
  (`total_cost_usd`, usage, `num_turns`). The plugin cost-meter hook does **not**
  fire in a nested dispatch, so the native result object is the source of truth.
- **Pass/fail** — model-free: hidden acceptance commands must exit 0.
- **Manipulation check** — count of agent-authored test files.

### Not captured in this pilot (limitations, see below)

Coverage %, mutation score, and Farley Score were **not** wired in — the
"fully tested" axis is approximated here by *pass@acceptance* + *test-file
presence* only. `cost_usd` (real dollars) is the primary metric; `tokens_total`
includes cache reads and is secondary.

## Results

### Per task × arm (median of 2 trials)

| Task | Arm | Build $ | Change $ | **Total $** | Build turns | Change turns |
|---|---|---|---|---|---|---|
| roman | test-first | 0.2084 | 0.0779 | **0.2863** | 27.5 | 15.0 |
| roman | test-after | 0.2552 | 0.1027 | **0.3579** | 29.5 | 15.5 |
| word-tally | test-first | 0.1864 | 0.0624 | **0.2487** | 26.5 | 13.0 |
| word-tally | test-after | 0.1586 | 0.0735 | **0.2321** | 22.0 | 13.0 |

### Paired comparison (test-first − test-after, median totals)

| Task | TF total $ | TA total $ | Δ total | TF change $ | TA change $ | Δ change |
|---|---|---|---|---|---|---|
| roman | 0.2863 | 0.3579 | **−0.0716** (TF cheaper) | 0.0779 | 0.1027 | **−24%** |
| word-tally | 0.2487 | 0.2321 | +0.0167 (TA cheaper) | 0.0624 | 0.0735 | **−15%** |

- **Pass rate:** 16/16 (100%) — both workflows produced correct code on both
  tasks and both changes.
- **Change stage:** test-first cheaper on **both** tasks (−24%, −15%).
- **Total / build:** **mixed** — test-first won `roman` decisively; test-after
  won `word-tally` (driven by a more expensive test-first build there).

## Interpretation (directional)

Applying the design's pre-registered decision rule (§7) honestly: it is **not
satisfied** — test-first did not achieve ≤ total cost on *every* task (it lost on
`word-tally`). So at this scale the verdict is the **trade-off outcome the design
anticipated as most likely**: the test-first advantage concentrates in
**changeability** (cheaper Stage-2 on both tasks), not in up-front build cost.
That is consistent with the hypothesis that test-first code is easier to change —
but two tasks cannot distinguish a real effect from task-to-task noise.

The "fully tested" axis is **inconclusive** here: both arms passed identical
hidden suites and wrote a similar number of tests, and no mutation/coverage sensor
ran to separate assertion strength.

## Validity & limitations

1. **Underpowered** — N = 2 tasks × 2 trials. The design calls for ~8 tasks × ~6
   trials with the **task** as the unit of inference; nothing here supports a
   p-value. Directional only.
2. **Model = haiku-4.5** — chosen to bound pilot cost/time. TDD's benefits may
   scale differently on a stronger model; the campaign should fix one model and
   report it.
3. **Instruction-level TDD, not `/build`** — each cell ran in an isolated `$HOME`
   without the plugin, so "test-first" was enforced by prompt, not by the
   plugin's RED-GREEN-REFACTOR gates. Testing the *actual `/build` pipeline* needs
   per-cell plugin activation — a documented follow-up.
4. **Quality sensors absent** — coverage/mutation/Farley not wired, and worktrees
   are torn down after grading, so no post-hoc analysis of the produced code.
5. **Tiny tasks** — both are single-function katas; they may be too small for
   changeability differences to fully surface (the design wants ≥ 5–8 scenarios).
6. **Single environment / single day** — no cross-environment replication.

## Reproducibility

```bash
python3 scripts/run_tdd_experiment.py \
  --only exp-tdd-word-tally,exp-tdd-roman \
  --trials 2 --model claude-haiku-4-5-20251001 \
  --run-root /tmp/pilot-run --out metrics/tdd-experiment.jsonl
```

Each cell is isolated; `--skip-dispatch` runs the same plumbing with no model.

## Next steps to make this a valid result

1. Author the sized-task corpus (≥ 6–8 tasks, ≥ 5 scenarios each, modifying
   changes) per the design's §8/§11.
2. Wire post-run sensors (`/coverage-*`, `/mutation-testing`, `/farley-score`)
   into each cell so "fully tested" is measured, not approximated.
3. Run the pilot's variance to set N via the power calc, then the full campaign on
   one fixed model.
4. Optionally add a third arm that invokes the real `/build` pipeline to compare
   the *plugin* workflow, not just the TDD practice.
