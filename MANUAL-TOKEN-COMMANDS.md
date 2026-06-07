# Manual commands that require token/model usage

These are the steps from the issues #124–#142 work that **spend API tokens**
(they dispatch real models) and therefore could not run in the hermetic
automated session. Everything else (extractors, cost meter, semgrep audit,
`eval_grade.py --check-corpus`, `ci-local.sh`) is deterministic and free.

Prereq for all live evals: `ANTHROPIC_API_KEY` set in your shell (local) or as a
repo secret (CI).

---

## 1. Record a *measured* agent-eval baseline — #133  (the main deferred task)

`evals/baseline.json` currently ships `provenance: "hand-authored"`. To replace
it with a measured baseline (`provenance: "measured"`, real `recorded_at`):

**Option A — CI (recommended):** after #152 merges, add the **`run-eval`** label
to a PR (or run the `agent-eval` workflow via `workflow_dispatch` with
`force_live=true`). It produces `actuals.json` from a real run.

**Option B — locally (paid):**
```bash
# dispatch the review agents over the changed/relevant corpus (spends tokens):
bash scripts/eval-changed.sh "$(git merge-base HEAD origin/main)" HEAD
#   …or run the full live eval the pre-push hook offers:
HUSKY_RUN_EVALS=1 git push
```

Then grade the run and write the measured baseline (this step itself is free,
but needs the paid `actuals.json`):
```bash
python3 scripts/eval_grade.py --actuals actuals.json --write-baseline evals/baseline.json
```
This stamps `provenance: "measured"` and the real `recorded_at`. Commit the file.

---

## 2. Run `/session-review` — #128 (analyze stage spends tokens)

Stage 1 (extract) is free and zero-token:
```bash
python3 scripts/session_extract.py --plugin-root plugins/dev-team -o memory/session-digest.json
```
Stage 2 (analyze) dispatches the `session-analysis` agent over the digest —
**this costs tokens**. Run it from a Claude Code session:
```
/session-review
```
It writes `reports/session-review-<date>.md` and appends to
`metrics/session-digest.jsonl`.

---

## 3. Validate a new/changed detection rule — #136 hand-off (spends tokens)

When `/session-review` (or a fixture change) proposes a new/changed detection
rule, validate it before shipping with the live eval:
```
/agent-eval --agent <agent-name>
```
This dispatches the agent against the eval fixtures — **paid**.

---

## 4. Per-run live-eval cost estimate — #133 (c) / depends on #134

Once #147 (#134 cost meter) is merged and you've run at least one live eval with
the cost meter active, estimate the per-run live-eval cost before deciding
whether to make the gate default-on:
```bash
python3 plugins/dev-team/hooks/lib/cost_meter.py report --transcript <eval-run-transcript>
```
(The cost meter, regression, and pace subcommands are themselves free — they
parse transcripts; only producing the transcript via a live run costs tokens.)

---

### Free (no tokens) — for reference, run anytime
```bash
python3 scripts/session_extract.py ...                         # extractor
python3 plugins/dev-team/hooks/lib/cost_meter.py report|regression|pace ...
python3 plugins/security-assessment/scripts/audit-semgrep-fixtures.py
python3 scripts/eval_grade.py --check-corpus
bash scripts/ci-local.sh
```
