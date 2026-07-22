---
name: plugin-best-practices-review
description: Plugin structural best practices — agent type appropriateness, frontmatter compliance, eval coverage, and body line-count budgets
tools: Read, Grep, Glob
effort: medium
---
# Plugin Best Practices Review

Cites: [agent-type-decision-rules]

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=clean, warn=missing eval coverage or over budget, fail=type mismatch or malformed frontmatter
Severity: error=breaks plugin contract, warning=structural drift, suggestion=tightening
Confidence: high=mechanical (field absent, line count); medium=type judgment with rule support; none=human judgment
Context needs: project-structure
Read `knowledge/agent-type-decision-rules.md` first — the rule source (R1–R10) for the type check; cite rule IDs in findings.

## Skip

Return `{"status": "skip", "issues": [], "summary": "Not a plugin directory"}` when the target has no `agents/` or `skills/`.

## Detect

Agent type (markdown vs script):

- markdown unit with a purely mechanical body (R1–R5) → should be a script; a script whose job needs judgment (R6–R9) → should be markdown. Cite the governing rule IDs.

Frontmatter compliance:

- missing `name`, `description`, or `effort` on an agent; a colon inside the `description` value; a `## Skills` body section without `Skill` in `tools`.

Eval coverage:

- a review agent (JSON-output body) with no fixture under `evals/<plugin>/`.

Body line-count:

- review-agent body over 40 lines; team-agent body over 75 lines.

## Ignore

Detection-logic quality (the plugin's own `agent-eval`); shipping hygiene and portability (`plugin-audit` sibling checks).
