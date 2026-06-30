# C# HTTP client testing — fast, deterministic, pre-merge

Reference for testing a .NET service's **outbound** HTTP layer (`HttpClient`,
the **API Consumer** side of `knowledge/component-test-patterns.md` →
*API Consumer*). The canonical seam is `HttpMessageHandler` — substitute it
and the HTTP layer becomes a pure function of inputs: no sockets, no ports,
no Kestrel, microsecond-fast, bit-for-bit reproducible.

This is the .NET realization of the **Adapter Rule** from
`knowledge/cd-test-architecture.md#the-adapter-rule-own-your-boundaries`:
wrap each third-party HTTP API in a thin team-owned adapter, then double the
adapter (or its `HttpMessageHandler`) in component and contract tests.

For testing the **inbound** HTTP surface (your own ASP.NET Core endpoints — the
API Provider side), use `WebApplicationFactory<TEntryPoint>` instead; see
`knowledge/test-stack-profiles/dotnet.md` → Component / Service row. This
reference is for the *outbound* direction.

## The core pattern: stub HttpMessageHandler

`HttpClient` delegates every request to its `HttpMessageHandler.SendAsync`.
Subclass `HttpMessageHandler` (or `DelegatingHandler`) and return canned
responses keyed off the incoming request. The whole transport stack
collapses to a function `HttpRequestMessage -> HttpResponseMessage`.

```csharp
public sealed class StubHttpMessageHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _handler;
    public List<HttpRequestMessage> Requests { get; } = new();

    public StubHttpMessageHandler(
        Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> handler)
        => _handler = handler;

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken ct)
    {
        Requests.Add(request);
        return _handler(request, ct);
    }
}
```

Inject via `new HttpClient(handler) { BaseAddress = ... }` into the
adapter under test. The captured `Requests` list is the spy surface for
request-shape assertions; the handler delegate is the stub surface for
response control.

## Wiring with IHttpClientFactory (production parity)

When the production code uses `IHttpClientFactory` / typed clients (the
recommended .NET pattern since 2.1), preserve the DI graph and swap only the
leaf handler:

```csharp
services.AddHttpClient<UserClient>(c => c.BaseAddress = new Uri("https://api.test/"))
        .ConfigurePrimaryHttpMessageHandler(() => stubHandler);
```

Same `HttpClient` lifetime, same delegating-handler chain (auth, logging,
retry), only the bottom of the stack changes. This keeps tests honest about
the middleware that production runs.

## What to assert (drive from the contract, not the internals)

A consumer's contract is two-sided: the *request it builds* and the
*response shape it depends on*. Assert both, structurally:

- **Request shape** — method, path, query string, headers, body. Deserialize
  JSON bodies and compare structurally; never string-match request bodies
  (whitespace, member ordering, and culture-formatted numbers all flake).
