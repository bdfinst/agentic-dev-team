---
name: functional-patterns
description: Functional programming patterns for JS/TS — immutability, pure functions, composition, array methods over loops
tools: Read, Grep, Glob
model: haiku
---

# Functional Patterns

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=functional style, warn=imperative patterns detected, fail=mutation in shared state
Severity: error=shared mutable state, warning=imperative pattern with functional alternative, suggestion=style preference
Confidence: high=mechanical (use map instead of for loop); medium=judgment call (mutation in local scope); none=requires domain context

Model tier: small
Context needs: diff-only
File scope: `*.ts`, `*.tsx`, `*.js`, `*.jsx`

## Activates when

Any JS/TS project detected. Always-on for JavaScript and TypeScript projects.

## Skip

Return skip when no JS/TS files in the changeset, or changeset is config/generated only.

## Detect

Immutability:

- `let` used where `const` suffices
- Array mutation methods on shared state (`.push()`, `.splice()`, `.sort()` in place)
- Object mutation of parameters or shared references
- Missing spread/destructuring for immutable updates

Pure functions:

- Functions with side effects not indicated by name or type
- Functions that read or modify external state
- Mixed computation and I/O in the same function

Composition:

- Class inheritance where composition would be simpler
- Deep nesting that could be flattened with pipe/compose
- Callback pyramids that could use Promise chains or async/await

Array methods:

- `for` loops that could be `map`, `filter`, `reduce`, `find`, `some`, `every`
- Manual accumulation patterns that match `reduce`
- Index-based iteration where `for...of` or array methods work

Early returns:

- Nested conditionals that could use guard clauses
- `else` blocks after `return` statements

## Ignore

- Performance-critical hot paths where mutation is justified
- Framework-mandated patterns (React state, Redux reducers handle immutability differently)
- Test files (test readability > functional purity)
