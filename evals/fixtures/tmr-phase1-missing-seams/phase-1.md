# Phase 1 — Analysis (test-modernize)

- Repo slug: `orders-api`
- Assessment file: `.dev-team-reports/cd-test-architecture-orders-api.md`
- Resolved sink: `local-files`
- Quality targets: line ≥ 90%, branch ≥ 90%, mutants = 0, determinism = 100%, wall-clock = fastest achievable

## Components & patterns

| Component | Pattern | Surfaces |
|---|---|---|
| orders-api | API Provider | POST /orders |
| billing-worker | Event Consumer | order.created |

## Current-vs-correct test classification

| Test | Current layer | Correct layer | Reason |
|---|---|---|---|
| `tests/orders.test.ts::create order` | integration | component | uses real Postgres |

## Duplicate-coverage table

| Behavior | Layers | Keep | Retire |
|---|---|---|---|
| order rejection | unit, component | component | unit (over-mocked) |

## CD-fitness gaps

| Gap | Component | Evidence | Impact |
|---|---|---|---|
| Configured-dependency tests | orders-api | (no file cited) | cannot gate merges |

## Target architecture

| Component | Layer | Test type | Doubles | Pipeline stage |
|---|---|---|---|---|
| orders-api | component | API Provider | in-memory PaymentsClient | pre-merge gate |
| billing-worker | component | Event Consumer | in-memory MessageBus | pre-merge gate |

<!-- Intentionally missing: seam-reachability per component. Also: CD-fitness gap row has no file-level evidence. Both are blockers for the gate. -->
