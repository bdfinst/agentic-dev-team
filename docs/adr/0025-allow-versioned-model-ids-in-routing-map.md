# 25. Allow versioned (dated-snapshot) model IDs in the routing map

Date: 2026-07-21

## Status

Accepted. Supersedes the "uniform bare-canonical ID / no dated snapshot suffix" clause of [ADR 0024](0024-keep-single-model-routing-map-keyed-by-canonical-model-ids.md); ADR 0024's other decisions (one map, keyed by concrete IDs rather than generic aliases, no separate snapshot-bookkeeping table) still stand.

## Context

[ADR 0024](0024-keep-single-model-routing-map-keyed-by-canonical-model-ids.md) required every value in `knowledge/model-routing.json` to be a **bare canonical model ID with no dated snapshot suffix**, and dropped `claude-haiku-4-5-20251001` to `claude-haiku-4-5` to make the map uniform.

The model-staleness action (#1275, shipped in #1276) now reconciles the map against the live catalog and pins the newest member of each family. It reads `GET /v1/models`, whose `id` values are **not uniform**: some models are returned as dated snapshots (`claude-haiku-4-5-20251001`), while the 5-family models (`claude-sonnet-5`, `claude-opus-4-8`) have no dated public form and come back bare. Honoring ADR 0024's uniformity clause would force the bot to strip a trailing `-YYYYMMDD` from every ID before writing — a normalization step that re-litigates which spelling is "canonical" for no functional gain.

Nothing downstream needs the uniformity:

- **Dispatch** — `hooks/agent_model_resolve.py` reduces the map's ID to a bare dispatch alias (`haiku|sonnet|opus`) before the Agent/Task tool sees it (#1178), so a dated ID and a bare ID dispatch identically.
- **Calibration** — `claude -p --model <id>` accepts a concrete dated ID as readily as a bare one.
- **Pricing / bump log** — already key by full snapshot IDs (see the note in ADR 0024's context).

## Decision

**Allow each band's value to be either a bare canonical ID or a dated snapshot ID** — whatever `GET /v1/models` returns as the current newest member of that family. The map is no longer required to be uniform in shape.

The staleness bot therefore writes the Models API `id` verbatim; there is no suffix-stripping step. In practice this means the 5-family models stay bare (no dated form exists) while dated-snapshot models are pinned with their date — a mixed map is now expected, not a defect.

## Consequences

- **`test_model_routing_defaults.py` asserts family, not exact ID.** Each band must resolve to the right family name (the tier word with all version digits removed: `low`→`haiku`, `medium`→`sonnet`, `high`→`opus`) and be a `claude-*` string. It no longer pins an exact version or spelling, so a routine version bump does not break the suite.
- **`test_no_pinned_snapshots.py` is unaffected** — it already exempts `model-routing.json` (the single source of truth is where a pinned snapshot is *supposed* to live).
- **The 5-family / dated-family split is permanent and expected.** The map will look mixed; that is the Models API's shape, not drift to correct.
- **ADR 0024 otherwise stands.** One map, keyed by concrete model IDs (not generic aliases), with no second snapshot table — all unchanged. Only the uniform-shape requirement is lifted.
