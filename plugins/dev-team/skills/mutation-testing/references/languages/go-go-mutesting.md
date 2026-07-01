# Mutation Testing — Go (go-mutesting, advisory only)

Tool: [go-mutesting](https://github.com/zimmski/go-mutesting). Detection: `go.mod` present; `command -v go-mutesting` resolves (installed to `$GOPATH/bin`).

**Advisory only.** go-mutesting is alpha quality — the surviving-mutant count is **not** a reliable gate. Always pair with Go's built-in fuzzing (production-quality) for boundary and edge-case discovery.

## Install / detect

```bash
go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest
```

## Run (scoped)

> When capturing run output to a log file, do **not** use a bare `go-mutesting ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a tool failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

```bash
# Whole module
go-mutesting ./...

# Single package
go-mutesting ./pkg/order
```

## Per-mutant timeout flag

go-mutesting has no reliable per-mutant flag. Wrap the process externally:

```bash
timeout <seconds> go-mutesting ./...   # macOS: gtimeout (from coreutils)
```

Default shipped: 60 s. Set the outer wrapper timeout to `timeout_seconds` (formula in [`SKILL.md`](../../SKILL.md) Step 1b).

## Native report → schema mapping

go-mutesting has no stable machine-readable report. Parse its stdout (each mutant prints `PASS`/`FAIL` with the mutated `file:line`) and map into the standard envelope, adding `"advisory": true` so callers warn instead of halt. The `equivalent` count is `0` unless triage reclassifies a survivor.

```json
{
  "schema_version": 1,
  "tool": "go-mutesting",
  "advisory": true,
  "scope": ["pkg/order/order.go"],
  "captured_at": "2026-06-26T14:31:00Z",
  "total": 40,
  "killed": 31,
  "survived": 9,
  "equivalent": 0,
  "survivors": [
    { "file": "pkg/order/order.go", "line": 22, "operator": "branch/condition", "status": "survived" }
  ]
}
```

Because go-mutesting is advisory, downstream workflow callers MUST treat `advisory: true` as warn-not-block — a non-zero survivor count never fails the gate.

## Language-specific notes

### Advisory mode rationale

The orchestrated workflows (`/coverage-delta`, `/quality-targets-converge`) treat Go mutation results as **warn, do not block** — surface survivors as suggestions, never block on the count. Advisory mode is enforced by the `"advisory": true` flag on the schema envelope.

Never tell a Go project "no tool installed" without giving both:

1. The go-mutesting install path (above), and
2. The fuzz alternative (below).

### `go test -fuzz` complement (production-quality)

Native Go fuzzing (Go 1.18+) catches boundary/edge cases mutation testing can miss. The `-fuzz` flag takes a regexp matching a single `FuzzXxx` target and fuzzes **one package at a time** — it is **not** a package glob:

```bash
# Run every fuzz target's seed corpus as ordinary tests (all packages)
go test ./...

# Actively fuzz one target (bounded for a pre-merge gate)
go test -fuzz=FuzzXxx -fuzztime=30s ./path/to/pkg
```

Manage the fuzz corpus deliberately:

- Seed it from known edge cases.
- Commit interesting inputs under `testdata/fuzz/` so failures reproduce in CI.
- Run a bounded `-fuzztime` in the pre-merge gate while letting longer campaigns run out of band.

Pair the advisory go-mutesting result with `go test -fuzz` findings when reporting to the operator.
