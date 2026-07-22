# 24. Keep the single model-routing map keyed by canonical model IDs

Date: 2026-07-20

## Status

Accepted. The "uniform bare-canonical ID / no dated snapshot suffix" clause is superseded by [ADR 0025](0025-allow-versioned-model-ids-in-routing-map.md) (versioned/dated IDs are now allowed); the single-map, keyed-by-concrete-ID, and no-second-table decisions below still stand.

Relates to [8. Use effort bands instead of model names in agent frontmatter](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)

Superceded by [26. Adopt native model:/effort: agent frontmatter, retire the band resolver](0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)

## Context

[ADR 0008](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)
established `knowledge/model-routing.json` as the single band → model default
map. Two consumers read a value out of that map, and they need different shapes:

- **`hooks/agent_model_resolve.py`** rewrites the Agent/Task tool's `model`
  parameter, which silently ignores full dated-snapshot IDs (#1178). The hook
  therefore reduces the map's ID to a bare dispatch alias (`haiku|sonnet|opus`)
  before the harness sees it.
- **Calibration dispatch** (`claude -p --model <id>`) and the **staleness
  advisory** (`/model-routing-check`, whose `routing_hash()` hashes the bytes of
  `model-routing.json` + `.claude/model-ladder.json`) both need a **concrete
  model ID**, not an alias.

Historically the map mixed shapes: `low` pinned a dated snapshot
(`claude-haiku-4-5-20251001`) while `medium`/`high` used bare canonical IDs. The
5-family models (`claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`) have no
dated public form at all — the bare ID *is* the canonical ID. This raised the
question of whether the map should hold generic aliases, or whether a separate
"last-known-snapshot-per-alias" table should track concrete IDs alongside a map
of aliases.

## Decision

**Keep one map, keyed by bare canonical model IDs, for every band and legacy
tier.** Concretely, in this PR: `medium`/`sonnet` → `claude-sonnet-5`,
`low`/`haiku` → `claude-haiku-4-5` (dropping the dated suffix),
`high`/`opus` → `claude-opus-4-8`. Every entry is now a bare canonical ID with
no dated snapshot suffix — the map is uniform.

We reject both alternatives:

- **(a) Generic aliases in the map** (`"sonnet"`, `"haiku"`) — this pushes the
  alias→ID resolution into calibration and the staleness advisory, which both
  need a concrete ID. The dispatch hook already reduces the canonical ID to an
  alias in the one place an alias is required; adding aliases to the map would
  invert that, forcing the two ID-needing consumers to re-expand.
- **(b) A separate last-known-snapshot-per-alias bookkeeping table** — a second
  table that must stay in sync with the map is a moving part with no payoff. The
  canonical-ID → alias round-trip the hook already performs is negligible, and
  the split would **not** fix the snapshot-rotation-detection gap (below).

## Consequences

- **Bumping the map stales all calibration records.** `routing_hash()` hashes
  the bytes of `model-routing.json` + `.claude/model-ladder.json`; this PR's
  edit changes those bytes, so every target's last calibration record becomes
  `calibration-stale`. This is advisory only and fail-open — dispatch behavior
  is unchanged, and `/model-routing-check` surfaces the drift with a pointer to
  `/agent-eval --calibrate`.
- **Snapshot rotation under an unchanged map is not detected — accepted
  limitation.** A model release that does not edit either routing file leaves
  `routing_hash()` unchanged, so every record stays `calibration-current`. The
  documented staleness contract is content-hash drift of the two routing files,
  **not** "model releases" (the doc was corrected to say so). Neither rejected
  alternative would close this gap; a release-aware signal is out of scope here.
- **Recalibration is deferred.** This PR stales the records but does not
  re-run calibration; that follow-up is tracked as a separate issue.
- **One shape to reason about.** Every band and legacy tier resolves to a bare
  canonical ID; the dispatch hook is the sole place that reduces to an alias.
