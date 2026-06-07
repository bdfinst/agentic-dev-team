# How eval testing works & keeping it current

The conceptual model behind the agent evals and the discipline for keeping the
corpus honest over time. For the architecture see [`eval-system.md`](eval-system.md);
for the operational run procedure see [`eval-running-guide.md`](eval-running-guide.md).

## The pieces

| Piece | Where | Role |
|---|---|---|
| Fixtures | `evals/fixtures/` | Input code (deliberately good or bad) the agents review. |
| Expectations | `evals/expected/*.json` | The **contract**: what a correct verdict looks like per fixture/agent. |
| Grader | `scripts/eval_grade.py` | Deterministic, model-free: compares recorded actuals to expectations. |
| Variance | `scripts/eval_variance.py` | Aggregates K trials → pass@k, flap rate, quarantine. |
| Trend | `metrics/eval-variance.jsonl` | Append-only stability history (metrics only). |
| Semver contract | `scripts/eval_semver_classify.sh` | The eval corpus IS the version contract (#101). |
| CI gates | `.github/workflows/agent-eval.yml` | Structural check always; live regression when keyed. |

## How grading works (the rules)

`eval_grade.py grade_agent` checks each expectation field; an empty failure list
means PASS:

- **`expectedStatus`** — `pass` / `fail`; must match the agent's `status`.
- **`issueCount: {min, max}`** — number of reported issues must fall in range.
- **`severities: {error: {min,max}, ...}`** — count per severity in range.
- **`mustMention: [...]`** — every keyword must appear (case-insensitive
  **substring**) in the issue messages + summary. **All-of.**
- **`mustNotMention: [...]`** — none may appear. **All-of.**

Grading is intentionally dumb (no judgment) so it can run as a CI gate and so
variance is reproducible.

## The calibration trap (learn this — #198)

Because matching is plain substring, expectations drift out of sync with how
agents actually phrase correct verdicts. Two failure modes, both **fixture bugs,
not agent bugs**:

1. **`mustNotMention` is negation-blind.** A clean-pass fixture forbidding
   `"hardcoded"` fails when the agent correctly says *"no hardcoded secrets"*.
   **Fix:** drop `mustNotMention` on clean-pass fixtures — `expectedStatus:pass` +
   `issueCount` (+ `error 0-0`) already encode "found clean."
2. **`mustMention` too strict.** Requiring the exact token `"SRP"` fails when the
   agent says *"responsibilities"* / *"divergent change"*. **Fix:** use **stems**
   (`"responsibilit"`) and the vocabulary agents actually emit; avoid all-of lists
   of rare tokens.

**When a correct agent verdict fails grading, suspect the fixture first.** Verify
the fix against the agent's *real* output, not a hand-typed approximation.

## Keeping the corpus current

### Adding a fixture

1. Add the input file under `evals/fixtures/`.
2. Add `evals/expected/<stem>.json` with `fixture`, `applicableAgents`, and the
   per-agent expectation (prefer `expectedStatus` + `issueCount`; add
   `mustMention` stems only when a specific concept must be named).
3. `python3 scripts/eval_grade.py --check-corpus` (every expectation must be
   schema-valid and pair with a fixture; this runs in CI).

### Changing an expectation = a version bump (#101)

The eval corpus is the semver contract. `eval_semver_classify.sh` (pre-push + CI)
enforces it:

- GREEN-preserving change → **patch**.
- Adds expectations → **minor** (`feat:`).
- **Edits** existing expectations → **minor/major** (`feat:` / `feat!:`) — an
  edit changes the agents' observable contract.
A `fix:` commit that edits an expectation will be **rejected**; use the bump the
classifier names.

### Watching stability over time

- Run per-agent variance batches periodically (see the running guide). The trend
  in `metrics/eval-variance.jsonl` accumulates pass@k and flap rate.
- **Flaky pairs** (0 < pass@k < 1) go on the quarantine list — they inform the
  #99 gate but must not hard-block it. A persistently flaky fixture is either
  borderline (tighten it) or genuinely non-deterministic for that agent.
- **Saturated** agents (identical grades for many runs) may have expectations too
  loose to detect regressions — consider tightening ranges.

## Cardinal rules

1. **Faithful actuals.** The grader sees what you record; abbreviating issue
   messages drops `mustMention` keywords and fabricates flaps.
2. **Neutral dispatch.** Never leak `status`/`severity` examples into the agent's
   prompt (see the running guide).
3. **Fixtures are the contract.** Keep them honest: a stable-fail on correct
   output is a corpus bug to fix, not noise to ignore.
4. **Metrics only.** Digests, the trend, and reports carry counts/ratios/names —
   never prompt or code content.
