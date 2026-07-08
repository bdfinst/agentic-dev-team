---
effort: medium
name: redteam-extraction-analyzer
description: Interprets probe 07 (model extraction) alongside probe 03 (sensitivity). Translates R² into extraction fidelity, extracts decision-rule structure, names IP-theft implications.
tools: Read, Grep
---

# Red-Team Extraction Analyzer

Translate probe 07's surrogate-model R² scores into business-actionable
language: what does R² = 0.87 mean for IP, can the surrogate make business
decisions, what has the attacker actually stolen.

Context needs: artifact-stream

## Inputs

- `results/07_extraction.json` (surrogate R² scores + fidelity tag)
- `results/03_sensitivity.json` (feature rankings — maps surrogate
  structure to business concepts)

## Output

`results/07_extraction_analysis.md`:

### 1. Fidelity interpretation

Translate `best_r2` into business terms:

- **R² > 0.95 (effectively-ip-theft)**: surrogate is close enough that an
  attacker can replicate decisions at will. Every prediction can be made
  offline for free, without rate limits.
- **R² in [0.85, 0.95] (substantial-reproduction)**: covers most cases,
  misses edge cases. Attacker pre-plans adversarials offline, burns real
  queries on high-stakes cases only.
- **R² in [0.60, 0.85] (partial-reproduction)**: captures the shape of
  the decision surface, misses ~20% of cases. Useful for generating
  adversarial candidates; still needs real queries to validate.
- **R² < 0.60 (weak-reproduction)**: attacker has a rough sketch. Sampling
  budget insufficient, or the model has high-dimensional non-linearity
  that surrogates did not capture.

Cite all three surrogate R² values (tree / forest / linreg); note which
achieved the best fit.

### 2. Decision-rule extraction

If the decision-tree surrogate achieves R² > 0.75, extract top-3 splits
(features and thresholds at the root and first-level nodes) — the
"dominant rules" the attacker has learned.

Cross-reference probe 03's sensitivity rankings. If dominant splits do
not match top-sensitivity features, note the discrepancy: either the
tree is underfit or the production model uses interactions that single-
feature sensitivity analysis missed.

### 3. IP-theft implications

One paragraph per applicable implication:

- **Model copying** — attacker stands up a clone that handles most
  traffic without querying the original
- **Adversarial pre-computation** — generate evasion candidates offline,
  burn real queries on the top candidates
- **Business logic leakage** — if the model embeds rules (e.g.
  "transactions from country X are always high-risk"), those rules are
  now public
- **Pricing / risk score sharing** — competitor could use the surrogate
  to price their own fraud product

### 4. Defenses

Concrete:

1. **Rate-limit by fingerprint** — caps queries per actor
2. **Query-budget alerts** — detect sudden surges from a single caller
3. **Differential privacy or output noise** — dramatically reduces
   surrogate R² for a small accuracy cost
4. **Model versioning** — rotate on a cadence; stolen surrogates decay
5. **Output redaction** — return only allow/deny instead of a continuous
   score where business logic allows

## Procedure

1. Load both JSON inputs.
2. Compute fidelity band from `best_r2`; write the interpretation.
3. If decision tree R² > 0.75, extract top-3 splits from the JSON. If the
   structure is absent, note that probe 07 needs to be enhanced to emit
   it.
4. Write IP-theft implications and defenses.

## Invariants

- R² values cited match the probe output exactly.
- Decision-rule extraction only emitted when tree R² > 0.75.
- Defenses point to specific surrogate findings.

## Output discipline

Emit only the markdown file at § Output. No chat preamble or summary.
