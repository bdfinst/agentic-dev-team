# Output Format Reference

## Per-agent JSON result

```json
{
  "agentName": "structure-review",
  "status": "pass|warn|fail|skip",
  "modelTier": "mid",
  "issues": [
    {
      "severity": "error|warning|suggestion",
      "confidence": "high|medium|none",
      "file": "src/auth/login.ts",
      "line": 42,
      "message": "God object: AuthController handles login, registration, and password reset",
      "suggestedFix": "Split into LoginController, RegistrationController, and PasswordResetController"
    }
  ],
  "summary": "2 issues found: 1 error, 1 warning"
}
```

### `confidence` field values

| Value | Meaning | `apply-fixes` behavior |
|-------|---------|----------------------|
| `high` | Mechanical fix; correct with high certainty | Auto-apply |
| `medium` | Direction right; tradeoffs possible | Present as suggested diff — require confirmation |
| `none` | Requires human judgment | Present finding only; do not generate correction prompt |

## Aggregated JSON result (`--json` flag)

```json
{
  "overall": "pass|warn|fail",
  "timestamp": "2026-03-01T12:00:00Z",
  "targetFiles": 42,
  "preFlightPassed": true,
  "agents": [
    {"agentName": "test-review", "status": "pass", "modelTier": "mid", "issues": [], "summary": "..."}
  ],
  "totals": {"errors": 0, "warnings": 2, "suggestions": 1},
  "tokenEstimate": {
    "totalInputFiles": 15000,
    "agentCount": 11,
    "contextStrategy": "diff-only|full-file|mixed"
  },
  "summary": "WARN (N agents passed, N warned, N failed). N total issues."
}
```

The `tokenEstimate` field provides rough cost observability:

- `totalInputFiles`: approximate character count of all input files passed to agents
- `agentCount`: number of agents that ran (not skipped)
- `contextStrategy`: whether diff-only, full-file, or a mix was used

## Correction prompt JSON

```json
{
  "priority": "high|medium|low",
  "confidence": "high|medium",
  "category": "structure-review",
  "instruction": "Fix: God object handles too many concerns (Suggested: Split into focused controllers)",
  "context": "Line 42 in src/auth/login.ts",
  "affectedFiles": ["src/auth/login.ts"]
}
```

Severity mapping: error→high, warning→medium, suggestion→low.

Correction prompts are only generated for issues with `confidence: high` or `confidence: medium`. Issues with `confidence: none` are included in the review report but do not produce correction prompts — they require human judgment and must be resolved manually before merging.

## Status rules

- **pass**: Zero issues
- **warn**: Issues found, none are errors
- **fail**: At least one error-severity issue
- **skip**: Agent is inapplicable to the target (e.g., no JS/TS files for js-fp-review)

## Model tier values

Each agent declares a `Model tier` field that controls which model runs it:

| Tier | Model | Use for |
| ------ | ------- | --------- |
| `small` | Haiku | Pattern matching, thresholds, naming checks |
| `mid` | Sonnet | Structural analysis, test quality, mutation detection |
| `frontier` | Opus | Security analysis, domain modeling, semantic reasoning |

## Context needs values

Each agent declares a `Context needs` field that controls what input it receives:

| Value | Input | When to use |
| ------- | ------- | ------------- |
| `diff-only` | Git diff output only | Pattern-matching agents (naming, FP) |
| `full-file` | Complete file contents | Agents needing function-level context |
| `project-structure` | Full files + directory tree | Agents reasoning about architecture |
