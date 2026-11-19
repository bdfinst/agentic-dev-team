# CD Test Architecture

**Date**: 2026-11-19
**Target**: orders-service
**Scope**: full app

## CD Test Architecture — orders-service

### Components & patterns
| Component | Pattern | Surfaces |
|---|---|---|
| orders-api | API Provider | POST /orders |
| orders-worker | Event Consumer | `order.created` topic |

### Current tests (in-repo)
| Suite | MinimumCD type | Deterministic? | Requires to run | Pre-merge-safe? |
|---|---|---|---|---|
| tests/unit | unit | yes | nothing | yes |
| tests/api | component | no | shared staging DB | no |

The service has 12 unit tests and 3 component tests.

### Target architecture (per component)
| Component | Layer | Test type | Double (to run config-free) | Pipeline stage | Build/Document status |
|---|---|---|---|---|---|
| orders-api | HTTP handler | component | in-memory repository | pre-merge | |

### Pre-merge gate (deterministic, config-free)
Static analysis, unit, and component tests with the repository doubled in memory.

### Migration path
1. Replace the shared staging DB in `tests/api` with an in-memory repository.

## Provenance

- Repository: `orders-service`