- **Response handling** — success deserialization (including optional and
  unknown fields per Postel's Law), non-2xx → typed exceptions, empty
  bodies, malformed JSON, content-type mismatches.
- **Cross-cutting** — auth headers, correlation/idempotency keys,
  trace-context propagation, cancellation propagation, deadline/timeout
  enforcement.
- **Retry sequences** — queue a deterministic sequence
  (e.g. `503, 503, 200`); assert the request count and the final outcome.

Map these onto the API Consumer success/failure list in
`knowledge/component-test-patterns.md#api-consumer` — the patterns there are
the source of truth for *what* to cover; this file is *how* to cover it on
.NET.

## Keep it deterministic

Two recurring sources of flake in HTTP-client tests:

- **Time.** Inject `TimeProvider` (built-in since .NET 8) — never call
  `DateTime.UtcNow`, `DateTimeOffset.Now`, or `Task.Delay` directly in
  application logic. In tests, drive `FakeTimeProvider` (from
  `Microsoft.Extensions.TimeProvider.Testing`) forward explicitly. Mirrors
  the determinism rule in
  `knowledge/cd-test-architecture.md#determinism-techniques-minimal-tooling`.
- **Polly jitter / backoff.** When the adapter uses Polly (the .NET resilience
  pipeline) for retry, circuit-breaker, or timeout, configure the pipeline
  with the **same** `TimeProvider`. Polly v8 accepts `TimeProvider` directly
  in its `ResiliencePipelineBuilder` — retries then advance *virtual* time,
  not wall-clock, so a "wait 30s then retry" policy completes in
  microseconds without `Thread.Sleep`.

Combined with the stub handler, the entire outbound HTTP layer — including
retries, timeouts, and circuit-breakers — is a pure function of inputs.

## Testing Polly resilience policies deterministically

This is the canonical setup for the consumer-resilience component tests
required by `knowledge/component-test-patterns.md` → API Consumer §
*Failure modes*:

```csharp
var time = new FakeTimeProvider();
var responses = new Queue<HttpResponseMessage>(new[]
{
    new HttpResponseMessage(HttpStatusCode.ServiceUnavailable),
    new HttpResponseMessage(HttpStatusCode.ServiceUnavailable),
    new HttpResponseMessage(HttpStatusCode.OK) { Content = JsonContent.Create(payload) },
});
var handler = new StubHttpMessageHandler((_, _) => Task.FromResult(responses.Dequeue()));

var pipeline = new ResiliencePipelineBuilder<HttpResponseMessage>()
    .AddRetry(new HttpRetryStrategyOptions { /* ... */ })
    .ConfigureTelemetry(NullLoggerFactory.Instance)
    .Build(); // bind TimeProvider via DI in production wiring

// drive: advance virtual time across each backoff window; assert request count == 3 and final result OK.
```

The same shape proves circuit-breaker open/half-open/closed transitions and
timeout enforcement without any real wall-clock waits.

## Where it sits on the pyramid

Map directly to `knowledge/cd-test-architecture.md` § *The Six Test Types*:

| Behavior under test | MinimumCD layer | Tool |
|---|---|---|
| Pure logic in the adapter (header building, query-string construction, response mapping) | **Unit** (solitary) | xUnit + the adapter constructed directly, no `HttpClient` needed |
| Adapter speaks the wire correctly to a doubled transport: builds the right request, parses the canned response, maps non-2xx to typed errors | **Contract** | xUnit + `StubHttpMessageHandler` |
| Resilience policy (retry/backoff/circuit-breaker/timeout) survives a doubled provider failure | **Component** (resilience) | xUnit + `StubHttpMessageHandler` + `FakeTimeProvider` + Polly bound to that `TimeProvider` |
| Adapter against the real third-party API in a non-prod test environment | **Scheduled provider verification** (out-of-band) | xUnit/console job vs the provider's real endpoint, **never pre-merge** |
| Multi-service journey across real deployed components | **E2E** (post-deploy smoke) | Playwright for .NET — only when the four-condition E2E justification gate from `knowledge/cd-test-architecture.md#the-e2e-justification-gate` is satisfied |

Contract and component tests with the stub handler are **deterministic and
pre-merge** per
`knowledge/cd-test-architecture.md#the-pre-merge-gate-rule`. The scheduled
provider-verification job is the **detection** half of
`knowledge/cd-test-architecture.md#double-validation-keeping-doubles-honest`;
the resilience component test is the **survival** half — both are required
when the provider is third-party (no provider cooperation assumed).

## Off-the-shelf alternatives to the hand-rolled stub

The hand-rolled `StubHttpMessageHandler` is usually enough and has zero
dependencies. Two libraries cover larger or noisier surfaces:

- **`RichardSzalay.MockHttp`** — fluent matcher API (`When(...).Respond(...)`).
  Good when one test method exercises many endpoints and inline matching
  beats a delegate's `switch`.
- **`Moq.Contrib.HttpClient`** — extensions for treating
  `HttpMessageHandler` as a `Mock<>`. Good when the team already uses Moq
  pervasively and prefers one mocking idiom across the suite.

Either library is a stylistic choice over the hand-rolled stub, **not** an
escalation up the pyramid; both still test the same `HttpMessageHandler`
seam in-process, deterministically.

## What to avoid for unit and component tests

These are integration/E2E tooling — fast feedback isn't what they're for,
so they don't belong on the pre-merge gate (see
`knowledge/cd-test-architecture.md#the-pre-merge-gate-rule`):

- **`WebApplicationFactory<T>` to test an outbound client.** It spins up
  the *server* in-process. The seam you want is below the client, not above
  the server. Use it for the API Provider side (inbound HTTP); use the
  stub handler for the API Consumer side.
- **Kestrel on a random port + a real HTTP request.** You are now testing
  the network stack and DNS, not your code. Slow, OS-dependent, flaky.
- **WireMock.Net / MockServer for unit tests.** These are full HTTP
  servers in-process. Reserve them for the **adapter-integration** layer
  (Stage 1/2, off-gate) where the network behavior itself is under test —
  TLS, HTTP/2, proxy, real timeouts. For pre-merge behavior coverage, the
  in-process `HttpMessageHandler` stub is strictly faster and at least as
  accurate.

## Common smells in C# HTTP-consumer tests

Catalogued so `test-smell-review` and `test-design-advisor` can map a
finding to the .NET-specific fix:

- **Mocking `HttpClient` directly** (e.g. with Moq). `HttpClient` is a
  sealed/non-virtual surface in practice; mocking it requires reflection
  hacks or `InternalsVisibleTo`, both of which are test workarounds for a
  missing production seam. Wrap it in an adapter and double the
  `HttpMessageHandler` instead. (`knowledge/test-doubles.md` rule:
  never invent a test-only seam to dodge a missing production one.)
- **Mocking the third-party SDK directly** instead of an owned adapter.
  Same pattern, same fix — Adapter Rule applies.
- **`DateTime.UtcNow` in retry/expiry logic** without `TimeProvider`. The
  test must `Thread.Sleep` (or worse, give up determinism). Inject the
  clock.
- **`Thread.Sleep`/`Task.Delay` in tests** to wait for retries. Always a
  symptom of (a) above. Use `FakeTimeProvider` and Polly bound to it.
- **String-matching JSON request bodies.** Deserialize structurally; the
  test breaks on whitespace and culture otherwise.
- **Asserting against the adapter's internal calls** (e.g. with a behaviour
  verification mock) instead of the request that crossed the seam. The
  contract is the request bytes the SUT *would emit*, not which method on
  the SDK it called. Prefer state verification of `Requests` captured by
  the stub handler.

## Boundaries

This file covers .NET-specific *mechanics* for the API Consumer pattern.
The pattern itself — coverage layers, success/failure scenarios, double
validation loop, pipeline placement — lives in
`knowledge/component-test-patterns.md#api-consumer` and is language-agnostic.
For the broader stack picture (which tool at which layer on .NET), see
`knowledge/test-stack-profiles/dotnet.md`. For a worked example using this
pattern end-to-end, see
`knowledge/test-matrix-examples/dotnet-http-consumer.md`.
