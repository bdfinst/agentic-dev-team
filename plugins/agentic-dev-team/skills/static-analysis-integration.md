---
name: static-analysis-integration
description: >-
  Pre-pass stage for /code-review that runs available static analysis tools
  (Semgrep, ESLint, TypeScript compiler, pylint) before dispatching AI review
  agents. Deduplicates findings across tools and passes confirmed issues to
  agents so they can focus on semantic concerns.
role: worker
user-invocable: false
---

# Static Analysis Integration

## Overview

This skill defines the static analysis pre-pass for `/code-review`. When
enabled, it runs deterministic analysis tools before AI agents, collecting
structured findings that agents receive as pre-confirmed context. This
reduces token waste on syntactic issues and lets agents focus on semantic
and architectural concerns.

## Constraints

1. **Do not modify code.** Collect and report findings only.
2. **Graceful degradation.** If no tools are installed, return an empty
   result — never fail the pipeline.
3. **Deduplicate across tools.** The same issue reported by both ESLint
   and Semgrep should appear once, attributed to the first tool that
   found it.

## Supported Tools

| Tool | Detection | Output Format | File Types |
|------|-----------|---------------|------------|
| Semgrep | `which semgrep` | JSON (`--json`) | All supported |
| ESLint | `npx eslint --version` or project has `.eslintrc*` / `eslint.config.*` | JSON (`-f json`) | JS, TS, JSX, TSX |
| TypeScript | `tsconfig.json` exists | Line-based (`tsc --noEmit`) | TS, TSX |
| pylint | `which pylint` | JSON (`--output-format=json`) | Python |

## Execution Steps

### 1. Detect available tools

For each tool in the table above, run the detection command. Record
which tools are available. If none are available, return:

```json
{
  "status": "skip",
  "tools": [],
  "findings": [],
  "summary": "No static analysis tools detected — skipping pre-pass."
}
```

### 2. Run each available tool

Run tools in parallel where possible. For each tool:

**Semgrep**:
```bash
semgrep scan --config auto --quiet --json <target-files-or-path>
```

Map findings using the schema from `/semgrep-analyze` (step 3 of that
skill). Each finding becomes:

```json
{
  "tool": "semgrep",
  "severity": "error|warning|suggestion",
  "file": "<path>",
  "line": 0,
  "ruleId": "<check_id>",
  "message": "<description>",
  "cwe": "<CWE-ID if present>"
}
```

**ESLint**:
```bash
npx eslint -f json <target-js-ts-files>
```

Map findings:

| ESLint field | Output field |
|-------------|-------------|
| `filePath` | `file` |
| `messages[].line` | `line` |
| `messages[].ruleId` | `ruleId` |
| `messages[].message` | `message` |
| `messages[].severity` (1=warn, 2=error) | `severity` |

```json
{
  "tool": "eslint",
  "severity": "error|warning",
  "file": "<path>",
  "line": 0,
  "ruleId": "<rule-id>",
  "message": "<description>"
}
```

**TypeScript compiler**:
```bash
npx tsc --noEmit 2>&1
```

Parse `file(line,col): error TSxxxx: message` lines:

```json
{
  "tool": "tsc",
  "severity": "error",
  "file": "<path>",
  "line": 0,
  "ruleId": "TSxxxx",
  "message": "<description>"
}
```

**pylint**:
```bash
pylint --output-format=json <target-py-files>
```

Map findings:

| pylint field | Output field |
|-------------|-------------|
| `path` | `file` |
| `line` | `line` |
| `message-id` | `ruleId` |
| `message` | `message` |
| `type` (error/warning/convention/refactor) | `severity` |

Severity mapping: `error` → error, `warning` → warning,
`convention`/`refactor` → suggestion.

### 3. Deduplicate findings

Two findings are duplicates if they share the same `file`, `line`, and
a matching `message` (fuzzy — same semantic meaning). When duplicates
exist, keep the finding from the more specific tool (Semgrep > ESLint >
tsc > pylint) and note the duplicate source.

### 4. Return structured result

```json
{
  "status": "pass|warn|fail",
  "tools": ["semgrep", "eslint"],
  "findings": [
    {
      "tool": "semgrep",
      "severity": "error",
      "file": "src/api/handler.ts",
      "line": 42,
      "ruleId": "javascript.express.security.audit.xss",
      "message": "Potential XSS vulnerability",
      "cwe": "CWE-79"
    }
  ],
  "summary": "12 findings from 2 tools: 3 errors, 7 warnings, 2 suggestions"
}
```

Status: `fail` if any errors, `warn` if warnings but no errors,
`pass` if clean or no tools available.

## Agent Context Injection

When findings are passed to review agents, format them as:

```text
## Static Analysis Pre-Pass Results

The following issues were detected by static analysis tools (Semgrep,
ESLint, etc.). These are confirmed syntactic/structural findings.
Do not re-report these issues. Focus your review on semantic and
architectural concerns that static analysis cannot detect.

| Tool | Severity | File | Line | Rule | Message |
|------|----------|------|------|------|---------|
| semgrep | error | src/api/handler.ts | 42 | xss-audit | Potential XSS |
| eslint | warning | src/utils/parse.ts | 17 | no-unused-vars | 'x' is unused |
```

If no findings exist, pass: "Static analysis pre-pass ran (tools:
semgrep, eslint). No findings — all clear."

This context goes to **all** review agents, not just security-review.
Agents in any domain (structure, naming, performance) benefit from
knowing what static tools already caught.
