# Component Test Patterns

Reference file for the `cd-test-architecture` skill. Per-component-type testing patterns for a CD pipeline. Builds on `cd-test-architecture.md` (the six test types, the pre-merge determinism rule, the adapter rule, and double validation) — read that first.

Source: MinimumCD Applied Testing Strategies — component patterns (beyond.minimumcd.org/docs/testing/applied-testing-strategies/patterns/). These are recommended starting points, not mandates: drop items that don't apply, add what a component clearly needs.

Core principle for every pattern: **assemble the real component, double only the systems the team doesn't control, drive through the public interface, assert observable outcomes.** Everything below is a specialization of that.

---

## Identify the Component's Pattern

| If the component… | Pattern | Group |
|---|---|---|
| renders data and accepts user interaction against backend APIs | **User Interface** | UI |
| exposes endpoints and owns its data store, no outbound internal calls | **API Provider** | Services |
| exposes endpoints **and** calls upstream services | **API Consumer** | Services |
| consumes messages from a broker | **Event Consumer** | Services |
| publishes messages to a broker | **Event Producer** | Services |
| holds long-lived in-memory state (cache, aggregate, coordinator, websocket gateway) | **Stateful Service** | Services |
| is a binary/package invoked via CLI or imported API | **CLI / Library** | Services |
| is triggered by cron/queue/scheduler to process data and write output | **Scheduled Job** | Batch |

A real system is often several of these; test each surface by its pattern.

---

## UI

### User Interface

Renders data and accepts interaction against backend APIs.

- **Coverage layers:** pure rendering (solitary unit) → component composition (sociable unit) → feature behavior in the DOM (component tests in a real browser, backend stubbed at the network layer) → backend HTTP client (consumer-side contract tests) → a small set of E2E happy paths against real backends (post-deploy).
- **Isolation (run without the backend configured):** drive the UI in a real browser engine; stub the backend **at the network layer** (e.g. Playwright `page.route`). The same fixtures later serve E2E smoke. Do **not** use an in-memory DOM shim (JSDOM) for feature tests — it trades accuracy for false positives on layout/event timing.
- **Success scenarios:** critical flows via keyboard + mouse; valid input submits; loading states; empty/populated/overflow states; i18n (long translations, RTL); responsive breakpoints.
- **Failure modes:** every API call's 4xx/5xx/network/timeout; validation messages (screen-reader announced); token expiry mid-session → re-auth; permission denied; stale data after cross-tab deletes; slow (3G) network; concurrent-edit/optimistic-lock UX; back-button nav; automated WCAG scan.
- **Double validation:** backend stubs must match real endpoints — pin them with contract tests pre-merge, then run **scheduled verification of those contracts against the real backend in a test environment** to detect drift when it happens (not at your next deploy). If the backend is the same team's, provider-side verification in its pipeline is a bonus; don't depend on it for backends you don't control. Post-deploy E2E smoke catches drift the contracts didn't pin.
- **Pipeline:** unit + component (headless browser) + consumer contract tests in Stage 1; visual regression Stage 1/2; E2E smoke post-deploy (blocks rollout, not build); RUM + synthetics in prod.

---

## Services

### API Provider

Exposes endpoints, owns its data store, no outbound internal calls.

- **Coverage layers:** HTTP/API surface (component + provider contract) → domain logic (solitary/sociable unit + component) → persistence adapter (sociable unit + adapter integration + component) → external database (doubled in component; real engine in adapter integration).
- **Isolation:** assemble the full app with an **in-memory repository** and in-memory event bus; drive through HTTP handlers; assert status, persisted state, emitted events.
- **Success scenarios:** documented endpoints return expected shape/status for valid input; auth succeeds for valid creds/tokens; pagination/filter/sort; idempotent ops idempotent, non-idempotent create exactly one; success-path side effects (events, audit).
- **Failure modes:** malformed input (bad JSON, missing/extra fields, type errors); out-of-range/unicode; authz failures (missing/expired token, insufficient scope, cross-tenant); not-found returns 404 not 500; concurrency conflicts with correct status; persistence failure without partial commit; rate-limit/size enforcement; idempotency under retry.
- **Double validation:** adapter integration tests run against a real instance of the **production database engine** via testcontainers (matching version + extensions) — never an SQLite shim for a Postgres prod; provider contract verification confirms the API still satisfies every consumer expectation.
- **Pipeline:** unit + sociable unit pre-commit/Stage 1; component Stage 1; adapter integration out-of-band on a schedule, regardless of ownership; provider contract verification in CD contract/boundary stage.

### API Consumer

Exposes endpoints **and** calls upstream services. The most failure-prone distributed pattern — give it the most attention.

