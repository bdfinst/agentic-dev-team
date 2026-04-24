# Comparative testing: our plugin vs. `opus_repo_scan_test`

How to measure whether our tool-first `/security-assessment` pipeline finds the
same issues as the reference's prompt-heavy pipeline, with the same severity
calibration, on the same input.

## Why this exists

The `opus_repo_scan_test-main` repo (`/Users/finsterb/Downloads/opus_repo_scan_test-main/`) is the design inspiration
for this plugin. Our plan explicitly **inverts** its prompt-heavy design —
deterministic tools do detection, LLM agents do semantic reasoning. An
inversion is only valuable if it produces equivalent or better security
coverage. This directory tree provides the evidence.

## What we ship

```
evals/comparative/
├── README.md             # user-facing overview
├── fixture-repo/         # seeded two-service fixture (20+ known findings)
├── ground-truth.yaml     # structured declaration of expected findings
├── score.py              # scoring harness (recall / precision / severity)
└── unit-tests/
    └── codebase-recon-equivalence.md   # first component-level unit test

docs/comparative-testing.md            # this file (runbook)
```

## Component-level equivalence map

Each reference agent has a counterpart in our plugin. A full comparative
test is roughly the conjunction of all of these passing.

| Reference agent | Our counterpart | Unit test |
|---|---|---|
| `scan-00-codebase-recon.md` | `plugins/agentic-dev-team/agents/codebase-recon.md` | ✅ [`codebase-recon-equivalence.md`](../../../evals/comparative/unit-tests/codebase-recon-equivalence.md) |
| `scan-01-secrets-credentials.md` | `gitleaks` + `entropy-check.py` + `semgrep.secrets` | TBD — `secrets-equivalence.md` |
| `scan-02-auth-authorization.md` | `agents/security-review.md` | TBD |
| `scan-03-business-logic-fraud.md` | `plugins/agentic-security-review/agents/business-logic-domain-review.md` + `knowledge/semgrep-rules/fraud-domain.yaml` | TBD |
| `scan-04-data-flow-pii-pci.md` | `tool-finding-narrative-annotator` (PII-flow narrative) + pattern rules | TBD |
| `scan-05-infrastructure-container.md` | `hadolint` + `trivy` | TBD |
| `scan-06-cicd-pipeline.md` | `actionlint` + `semgrep` | TBD |
| `scan-07-cryptographic-analysis.md` | `knowledge/semgrep-rules/crypto-anti-patterns.yaml` | TBD |
| `scan-08-supply-chain.md` | `trivy` + `osv-scanner` + `grype` (tier-2 adapters) | TBD |
| `scan-09-concurrency-state.md` | `agents/concurrency-review.md` | TBD |
| `analyze-10-cross-repository.md` | `/cross-repo-analysis` + `cross-repo-synthesizer` + `service-comm-parser.py` + `shared-cred-hash-match.py` | TBD |
| `analyze-11-false-positive-reduction.md` | `skills/false-positive-reduction` + `agents/fp-reduction.md` | TBD |
| `generate-12-security-report.md` | `agents/exec-report-generator.md` + `skills/security-assessment-pipeline` + `/export-pdf` | TBD |

Adversarial pipeline (reference ships 8 Python probes + 5 prompts):

| Reference | Our counterpart |
|---|---|
| `adversarial-agents/scripts/01..08_*.py` | `plugins/agentic-security-review/harness/redteam/probes/01..08_*.py` |
| `adversarial-agents/lib/{http_client,result_store,scoring,feature_dict}.py` | `harness/redteam/lib/{http_client,result_store,scoring,feature_dict,scope_check}.py` |
| `adversarial-agents/prompts/adversarial-{01..05}-*.md` | `agents/redteam-{recon,evasion,extraction,report-generator}.md` |
| `adversarial-agents/orchestrator.py` | `harness/redteam/orchestrator.py` + `/redteam-model` command (adds scope / consent enforcement) |

## Running the comparison

### Approach 1: Seeded-fixture differential (recommended first)

**Prerequisites**:
- `opus_repo_scan_test-main` at the known path with its agents configured
- Claude Code CLI installed; agentic-security-review plugin installed locally
- `semgrep`, `gitleaks`, `hadolint`, `actionlint` ideally installed (affects recall ceiling on `ours`)

**Steps**:

1. **Capture the reference baseline** (one-time, uses Claude API credits):

   ```bash
   cd /Users/finsterb/Downloads/opus_repo_scan_test-main
   mkdir -p repos
   cp -r /Users/finsterb/_git-os/agentic-dev-team/evals/comparative/fixture-repo repos/fixture-repo

   # From a Claude Code session in the opus_repo_scan_test directory:
   # Run the 13 agents in order per docs/static-analysis-agents.md.
   # Recommended: ask Claude to "run the full static analysis pipeline
   # against repos/fixture-repo per docs/static-analysis-agents.md and
   # produce all four reports under results/reports/".
   #
   # Expected time: ~10-15 minutes; cost: ~$5-15 in Opus API calls.

   # Archive the reference output for future diff checks:
   mkdir -p /Users/finsterb/_git-os/agentic-dev-team/evals/comparative/reference-baseline/$(date +%Y-%m-%d)
   cp -r results/reports/* \
     /Users/finsterb/_git-os/agentic-dev-team/evals/comparative/reference-baseline/$(date +%Y-%m-%d)/
   ```

