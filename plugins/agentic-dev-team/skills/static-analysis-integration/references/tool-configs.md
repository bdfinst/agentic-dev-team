# Static Analysis Tool Configurations

Per-tool commands, field mappings, and unified output schemas.

## Semgrep

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

## ESLint

```bash
npx eslint -f json <target-js-ts-files>
```

### Field mapping

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

## TypeScript Compiler

```bash
npx tsc --noEmit 2>&1
```

Parse `file(line,col): error TSxxxx: message` lines.

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

## pylint

```bash
pylint --output-format=json <target-py-files>
```

### Field mapping

| pylint field | Output field |
|-------------|-------------|
| `path` | `file` |
| `line` | `line` |
| `message-id` | `ruleId` |
| `message` | `message` |
| `type` (error/warning/convention/refactor) | `severity` |

### Severity mapping

`error` -> error, `warning` -> warning, `convention`/`refactor` -> suggestion.

```json
{
  "tool": "pylint",
  "severity": "error|warning|suggestion",
  "file": "<path>",
  "line": 0,
  "ruleId": "<message-id>",
  "message": "<description>"
}
```