- **Coverage layers:** inbound HTTP surface → domain/orchestration (composes calls) → **resilience policy** (retry, circuit breaker, timeout, fallback) → outbound HTTP client (request build, response parse, headers, deadlines) → persistence adapter → external DB (doubled/real) → downstream service (doubled in pipeline, real out-of-band).
- **Isolation (run without the upstream configured):** wrap the upstream client in a **team-owned thin adapter**; double the adapter in component tests. Drive each failure through the client double.
- **Success scenarios:** constructs right URL/headers/body/auth/timeout; parses success incl. optional/unknown fields; composes multiple downstream calls (sequence/parallel); caching within TTL + refresh after expiry; trace-context propagation.
- **Failure modes:** **timeout** (deadline enforces, caller gets documented response e.g. 504, no partial commit); connection refused (retry count + backoff → fallback/error); 5xx retried only when retryable; 4xx mapped to documented behavior, generally not retried, 429 respects `Retry-After`; malformed/drifted response per Postel's Law; circuit breaker opens under sustained failure, fast-fails, recovers on half-open probe; partial multi-call failure → compensation/rollback/documented partial success.
- **Double validation (do not depend on provider cooperation):** assume the provider can break the contract without versioning and that you won't know until an incident. (1) consumer-side contract tests pin request + response shape, block the build; (2) **scheduled provider-contract verification in a test environment** — *you* run your pinned contract against the provider's real non-prod endpoint on a schedule, out-of-band, decoupled from your deploys — this is the primary defense, attributing a break to the provider when it happens rather than to your next unrelated change; (3) adapter integration tests exercise the real outbound client against controlled states (testcontainers) — asserts the *adapter*, not the dependency; (4) resilience component tests (above) prove the consumer **survives** a broken contract, not just detects it. Provider-side verification of your contract is a bonus *if* they offer it — never relied upon.
- **Anti-pattern:** mocking the third-party SDK directly instead of wrapping + doubling an owned adapter.
- **Pipeline:** consumer contract + resilience component tests (fault injection) Stage 1; adapter integration out-of-band on a schedule, decoupled from deploys — regardless of whether the dependency is in-house or third-party/other-team, never in-band; post-deploy checks scheduled.
- **Stack-specific mechanics — .NET:** the canonical pre-merge seam is `HttpMessageHandler` (stubbed + wired via `IHttpClientFactory.ConfigurePrimaryHttpMessageHandler`); WireMock.Net is the preferred implementation of that seam when installed, with the hand-rolled stub kept as backup. See `references/csharp-http-client-testing.md` and the worked matrix in `test-matrix-examples/dotnet-http-consumer.md`. (Other stacks: Node / Nock preferred, MSW as a documented fallback; JVM / WireMock; Python / VCR.py preferred, `responses`/`httpx` mock as a documented fallback. `virtual-service-libraries.md` is the single source of truth for the per-stack preferred/backup catalog — cite it rather than restating tool names here; add to a stack profile as needed.)

### Event Consumer

Consumes messages from a broker (Kafka/SQS/RabbitMQ/PubSub).

