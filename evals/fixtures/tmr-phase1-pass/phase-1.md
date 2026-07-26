# Phase 1 — Analysis (test-modernize)

- Repo slug: `orders-api`
- Assessment file: `.dev-team-reports/cd-test-architecture-orders-api.md`
- Resolved sink: `gh` (<https://github.com/acme/orders-api/issues/42>)
- Quality targets: line ≥ 90%, branch ≥ 90%, mutants = 0, determinism = 100%, wall-clock = fastest achievable

## Components & patterns

| Component | Pattern | Surfaces |
|---|---|---|
| orders-api | API Provider | POST /orders, GET /orders/:id, DELETE /orders/:id |
| billing-worker | Event Consumer | order.created |
| nightly-reconcile | Scheduled Job | scheduler.cron('0 2 ** *', main) |

## Current-vs-correct test classification

| Test | Current layer | Correct layer | Reason |
|---|---|---|---|
| `tests/orders.test.ts::create order` | integration | component | uses real Postgres; should use in-memory adapter |
| `tests/billing.spec.ts::happy path` | unit | component | exercises full event handler |

## Duplicate-coverage table

| Behavior | Layers | Keep | Retire |
|---|---|---|---|
| order rejection on invalid total | unit, component, e2e | component | unit (over-mocked), e2e (slow) |

## CD-fitness gaps

| Gap | Component | Evidence | Impact |
|---|---|---|---|
| Configured-dependency tests | orders-api | tests/orders.test.ts:12 — requires DATABASE_URL | cannot gate merges |
| Manual smoke script | nightly-reconcile | docs/manual-smoke.md | non-repeatable |

## Seam-reachability per component

| Component | Behavior | Testable today | Requires refactor | Code location | Minimum refactor |
|---|---|---|---|---|---|
| orders-api | accept valid order | yes (HTTP handler seam) | — | — | — |
| orders-api | reject on payments-service 500 | no | yes | src/payments.ts:8 (static fetch) | inject HttpClient |
| billing-worker | invoice on order.created | yes (handler export) | — | — | — |
| nightly-reconcile | reconcile valid rows | yes (main entry) | — | — | — |

## Target architecture

| Component | Layer | Test type | Doubles | Pipeline stage |
|---|---|---|---|---|
| orders-api | component | API Provider | in-memory PaymentsClient, in-memory OrdersRepo | pre-merge gate |
| billing-worker | component | Event Consumer | in-memory MessageBus | pre-merge gate |
| nightly-reconcile | component | Scheduled Job | in-memory InputSource | pre-merge gate |

## Child-slug → tracker-id map

```json
{
  "gap-orders-api-configured-deps": 101,
  "gap-nightly-reconcile-manual-smoke": 102,
  "baseline-orders-api": 103,
  "baseline-billing-worker": 104,
  "baseline-nightly-reconcile": 105
}
```
