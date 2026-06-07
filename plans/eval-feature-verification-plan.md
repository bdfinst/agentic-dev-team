# Future test plan — verifying #107, #110, #180 work correctly

These three children of [#98](https://github.com/bdfinst/agentic-dev-team/issues/98)
are **unblocked** (the tooling and the clean-eval methodology now exist) but not
yet built. This plan defines, for each, what it builds on, how to build it, and —
the point of this doc — **how to verify it actually works** once built.

Cross-cutting requirement for all three: use the **clean methodology** from
[`../plugins/dev-team/docs/eval-running-guide.md`](../plugins/dev-team/docs/eval-running-guide.md)
(neutral dispatch, faithful actuals) and the variance aggregator. A feature that
"runs" but biases its own measurement is not working.

---

## #107 — Knowledge ablation testing

**Builds on:** the eval harness (`eval_grade.py`), the variance aggregator, and
the knowledge index. **Mechanism:** for a knowledge file (or anchor), run the eval
corpus with it **available** vs **ablated** (hidden from the agent) and diff the
grades → a per-file "retrieval value" score.

**Verification (acceptance):**

1. **Positive control — a load-bearing file shows impact.** Pick a fixture whose
   correct verdict plausibly depends on a specific knowledge file (e.g. a
   test-smell fixture and `knowledge/test-smells.md`). Ablating that file must
   **measurably drop** the agent's grade (pass@k down) vs. with it present.
2. **Negative control — an irrelevant file shows none.** Ablating a knowledge file
   unrelated to the fixture must **not** change the grade.
3. **Report shape.** The output ranks knowledge files by measured grade impact;
   zero-impact files are listed as removal/consolidation candidates.
4. **No bias.** Ablation must not change the dispatch prompt (only knowledge
   availability), and actuals are captured faithfully.

**Pass condition:** the positive control drops, the negative control doesn't, and
the ranking is reproducible across a re-run (within the variance band from #103).

---

## #110 — Persona-vs-context-boundary test

**Builds on:** the variance harness (#103) and the eval corpus. **Mechanism:** run
each review agent with its **persona frontmatter ON vs OFF** (same fixtures,
knowledge, trials) and compare pass@k; the #103 variance band tells you whether a
delta is real or noise.

**Verification (acceptance):**

1. **The toggle actually toggles.** Confirm the persona-OFF run dispatches an agent
   whose persona prose is genuinely stripped (diff the two agent definitions used)
   — otherwise the experiment measures nothing.
2. **Delta vs. variance band.** For each agent, the persona-on/off pass@k delta is
   reported **with** the #103 flap/variance, so a delta is only called "real" when
   it exceeds the noise band.
3. **Reproducibility.** A re-run reproduces the sign of each agent's delta.
4. **Honest null.** If personas show no delta beyond noise, the report says so —
   the test must be capable of returning "no effect."

**Pass condition:** the toggle is verified to change the dispatched agent, and the
per-agent deltas are reported against the variance band and reproduce on re-run.
(Acting on the result — dissolving personas — is a separate decision, not part of
"does the test work.")

---

## #180 — Raw-log tier + methodology lens (Delta A/B)

**Builds on:** the digest/rollup (flags worst sessions), the loop infra (Delta
C/D). **Mechanism:** for the **top-N worst sessions the digest flags**, dispatch
one agent **per raw log** to surface *semantic* frictions a metrics digest can't
(e.g. hallucinated citations), plus a `methodology` lens for operator habits —
output held to metrics-only/no-quote discipline.

**Verification (acceptance):**

1. **Seeded-friction detection.** Construct a session transcript containing a known
   semantic friction (e.g. the model citing a skill as a source when that content
   doesn't exist). The raw-log tier must **surface that friction**.
2. **No false friction on a clean session.** A clean seeded session yields no
   fabricated findings.
3. **Gated by the digest.** The tier runs **only** on digest-flagged worst
   sessions, never the whole corpus — verify it skips un-flagged sessions.
4. **Privacy.** The tier's output contains **no** raw prompt/code/path content —
   only metrics + which-artifact-to-fix. Assert no quoted source leaks.
5. **Methodology lens.** A session with a planted operator habit (e.g. repeatedly
   deferring decisions) produces a human-directed observation with no artifact/hook
   target.

**Pass condition:** seeded friction is detected, clean sessions stay quiet, the
tier only runs on flagged sessions, and output passes the metrics-only/no-quote
check.

---

## Regression guard for all three

Add each feature's verification as repeatable tests where possible:

- The **deterministic** parts (report shape, gating logic, privacy assertions,
  toggle-changes-the-agent) become `bats`/unit tests that run in CI — no model
  spend.
- The **model-dependent** parts (does ablation drop the grade, does the tier find
  the seeded friction) run as **opt-in** live checks under a budget cap, like the
  #103 variance batches — never in the default CI gate.

This split keeps the "does it work" verification cheap and continuous, with the
expensive model-truth checks gated behind explicit budget.
