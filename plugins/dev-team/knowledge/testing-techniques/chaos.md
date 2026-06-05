# Chaos / resilience testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior makes a **resilience claim under dependency failure** — "retries on a 5xx", "degrades gracefully when the cache is down", "the circuit breaker opens", "recovers after the broker reconnects". The risk is in the *failure* path, which happy-path tests never exercise.

**What it is.** Deliberately inject failure — latency, errors, dropped connections, killed dependencies — and assert the system's degradation/recovery behavior matches the claim.

**When to use.** Distributed systems, anything with retries/timeouts/circuit-breakers/fallbacks, jobs that must survive a mid-run dependency outage.

**Scope split (important).** Inject failure at the **owned adapter** in a component test to verify retry/fallback *logic* deterministically (pre-merge). Reserve infrastructure-level chaos (kill a pod, partition the network) for **out-of-band/staging** — it is non-deterministic and never belongs in the pre-merge gate (`cd-test-architecture.md`).

**Trade-offs / cost.** Infra chaos is flaky and slow; needs a controlled environment and observability to read results. Start with adapter-level fault injection — most resilience bugs surface there cheaply.

**Minimal shape.** Stub the payment adapter to throw `Timeout` twice then succeed → assert two retries then success.

**Complements.** Component (adapter fault injection) and out-of-band (infra). Q4 in `testing-quadrants.md`. Tools: Toxiproxy, fault-injecting test doubles, Chaos Monkey / Litmus (infra).
