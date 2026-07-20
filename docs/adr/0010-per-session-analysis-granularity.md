# 10. Per-Session Analysis Granularity

Date: 2026-06-23

## Status

Accepted

## Context

The closed learning loop must decide how frequently to run session analysis. Two
candidates were considered:

1. **Per conversation turn** — trigger analysis after every model response.
2. **Per session** — trigger analysis when a session ends (SessionEnd event).

Per-turn analysis would provide the highest freshness but runs the extractor and
dispatches a background agent after every single response, multiplying API cost
and adding latency to every interaction.

## Decision

The analysis trigger fires on **SessionEnd**, not per conversation turn. A
configurable counter (`DEV_TEAM_AUTO_REVIEW_THRESHOLD`, default 5) controls how
many sessions accumulate before analysis runs — amortizing the background dispatch
cost across multiple sessions. The counter is persisted in
`metrics/learning-loop-state.json` and reset to zero when the threshold is reached.

The session-id from the SessionEnd payload is passed to the background `claude`
subprocess via `--session-id` to enable prompt-cache reuse, reducing background
API cost.

## Consequences

- Analysis latency is bounded: findings appear within (threshold × session
  duration) of the triggering sessions.
- The per-session granularity matches the granularity of the session digest
  produced by `session_extract.py`, so no information is lost relative to a
  per-turn approach.
- The configurable threshold lets power users lower it (e.g.,
  `DEV_TEAM_AUTO_REVIEW_THRESHOLD=1` for immediate analysis) without code changes.
- "Per turn" triggering is explicitly excluded; any future proposal to change the
  granularity must supersede this ADR.
