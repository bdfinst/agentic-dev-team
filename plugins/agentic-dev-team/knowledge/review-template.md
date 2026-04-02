# Code Review Report Template

Use this template for non-JSON (`--json` not set) code review output.
The orchestrator reads this file during Step 5 (Aggregate and report).

---

## Report Structure

```
# Code Review Summary

**Overall: {PASS|WARN|FAIL}** — {1-sentence summary}
**Date:** {ISO 8601}
**Scope:** {file count} files ({--changed|--since <ref>|--path <dir>|full repo})
**Health:** {🟢|🟠|🔴} ({see review-rubric.md for scoring})

## Pre-Flight Gates

| Gate | Result | Details |
|------|--------|---------|
| Lint | ✅/❌/➖ | {pass/fail/skipped} |
| Type check | ✅/❌/➖ | {pass/fail/skipped} |
| Secret scan | ✅/❌/➖ | {pass/fail/skipped} |
| Semgrep | ✅/❌/➖ | {pass/fail/skipped} |
| Pipeline | ✅/❌/➖ | {pass/fail/skipped} |

## Agent Results

| Agent | Status | Issues | Model |
|-------|--------|--------|-------|
| {name} | PASS/WARN/FAIL | {count} | {haiku/sonnet/opus} |
| ... | | | |

**Totals:** {N} errors, {N} warnings, {N} suggestions

## Institutional Context

{If REVIEW-CONTEXT.md was found, summarize key points that influenced the review.
 Omit this section if no context file exists.}

## Issues by File

### {file path}

| # | Severity | Agent | Message | Confidence |
|---|----------|-------|---------|------------|
| 1 | 🔴 error | security-review | {message} | high |
| 2 | 🟠 warning | test-review | {message} | medium |
| 3 | 💡 suggestion | naming-review | {message} | high |

{Repeat for each file with issues, sorted by severity (errors first).}
{Issues with confidence: none are marked [human review required].}

## Recommendations

Top 3 priorities synthesized across all agent findings:

1. **{Priority 1}** — {1-2 sentences, cite agent and file}
2. **{Priority 2}** — {1-2 sentences, cite agent and file}
3. **{Priority 3}** — {1-2 sentences, cite agent and file}

## Tool Availability

| Tool | Available | Used By |
|------|-----------|---------|
| {MCP tool name} | ✅/❌ | {agent names} |
| semgrep | ✅/❌ | pre-flight, security-review |

{Omit this section if no optional tools were probed.}
```

## Severity Icons

Use these consistently:

| Severity | Icon |
|----------|------|
| error | 🔴 |
| warning | 🟠 |
| suggestion | 💡 |

## Health Score Icons

| Health | Icon |
|--------|------|
| Healthy | 🟢 |
| Needs attention | 🟠 |
| Critical | 🔴 |
