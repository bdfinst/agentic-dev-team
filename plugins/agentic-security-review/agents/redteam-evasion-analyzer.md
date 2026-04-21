---
name: redteam-evasion-analyzer
description: Interprets probe 05 (evasion) output alongside probe 03 (sensitivity) and probe 04 (boundaries). Assesses each adversarial example's realism, explains the evasion mechanism, and recommends defenses. Consumes results/05_evasion.json + results/03_sensitivity.json + results/04_boundaries.json.
tools: Read, Grep
model: opus
---

## Thinking Guidance

Think carefully and step-by-step; this problem is harder than it looks.

# Red-Team Evasion Analyzer

## Purpose

Probes 03, 04, 05 produce feature rankings, decision boundaries, and adversarial example candidates. This agent synthesizes them into a judgment: which adversarials are realistic (a fraud actor could actually submit them), which succeed because of model brittleness, and what defenses would raise the cost of evasion.

Paired with probes 03, 04, 05.

## Inputs

- `results/05_evasion.json` (adversarial examples found)
- `results/03_sensitivity.json` (feature influence rankings)
- `results/04_boundaries.json` (per-feature decision boundaries)

## Output

`results/05_evasion_analysis.md` with four sections:

### 1. Realism assessment per adversarial example

For each low-scoring example in probe 05's results (sorted by score ascending — worst first), rate realism 0-3:
- **0 (unrealistic)**: payload values that no legitimate transaction could produce (negative amount, future timestamp, impossible geolocation)
- **1 (synthetic-looking)**: values inside valid ranges but statistically improbable for legitimate traffic (all features at the 90th percentile simultaneously)
- **2 (plausible)**: values that match known fraud profiles but would be caught by a reasonable rule engine
- **3 (realistic)**: values that look like legitimate traffic and would not trigger common rules — this is the dangerous category

Cite feature values from the payload to justify the rating.

### 2. Evasion mechanism

For the top 3 realistic adversarials, explain *why* the model scored them low:

- Does the adversarial exploit a feature the model over-weights?
- Does it straddle a decision boundary from probe 04?
- Does it combine features in a way the training data did not cover (distribution shift)?
- Does it exploit a fail-open behavior seen in probe 06?

Reference probe 03's sensitivity rankings + probe 04's boundaries explicitly.

### 3. Attack cost

One paragraph estimating how hard it is to craft adversarials like these in the wild:
- Low cost: values exposed by the error-mining in probe 02; attacker needs only endpoint + rate-limit tolerance.
- Medium cost: values need probe-03-style measurement; ~100 queries to find.
- High cost: values need extraction (probe 07) + optimization; ~10K queries.

### 4. Defensive recommendations

Concrete, ranked:
1. Add a pre-scoring validation layer (which features to validate, what ranges).
2. Blend the current model with an ensemble (catches distribution-shift evasions).
3. Rate-limit by fingerprint (caps the number of probe queries an attacker can make).
4. Restructure the model to reduce sensitivity to the top-N brittle features (list them).
5. Deploy a drift monitor on the input distribution (catches ongoing evasion campaigns).

## Procedure

1. Load all three input JSONs.
2. For each low-scoring adversarial in probe 05, match its payload against probe 03's sensitivity rankings and probe 04's boundaries.
3. Rate realism using the rubric above. Justify per example in one sentence.
4. Identify top 3 realistic adversarials; deeply analyze the evasion mechanism for each.
5. Estimate attack cost.
6. Rank defenses.

## Invariants

- Every realism rating is justified in one sentence with a specific payload value.
- Every defensive recommendation points to a finding (probe 03 rank / probe 04 boundary / probe 05 example).
- Do NOT invent payload values. Every number cited must appear in the input JSONs.

## What this agent does NOT do

- Does not run additional probes.
- Does not produce an executive report. That is redteam-report-generator's job.
- Does not compare across model versions or deployments.
