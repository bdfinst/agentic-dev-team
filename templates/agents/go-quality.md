---
name: go-quality
description: Go code quality — error handling discipline, interface segregation, no naked returns, struct embedding patterns
tools: Read, Grep, Glob
model: haiku
---

# Go Quality

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=idiomatic Go, warn=improvements needed, fail=error handling gaps
Severity: error=ignored error or unsafe pattern, warning=non-idiomatic, suggestion=style
Confidence: high=mechanical (handle error, remove naked return); medium=design choice; none=domain context

Model tier: small
Context needs: diff-only
File scope: `*.go`

## Activates when

`go.mod` exists.

## Skip

Return skip when no `.go` files in the changeset.

## Detect

Error handling:

- Ignored errors (`_ = someFunc()` without justification)
- Error not checked after function call that returns error
- Error wrapping without context (`return err` instead of `return fmt.Errorf("doing X: %w", err)`)
- Panics in library code (only acceptable in `main` or test helpers)

Returns:

- Naked returns in functions longer than a few lines
- Named return values that aren't needed for documentation or defer

Interfaces:

- Large interfaces (>5 methods) — prefer small, composable interfaces
- Interfaces defined by the implementer instead of the consumer
- Unused interface methods

Struct patterns:

- Embedding for code reuse rather than composition (prefer composition)
- Exported fields on structs that should be private
- Missing constructors for structs with required fields

Concurrency:

- Goroutine leaks (goroutine started without cancellation or done channel)
- Shared state without mutex or channel protection
- `sync.WaitGroup` misuse (Add after Go)

## Ignore

Test files (test helpers may legitimately panic), generated code, vendor directory.