- **Coverage layers:** message handler (solitary unit) → idempotency & ordering (component) → dead-letter / poison-message (component) → backpressure (resilience component) → broker client (adapter integration vs real broker container) → external broker & schema registry (doubled in component; contract + post-deploy synthetic publish).
- **Isolation (run without the broker):** replace the broker with a double; drive the handler with messages directly.
- **Success scenarios:** well-formed message → expected state change + documented downstream event; batch policy honored; replay from offset reproduces identical end state; documented schema versions accepted.
- **Failure modes:** poison message → DLQ with correlation id, consumer survives; duplicate delivery → exactly one record (idempotency); out-of-order per documented policy; mid-batch failure → offsets uncommitted, no data loss; schema skew per version policy; backpressure (slow, don't OOM); rebalancing strands no in-flight messages.
- **Double validation:** adapter integration tests vs a real broker container the team controls (Docker Kafka, ElasticMQ, Redpanda) assert the adapter speaks the protocol (not broker ordering — that's the broker's job); schema-registry doubles validated via contract tests + post-deploy checks vs the real registry.
- **Pipeline:** handler unit + component Stage 1; adapter integration out-of-band on a schedule — regardless of whether the broker is team-controlled or managed/third-party; post-deploy synthetic publishes out-of-band.

### Event Producer

Publishes messages to a broker (often paired with a consumer in the same service).

- **Coverage layers:** publish logic (unit) → publish contract (contract test pins message schema) → broker client adapter (adapter integration) → external broker (doubled; post-deploy synthetic).
- **Isolation:** double the broker adapter; assert the message that *would* be published (shape, key, headers, idempotency).
- **Success/failure:** correct schema/partition-key/headers on the happy path; publish failure → documented retry/outbox behavior, no silent drop; transactional outbox prevents loss on crash between state-write and publish.
- **Double validation:** message schema pinned by contract (consumers verify); adapter integration vs real broker container; post-deploy synthetic publish.
- **Pipeline:** unit + contract Stage 1; adapter integration out-of-band on a schedule, regardless of ownership; post-deploy synthetic.

### Stateful Service

Long-lived in-memory state: caches, aggregates, coordinators, websocket gateways, real-time engines.

- **Coverage layers:** state-machine logic (solitary unit) → persistence & recovery (component with doubled persistence) → single-node concurrency (component) → replication & leader election (cluster tests with real consensus library) → memory bounds (soak) → connection lifecycle (component) → external persistence engine (doubled in component; real engine in adapter integration, out-of-band).
- **Isolation:** double persistence; control time and event ordering to make concurrency deterministic.
- **Success scenarios:** transitions follow documented state machine; state rebuilds identically after restart; replication lag within budget.
- **Failure modes:** crash mid-write → consistent state on restart, no torn writes; concurrent mutations serialize without lost updates; network partition → minority steps down with documented reconciliation; memory pressure → evicts per policy, no OOM; idle connections close cleanly with documented reconnect.
- **Double validation:** persistence doubles validated by adapter integration against the real persistence engine, out-of-band; consensus doubles validated by cluster testcontainer tests, out-of-band.
- **Pipeline:** unit + component Stage 1; adapter integration (persistence recovery) out-of-band on a schedule, regardless of ownership; cluster tests out-of-band on a schedule, regardless of ownership; soak + chaos out-of-pipeline vs deployed instances.

### CLI / Library

Binary or package consumed via CLI or an exported API.

- **Coverage layers:** public-interface behavior (unit/component invoking the real surface) → process startup for a CLI (deployed-binary test invoking the real artifact) → any external deps via owned adapters.
- **Isolation:** test through the public invocation surface (args/stdin/stdout/exit codes for a CLI; exported functions for a library); double external deps via adapters.
- **Success/failure:** documented commands/flags produce documented output + exit code; bad args → documented error + non-zero exit; stdin/stdout/stderr contracts; backward-compatible public API (the consumer's contract).
- **Double validation:** a small set of deployed-binary tests invoke the real built artifact to catch packaging/startup gaps unit tests miss. Unlike Scheduled Job's equivalent check (out-of-band, below), this smoke is deterministic enough to gate in-band when it exercises only the artifact itself — startup, arg parsing, exit codes — with no external system configured: any external dep it does call is already behind an owned adapter (per Isolation above), so the smoke carries none of the source/sink/scheduler coupling that pushes Scheduled Job's version out-of-band.
- **Pipeline:** unit + component Stage 1; deployed-binary smoke Stage 1/2.

---

## Batch

### Scheduled Job

Triggered by cron/queue/scheduler to process data and write output/state.

- **Coverage layers:** pure transformation (solitary unit, no I/O) → job orchestration (component: idempotency, partial-failure recovery, checkpointing, time-window logic) → source/sink adapters (adapter integration vs real container or WireMock) → process startup (deployed-binary test invoking the real artifact) → scheduling integration (out-of-band vs the real scheduler in non-prod) → observability (assertions in component tests).
- **Isolation (run without real data stores or the scheduler):** field-level in-memory fakes for sources/sinks seeded in the test; **inject the clock** (`Clock.fixed(Instant.parse(...), ZoneOffset.UTC)`); invoke the job entrypoint directly rather than via the scheduler.
- **Success scenarios:** representative input → expected output (report/db update/published message); idempotency (running twice for the same logical period → same result, no duplicates); checkpoint resume without reprocessing; time-window correctness across DST and month/year boundaries; empty input → valid empty report; output conforms to documented schema.
- **Failure modes:** source unavailable → clean failure with documented exit code, no partial output, safely re-runnable; sink unavailable → no source state change; partial-write → idempotency keys / transactional outbox prevent duplicates on retry; slow run → alertable, locking prevents overlapping runs; malformed records → log context + configured policy (skip/dead-letter/fail); timezone bugs tested via injected clock; concurrent runs → locking/partitioning; mid-run crash → resume from consistent checkpoint.
- **Double validation:** one out-of-band real-clock check validates production clock wiring (catches "tests UTC, prod container-local"); source/sink contracts pin the shape, post-deploy checks confirm ongoing alignment; a real-scheduler check in non-prod confirms entrypoint discovery, cron timing, env/secret resolution, concurrency policy.
- **Pipeline:** unit + component + contract Stage 1; adapter integration out-of-band on a schedule, regardless of ownership; small deployed-binary set out-of-band on a schedule; real-clock + real-scheduler checks out-of-band scheduled vs non-prod; post-deploy synthetic invocation verifies it ran, processed records, met SLO.

---

## Quick Reference: Isolation Strategy by Pattern

| Pattern | Double to run pre-merge without config | Validated by |
|---------|----------------------------------------|--------------|
| User Interface | Network-layer backend stub (real browser) | Consumer contracts + post-deploy E2E |
| API Provider | In-memory repository + event bus | Adapter integration (real DB container) + provider contracts |
| API Consumer | Owned adapter over upstream client | 4-layer: consumer contract + adapter integration + provider verify + post-deploy |
| Event Consumer | Broker double | Adapter integration (real broker container) + schema contracts |
| Event Producer | Broker adapter double | Message contract + adapter integration + post-deploy synthetic |
| Stateful Service | Persistence double + controlled time/ordering | Adapter integration + cluster testcontainers |
| CLI / Library | Adapters over external deps | Deployed-binary smoke |
| Scheduled Job | In-memory source/sink fakes + injected clock | Adapter integration + real-clock + real-scheduler out-of-band |
