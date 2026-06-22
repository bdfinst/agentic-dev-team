---
name: complexity-review
description: Cyclomatic complexity, nesting depth, function size, parameter count
tools: Read, Grep, Glob
effort: medium
cites: [object-calisthenics]
---

# Complexity Review

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=manageable, warn=hotspots, fail=critical issues
Severity: error=unmaintainable, warning=high complexity, suggestion=could simplify
Confidence: high=threshold violation (function >N lines, nesting >N levels); medium=extraction direction clear, exact split requires context; none=requires human judgment (algorithm design)

Effort: medium
Context needs: full-file

## Knowledge Files

Read `knowledge/object-calisthenics.md` before analysis. Whole-file load: the agent needs all nine rules as design-pressure thresholds (especially rule 1 one-indentation-level, rule 2 no-else, rule 7 small-entities) plus the rationale prose tying them to the numeric limits below.

## Skip

Return `{"status": "skip", "issues": [], "summary": "No code files in target"}` when:

- Target contains only configuration, documentation, or data files
- No files with functions/methods to analyze

## Thresholds

| Metric | Limit |
| -------- | ------- |
| Function lines | <20 |
| Cyclomatic complexity | <10 |
| Nesting depth | <4 |
| Parameters | <5 |

## Detect

Function size:

- Functions >20 lines
- Functions with >5 parameters

Control flow:

- >10 branches (if/else/switch cases)
- >4 nesting levels
- Complex boolean expressions
- Large switch statements

Async:

- Callback hell (nested callbacks) — JS/TS
- Unstructured promise chains — JS/TS: chained `.then()` without error handling; C#: deeply nested `ContinueWith()` instead of `async/await`; Java: deeply nested `CompletableFuture` chains without `exceptionally()`
- Blocking calls inside async methods — C#: `.Result` or `.Wait()` on a `Task`; Java: `Future.get()` without timeout

Cognitive load:

- Too many concepts per function
- Non-obvious control flow

## Self-Challenge

After producing findings, run the adversarial challenge pass from `knowledge/adversarial-review-protocol.md#structure-review`. Use the structure-review challenge questions (the nearest applicable section — no complexity-specific section exists). Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

Domain modeling, naming, tests (handled by other agents)
