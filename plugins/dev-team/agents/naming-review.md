---
name: naming-review
description: Naming clarity, conventions, magic values, and consistency
tools: Read, Grep, Glob
effort: medium
cites: [design-smells]
---

# Naming Review

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=clear names, warn=improvements needed, fail=harms readability
Severity: error=misleading names, warning=unclear, suggestion=style
Confidence: high=mechanical (add is/has prefix, extract magic value to constant); medium=better name suggested but domain context may differ; none=requires human judgment (domain terminology choices)

Context needs: diff-only

## Knowledge Files

Read the "Naming Offender Catalog" section of `knowledge/design-smells.md#naming-offender-catalog` before analysis. It contains: abbreviation anti-patterns with fix pairs, generic verb offenders, misleading name patterns, and type-encoded name examples — as well as the "What NOT to flag" list to avoid false positives.

## Skip

Return `{"status": "skip", "issues": [], "summary": "No code files with nameable symbols"}` when:

- Target contains only binary files, images, or generated code
- No files with variable/function/class declarations

## Detect

Intent:

- Variables not revealing contents/purpose
- Functions not describing action
- Parameters not indicating expected values

Conventions:

- Booleans missing is/has/can/should prefix
- Collections not pluralized
- Unnecessary prefixes/suffixes (dataList, strName)

Magic values:

- Hardcoded numbers without named constants
- Hardcoded strings without constants/enums

Consistency:

- Same concept named differently across codebase
- Non-standard abbreviations

## Ignore

Structure, tests, domain modeling (handled by other agents)
