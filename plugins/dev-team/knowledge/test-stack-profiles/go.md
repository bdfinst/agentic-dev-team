# Stack profile — Go

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical Go tool. Go's standard `testing` package covers most layers; reach for libraries sparingly.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | `testing` + table-driven tests; interfaces for collaborators | call the function; stdlib `if got != want` or testify/assert |
| Component / Service | `net/http/httptest` (`httptest.NewServer` / `ResponseRecorder`) | drive the handler in-process; double outbound deps via interfaces |
| Integration | Testcontainers-go (real DB/broker) | repository/SQL/driver against a real dependency |
| Contract | Pact-go | consumer↔provider agreement (`microservice-testing.md`) |
| E2E | `rod` / `chromedp`, or `go test` driving the built binary | critical journeys only |

**Notes.** Define narrow interfaces at the consumer and substitute them — idiomatic Go doubling, no mock framework needed (generate with `moq`/`mockgen` only when hand-writing is tedious). Inject a clock (`func() time.Time`) rather than calling `time.Now()` in logic. Use the race detector (`go test -race`) on concurrency-bearing code. Fuzzing is built in (`func FuzzX(f *testing.F)`) — see `testing-techniques/fuzz.md`.
