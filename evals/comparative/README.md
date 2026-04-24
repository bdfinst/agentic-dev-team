# Comparative testing

Infrastructure for scoring this plugin's `/security-assessment` pipeline
against the `opus_repo_scan_test` reference pipeline on the same input.

## Layout

```
evals/comparative/
├── README.md                     # this file
├── fixture-repo/                 # two-service synthetic fixture with ~26 seeded findings
│   ├── services/fraud-scoring/   # Python FastAPI ML service
│   ├── services/auth-gateway/    # TypeScript Express gateway
│   ├── .github/workflows/ci.yml  # CI/CD scan-06 fixtures
│   ├── ACCEPTED-RISKS.md         # our suppression convention
│   └── business_logic.md         # reference's suppression convention (same carveouts)
├── ground-truth.yaml             # structured declaration of seeded findings
├── score.py                      # scoring harness: reference vs. ours scorecard
└── unit-tests/
    └── codebase-recon-equivalence.md  # component-level spec (first of several)
```

Full runbook: [`comparative-testing.md`](../../plugins/agentic-security-assessment/plugins/agentic-security-assessment/docs/comparative-testing.md).

## Quick start

Score our pipeline's output (after `/security-assessment evals/comparative/fixture-repo`):

```bash
python3 evals/comparative/score.py --ours memory
```

Score the reference's output (after manual run — see runbook):

```bash
python3 evals/comparative/score.py \
  --reference /path/to/opus_repo_scan_test/results/reports
```

Both side-by-side:

```bash
python3 evals/comparative/score.py \
  --reference /path/to/opus_repo_scan_test/results/reports \
  --ours memory
```

## What the scorecard measures

| Metric | What it tells you |
|---|---|
| Recall | How many seeded findings each pipeline surfaced |
| Severity agreement | Whether matched findings get the same CRITICAL/HIGH/MEDIUM/LOW tier |
| Suppression correctness | Whether ACCEPTED-RISKS / business_logic.md carveouts are honored |
| Extra emissions | Findings not in ground-truth (potential FPs, or real issues we missed when writing the fixture) |

## What this does NOT test

- **Adversarial ML pipeline** (probes 01-08 + analyzer agents). Needs a mock
  target; see `plugins/agentic-security-assessment/docs/comparative-testing.md` § Future improvements.
- **Cross-repo attack chains** at narrative level. Two services in the
  fixture exercise the `shared-cred-hash-match` path but not multi-service
  attack synthesis.
- **Runtime performance**. The scorecard doesn't time either pipeline.
  Informally: ours finishes in ~30s-2min tool-only; the reference's 13
  agents take ~10-15min in Claude.

## Extending

- Add a new seeded finding: create the code in `fixture-repo/`, add an
  entry to `ground-truth.yaml`, verify with `score.py`.
- Add a component-level unit test: create a spec under `unit-tests/` and
  link it from `plugins/agentic-security-assessment/docs/comparative-testing.md` § Component-level equivalence
  map.
- Real-world comparison: see `plugins/agentic-security-assessment/docs/comparative-testing.md` § Approach 3
  for Juice Shop guidance.
