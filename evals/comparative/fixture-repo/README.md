# comparative-testing fixture repo

A synthetic two-service repo that seeds ~20 known findings across the nine
concerns the `opus_repo_scan_test` reference scans for. Used to score the
reference pipeline and our `/security-assessment` pipeline against the same
ground truth.

## Services

- **services/fraud-scoring/** — Python FastAPI ML fraud-scoring service. Seeds:
  fail-open path, emulation-mode bypass, feature poisoning, MD5 for integrity,
  PAN in logs, hardcoded AWS key, unpinned requirements, root-user Dockerfile,
  insecure ONNX load, TLS verify=False.

- **services/auth-gateway/** — TypeScript Express gateway. Seeds: hardcoded JWT
  secret (same value reused in fraud-scoring — cross-env credential reuse),
  unauthenticated admin endpoint, NODE_TLS_REJECT_UNAUTHORIZED=0, outbound
  HTTP to hardcoded URL, CI workflow with printenv + continue-on-error
  misuse, unpinned npm dependencies.

## Shared surface

- **.github/workflows/ci.yml** — seeds scan-06 CI/CD findings (printenv in
  workflow, continue-on-error on security step, missing SAST).
- **services/fraud-scoring/models/scoring-v1.onnx** — model artifact with
  mismatched sidecar hash (scan-ml model-hash-verify integrity failure).

## Ground truth

See `evals/comparative/ground-truth.yaml` for the full list of seeded
findings with rule-id patterns, file locations, expected severity, and
reference-scan-concern mapping.

## Suppression carveouts

Both `ACCEPTED-RISKS.md` (our convention) and `business_logic.md` (the
reference's convention) declare the same two suppressions:

- Test-fixture credentials in `tests/` — matches a real test-only use.
- Dockerfile on the build-stage image running as non-root is OK; the final
  stage must be non-root (tests whether both systems handle multi-stage
  Dockerfiles correctly).

A scorer that correctly applies either file suppresses the flagged lines
from its emitted findings.

## Not seeded (intentionally)

- No real CVEs — everything is pattern-detectable.
- No actual runtime behaviour — probes (red-team) are out of scope for the
  static-analysis comparison. A separate adversarial-pipeline fixture would
  need a live mock target.
- No test-framework expectations — this is not a Python project you `pytest`;
  it is a pattern fixture.

## Running the comparison

```bash
# Reference pipeline (manual, uses Claude API credits):
cd /path/to/opus_repo_scan_test-main
cp -r /path/to/agentic-dev-team/evals/comparative/fixture-repo repos/fixture-repo
# Run the 13 agents per docs/static-analysis-agents.md
# Output lands in results/reports/

# Our pipeline:
cd /path/to/agentic-dev-team
/security-assessment evals/comparative/fixture-repo
# Output lands in memory/report-fixture-repo.md + findings-fixture-repo.jsonl

# Score both:
python3 evals/comparative/score.py \
  --reference /path/to/opus_repo_scan_test-main/results/reports \
  --ours memory
```
