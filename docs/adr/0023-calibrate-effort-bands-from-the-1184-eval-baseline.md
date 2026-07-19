# 23. Calibrate agent effort bands from the #1184 eval baseline

Date: 2026-07-19

## Status

Accepted

Relates to [8. Use effort bands instead of model names in agent frontmatter](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)

## Context

[ADR 0008](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)
established that each review agent declares a reasoning-effort band
(`effort: low|medium|high`) in frontmatter, resolved to a concrete model by
`hooks/agent_model_resolve.py`. Issue #880 added `knowledge/calibration-floors.json`:
a per-target minimum eval pass rate (`floor`) keyed by a `riskClass`
(`high` 1.0 / `standard` 0.9 / `advisory` 0.8).

Until now every band was **rubric-only** — assigned by human judgement, never
validated against evals. `calibration-records.json` did not exist; every
floors-bearing target was `never-calibrated` (epic #1181, finding: "no band has
ever been validated by calibration"). Bands could therefore be higher (more
expensive) than the task needs, with no evidence either way.

Issue #1184 ran the first baseline calibration across all 26 floors-bearing
targets. This ADR records the decision rule we applied to its results and the
resulting band changes.

## Decision

### Calibration rule

For each target we graded every `(fixture, band)` cell with **5 samples** and a
**majority vote** (a cell passes when ≥ 3/5 samples pass). A target's
**calibrated band** is the *lowest* band whose pass rate over its active
fixtures meets that target's floor. The verdicts:

- `aligned` — calibrated band equals the declared band. No change.
- `downgrade-available` — a cheaper band already clears the floor. Apply the
  downgrade.
- `floor-failure` — no band clears the floor. Do **not** change the band; this
  is a fixture/floor problem, not a routing decision (see Non-goals).

**The floor is a fixed quality bar; the effort band is the cheapest model that
clears it.** These are independent axes. `riskClass`/`floor` expresses the
*consequence* of a missed finding; the effort band expresses *which model*
runs. A downgrade lowers the model, never the floor — the
`calibration-floors.json` `_comment` was updated to state this decoupling
explicitly, and no floor value changed.

### Applied downgrades (8)

| agent | band | floor | evidence (calibrated-band pass rate) |
|---|---|---|---|
| `a11y-review` | medium → low | 0.90 | low 100% |
| `component-architecture-review` | medium → low | 0.90 | low 100% |
| `doc-review` | medium → low | 0.90 | low 100% |
| `performance-review` | medium → low | 0.90 | low 100% |
| `refactor-opportunity-review` | medium → low | 0.90 | low 100% |
| `spec-compliance-review` | medium → low | 0.90 | low 100% |
| `correctness-review` | high → medium | 1.00 | medium 100% (low 78% < floor) |
| `concurrency-review` | medium → low | 1.00 | low 100% — **provisional, see below** |

Verified-and-unchanged (`aligned`): `ai-provenance-review` (high),
`arch-review` (high), `session-analysis` (medium), `svelte-review` (low).

Each downgrade is its own commit so it can be reverted independently.

### `concurrency-review` is provisional

`concurrency-review` calibrated to `low` (100% at every band) but on only **3
fixtures, 2 of them positive**, all single-file and trivially caught even by the
cheapest model — implausibly easy for a `riskClass: high`, 1.0-floor
race-condition agent. Its `floor` stays 1.0; its band is downgraded
**provisionally**. Issue #1211 hardens the fixtures (now 8 positive + 2
negative, adding TOCTOU, missing-await, non-idempotent-retry, lock-leak,
lost-update, and fire-and-forget cases) and re-calibrates. If the harder set
drops the low band below 1.0, revert the band to medium/high.

### Confidence caveats

- **33% of cells flapped** (non-deterministic across the 5 samples) — many
  fixtures sit at the detection boundary. A fixture quarantine/rewrite pass is
  warranted before treating any single verdict as high-confidence.
- The baseline was run with a checkpointed driver (container-reclaim
  durability), and an initial local segment was discarded and recomputed after
  a dispatch-parsing corruption; the published figures are from the corrected
  run. See #1184 for the full method and table.

## Consequences

- **Cost**: six broad-scope review agents drop from Sonnet to Haiku and
  `correctness-review` from Opus to Sonnet, reducing per-review token cost with
  no measured loss against their floors.
- **Provisional risk**: `concurrency-review` runs on the cheapest model until
  #1211's re-calibration confirms or reverts it. The 1.0 floor is unchanged, so
  the quality bar it is held to has not moved.
- **Not applied**: ten targets are `floor-failure` on real signal
  (`claude-setup`, `complexity`, `domain`, `js-fp`, `naming`, `security`,
  `structure`, `test-review`, `test-smell`, `token-efficiency`) — their bands
  are untouched pending fixture/floor work, each blocking its own apply.
- **Excluded as harness gaps** (not calibration results): reactivity agents
  with missing fixtures (#1209) and `test-design-advisor`, a skill that
  `/review-agent` cannot dispatch (#1210).
- **Verification debt**: per-agent re-calibration (`/agent-eval --calibrate
  --agent <name>` → `aligned`) after each applied change is still pending; the
  #1184 baseline is the supporting evidence in the interim.
- Because the effort band no longer implies `riskClass`, future readers must not
  infer one from the other; the floors `_comment` now says so.
