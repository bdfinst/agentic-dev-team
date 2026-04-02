---
name: csharp-quality
description: "C# code quality — nullable reference types, async/await discipline, record types for DTOs, dependency injection patterns"
tools: Read, Grep, Glob
model: haiku
---

# C# Quality

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=modern C#, warn=improvements needed, fail=unsafe patterns
Severity: error=null safety issue or async misuse, warning=non-modern pattern, suggestion=style
Confidence: high=mechanical (enable nullable, use record); medium=design choice; none=domain context

Model tier: small
Context needs: diff-only
File scope: `*.cs`

## Activates when

`.csproj` or `.sln` exists.

## Skip

Return skip when no `.cs` files in the changeset.

## Detect

Nullable reference types:

- `<Nullable>enable</Nullable>` missing in `.csproj`
- Null-forgiving operator (`!`) used without safety check
- Missing null checks at public API boundaries
- `dynamic` type usage (loses type safety)

Async/await:

- `async void` methods (except event handlers)
- `.Result` or `.Wait()` on tasks (deadlock risk)
- Missing `ConfigureAwait(false)` in library code
- Fire-and-forget tasks without error handling

Modern C#:

- Classes used for DTOs where `record` types would be immutable and concise
- Manual `Equals`/`GetHashCode` where `record` handles it
- `string.Format` instead of string interpolation
- `switch` statements that could use pattern matching

Dependency injection:

- `new`-ing services instead of injecting via constructor
- Service locator anti-pattern (`IServiceProvider.GetService` in business logic)
- Missing interface for testability
- Transient services holding state

## Ignore

Test projects, generated code, migration files, Razor views.
