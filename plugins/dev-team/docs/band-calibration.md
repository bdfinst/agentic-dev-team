# Band calibration

The eval-graded policy layer of epic #879. Calibration is a **separate concern
from model routing** — it does not affect model selection at dispatch (that is
[model-routing.md](model-routing.md)). Instead it declares per-target quality
floors, validates each agent's declared `effort:` band against the cheapest
band that still clears its floor, and surfaces when a routing-file change has
invalidated a target's last calibration.

> Split out of [model-routing.md](model-routing.md) so the routing contract
> stays focused on resolution; this page owns the calibration policy.

**On this page**: [Calibration floors](#calibration-floors) · [Band calibration (`/agent-eval --calibrate`)](#band-calibration-agent-eval-calibrate) · [Recalibration staleness advisory](#recalibration-staleness-advisory-model-routing-check)

## Calibration floors

`knowledge/calibration-floors.json` is a separate policy table from the routing
files — it does not affect model selection. It declares, per eval-graded review
agent or advisory skill, a `riskClass` (`high|standard|advisory`) and a `floor`:
the minimum acceptable eval pass rate (0-1) for that target. `high`
(`security-review`, `concurrency-review`, `arch-review`, `domain-review`) is
floor `1.0`; the remaining review agents are `standard` at `0.9`;
low-effort/lexical review agents and advisory-only skills (e.g.
`test-design-advisor`) are `advisory` at `0.8`.

This is slice 1 of epic #879 (band calibration): a pure policy artifact plus
its guard test, `tests/repo/test_calibration_floors_sync.py`
(`scripts/check_calibration_floors_sync.py`), which keeps the table in sync
with the fixture-bearing `applicableAgents`/`applicableSkills` names declared
across `evals/expected/*.json` and with the agents/skills present on disk.

## Band calibration (`/agent-eval --calibrate`)

Slice 3 of epic #879 (issue #882) wires the floors above into an actual
check: `/agent-eval --calibrate [--agent <name>]` (dispatched through
`scripts/agent_calibrate.py`) walks a target's declared `effort:` band
against the cheapest band whose eval fixtures (quarantined pairs excluded)
clear its calibration floor, resolving each band via `hooks/lib/
model_resolve.py` exactly as a real dispatch would. It reports one of
`aligned | downgrade-available | upgrade-required | floor-failure |
uncalibratable` per target, prints a cost preflight before any dispatch, and
refuses `--in-session` (calibration must grade what's on disk). Output lands
at `.claude/evals/reports/<timestamp>-calibration.md` (per-band pass rates
and, on drift, a ready-to-apply `effort:` diff) and
`.claude/evals/calibration-records.json` (one record per target — the input
the staleness check below consumes). This run never edits any file
under `plugins/dev-team/agents/` or `plugins/dev-team/skills/` — report-only,
always. See [agent-eval's SKILL.md](../skills/agent-eval/SKILL.md#calibration-mode)
for the full procedure.

## Recalibration staleness advisory (`/model-routing-check`)

Slice 4 of epic #879 (issue #883) is the recalibration trigger: a change to
the **content** of `knowledge/model-routing.json` or `.claude/model-ladder.json`
invalidates a target's last calibration, and this surfaces that drift instead
of leaving it silent. The trigger is exactly what `routing_hash()` hashes — the
bytes of those two files — so anything that changes them (a bump to the default
band→model map included) stales every target's last calibration. A model
release with **no** edit to either file is **not** detected today:
`routing_hash()` never reads the released model, so a plain snapshot rotation
under an unchanged map leaves every record `calibration-current`. That gap is an
accepted limitation (see [ADR 0024](../../../docs/adr/0024-keep-single-model-routing-map-keyed-by-canonical-model-ids.md)),
not a bug — the honest contract is content-hash drift of the two routing files,
not "model releases." `/model-routing-check`'s fifth section reads
`knowledge/calibration-floors.json` for the target universe and
`.claude/evals/calibration-records.json` for each target's last calibration
record (both written by slice 1 `#880` and slice 3 `#882` respectively), and
recomputes the current content hash of `knowledge/model-routing.json` +
`.claude/model-ladder.json` using the exact same `routing_hash()` construction
`scripts/agent_calibrate.py` used to stamp the record. Three states per target:

- **`calibration-current`** — the record's `routing_hash` matches the
  current hash. Nothing to do.
- **`calibration-stale`** — the routing map or ladder changed since the
  target was last calibrated (hash drift). Flagged with a pointer to
  `/agent-eval --calibrate --agent <target>`.
- **`never-calibrated`** — the target has a floors entry but no calibration
  record yet. Listed with the same pointer.

**This is advisory only — it never blocks dispatch.** Even when every
calibration record is stale (or none exist at all), `hooks/
agent_model_resolve.py`'s dispatch behavior is completely unchanged; the
advisory is a read-only diagnostic, matching the model-resolution hook's
fail-open contract. See [model-routing-check's SKILL.md](
../skills/model-routing-check/SKILL.md) for the exec block and the
`CALIBRATION_FLOORS_JSON`/`CALIBRATION_RECORDS_JSON` test-only injection
seams.

## Related documents

- [Model Routing](model-routing.md) — effort-band → model resolution (the
  routing contract this calibration layer sits beside)
- [Model Routing — Override Authoring Guide](model-routing-overrides.md) — how
  to author a per-environment ladder