2. **Run our pipeline** against the same fixture:

   ```bash
   cd /Users/finsterb/_git-os/agentic-dev-team
   # Invoke the /security-assessment command via your Claude Code session:
   /security-assessment evals/comparative/fixture-repo

   # Expected time: faster than the reference (tool-heavy); ~30s-2min.
   # Output lands under memory/.
   ```

3. **Score both**:

   ```bash
   python3 evals/comparative/score.py \
     --reference /Users/finsterb/Downloads/opus_repo_scan_test-main/results/reports \
     --ours memory
   ```

   The scorecard surfaces:
   - **Recall** per system (findings caught / total 26 seeded)
   - **Severity agreement** for matched findings (within ±1 tier)
   - **Suppression correctness** (ACCEPTED-RISKS / business_logic.md)
   - **Extra emissions** (potential false positives — not definitive because
     a finding may be real even if not in ground-truth)

### Approach 2: Capture-and-replay for regression

Once Approach 1 has been run and a reference baseline captured, nightly CI
runs only **our** pipeline + `score.py --ours`. A recall drop over time
indicates regression.

The reference baseline is re-captured quarterly (reference's own code rarely
changes, but Claude Opus updates may drift its output).

### Approach 3: Real-world open-source comparison

Preferred target: [OWASP Juice Shop](https://github.com/juice-shop/juice-shop)
— ~100+ documented vulnerabilities, pinned release tags for reproducibility.

```bash
git clone --branch v17.0.0 https://github.com/juice-shop/juice-shop /tmp/juice-shop

# Capture reference output
# (as Approach 1 Step 1, against /tmp/juice-shop)

# Our pipeline
/security-assessment /tmp/juice-shop

# Score — note: Juice Shop's documented challenges aren't in our
# ground-truth.yaml format; a parallel juice-shop-ground-truth.yaml
# would need to be built from
# https://pwning.owasp-juice.shop/companion-guide.html
```

This is valuable for **real-world recall** but labor-intensive to set up.
Not recommended until Approach 1 is solid.

### Approach 4: Component-level unit equivalence

See `evals/comparative/unit-tests/`. Each unit test is self-contained and
runs against a small fixture subset — cheaper than a full pipeline run.
Useful for:
- Adding a new component and confirming it matches the reference's intent
  without running the full assessment
- Regression-testing a specific agent after modification

## Interpreting results

### Recall

- **95%+**: equivalent or better coverage. Our tool-first approach found
  everything the reference's prompt-heavy approach did.
- **85-94%**: small gaps. Inspect the `MISS` entries in the scorecard to
  see which reference concerns we under-cover. Common causes: a tool isn't
  installed (gitleaks, actionlint) or an LLM agent didn't run (full
  pipeline was bypassed).
- **< 85%**: real gap. Either our detection is incomplete OR the reference
  is finding false positives we correctly skip. Dive into specific
  findings.

### Severity agreement

- **90%+ within ±1 tier**: presentational calibration is sound.
- **< 90%**: our contract v1.1.0 severity mapping may be off for this
  domain. Specifically check `exploitability.score` derivation in
  `fp-reduction` agent.

### Suppression correctness

- **Both at 2/2**: ACCEPTED-RISKS / business_logic.md parsing works on both sides.
- **Ours 2/2, reference 0/2**: the reference hasn't adopted our ACCEPTED-RISKS
  convention — check its `business_logic.md` parsing.
- **Ours 0/2**: bug in our suppression pipeline.

### Extra emissions

- **Our extras < reference extras**: we're less noisy (tool-first wins).
- **Our extras > reference extras**: possibly false positives from our
  SARIF ruleset. Inspect specific rule_ids in the scorecard output.

## Limitations

1. **Non-determinism**: the reference uses Claude Opus for detection;
   re-running produces slightly different output. For stable regression
   testing, pin to a captured baseline rather than re-running.

2. **Ground-truth completeness**: the fixture seeds ~26 findings but the
   reference's 13 agents may find additional real issues we didn't seed
   (e.g. line 1 has a subtle concurrency flaw we didn't anticipate). Both
   systems finding "extras" is evidence, not noise — investigate rather
   than dismiss.

3. **Scan-09 concurrency not seeded**: the fixture doesn't currently
   exercise multi-threaded code. Extend the fixture with a concurrency
   sample if comparing scan-09 coverage matters.

4. **Adversarial pipeline not compared**: this runbook covers static
   analysis only. A parallel comparison for the red-team harness needs a
   mock target (FastAPI app with seeded decision boundaries) and a
   separate ground-truth matrix.

5. **Tool install matters**: our recall depends on which static tools
   are installed. A developer running `score.py --ours` without
   `gitleaks` / `actionlint` will show lower recall than the plugin is
   actually capable of.

## Future improvements

- Add `ground-truth.yaml` entries for scan-09 concurrency
- Add adversarial-pipeline comparative tests (fixture mock target + ground-truth probes)
- Add CI integration: nightly run + GitHub Actions summary
- Build remaining unit tests (`secrets-equivalence.md`, `fp-reduction-equivalence.md`, etc.)
- Build a `juice-shop-ground-truth.yaml` for real-world comparison
